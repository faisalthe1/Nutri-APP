from concurrent.futures import ThreadPoolExecutor
from django.core.paginator import Paginator
from django.views.decorators.cache import never_cache

from django.shortcuts import render, redirect
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from .forms import SignUpForm, PreferencesForm, GuestPreferencesForm
from .models import UserPreferences, SavedMeal
from .services import search_fast_foods, get_meal_details

def index(request):
    if request.user.is_authenticated:
        try:
            preferences = request.user.userpreferences
            return redirect('recommendations')
        except UserPreferences.DoesNotExist:
            return redirect('set_preferences')
    return render(request, 'nutrition/index.html')

def register(request):
    if request.method == 'POST':
        form = SignUpForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, 'Registration successful! Please set your preferences.')
            return redirect('set_preferences')
    else:
        form = SignUpForm()
    return render(request, 'nutrition/register.html', {'form': form})

@login_required
def set_preferences(request):
    # Initialize form with existing or default values
    try:
        preferences = request.user.userpreferences
        form_data = None
    except UserPreferences.DoesNotExist:
        preferences = None
        form_data = {
            'goal': 'bulking',
            'calorie_limit': 2500,
            'protein_target': 150,
            'carb_target': 300,
            'fat_target': 70,
            'allergies': []
        }

    if request.method == 'POST':
        form = PreferencesForm(
            request.POST,
            instance=preferences,
            initial=form_data if not preferences else None
        )

        if form.is_valid():
            preferences = form.save(commit=False)
            preferences.user = request.user
            preferences.save()
            form.save_m2m()  # For many-to-many fields if any
            messages.success(request, 'Preferences saved successfully!')
            return redirect('recommendations')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = PreferencesForm(
            instance=preferences,
            initial=form_data if not preferences else None
        )

    return render(request, 'nutrition/preferences.html', {
        'form': form,
        'existing_preferences': bool(preferences)
    })

def guest_preferences(request):
    if request.method == 'POST':
        form = GuestPreferencesForm(request.POST)
        if form.is_valid():
            request.session['guest_prefs'] = form.cleaned_data
            return redirect('recommendations')
    else:
        form = GuestPreferencesForm(initial=request.session.get('guest_prefs'))
    return render(request, 'nutrition/guest_preferences.html', {'form': form})


@never_cache
def recommendations(request):
    if request.user.is_authenticated:
        try:
            preferences = request.user.userpreferences
            context = {
                'goal': preferences.goal,
                'calorie_limit': preferences.calorie_limit,
                'protein_target': preferences.protein_target,
                'carb_target': preferences.carb_target,
                'fat_target': preferences.fat_target,
                'allergies': preferences.allergies if preferences.allergies not in ('[]', '', None) else [],
            }
        except UserPreferences.DoesNotExist:
            messages.warning(request, 'Please set your preferences first.')
            return redirect('set_preferences')
    else:
        if 'guest_prefs' not in request.session:
            return redirect('guest_preferences')
        context = request.session['guest_prefs']

    query = request.GET.get("q", "").strip()[:100] or "McDonald's"
    meals = search_fast_foods(
        query=query,
        goal=context['goal'],
        max_calories=context['calorie_limit'] if context['goal'] == 'cutting' else None,
        min_protein=context['protein_target'] if context['goal'] == 'bulking' else None
    )
    service_unavailable = meals is None

    if meals is None:
        messages.error(request, 'We encountered an issue fetching recommendations. Please try again later.')
        meals = []
    elif not meals:
        messages.warning(request, 'No meals found matching your criteria. Try adjusting your preferences.')

    return render(request, 'nutrition/results.html', {
        'meals': meals,
        'preferences': context,
        'query': query,
        'service_unavailable': service_unavailable,
    })


@never_cache
def meal_detail(request, meal_id):
    meal = get_meal_details(meal_id)
    if not meal and request.user.is_authenticated and not meal_id.startswith('fs-'):
        saved = SavedMeal.objects.filter(user=request.user, meal_id=meal_id).first()
        if saved:
            meal = {'food_name': saved.meal_name, 'brand_name': saved.restaurant,
                    'nf_calories': saved.calories, 'nf_protein': saved.protein,
                    'nf_total_carbohydrate': saved.carbs, 'nf_total_fat': saved.fat,
                    'serving_description': '1 saved serving', 'legacy': True}
    if not meal:
        messages.error(request, 'Could not retrieve meal details.')
        return redirect('recommendations')

    is_saved = False
    if request.user.is_authenticated:
        is_saved = SavedMeal.objects.filter(user=request.user, meal_id=meal_id).exists()

    return render(request, 'nutrition/meal_detail.html', {
        'meal': meal,
        'is_saved': is_saved,
        'meal_id': meal_id,
        'preferences': (getattr(request.user, 'userpreferences', None)
                        if request.user.is_authenticated else request.session.get('guest_prefs')),
    })

@login_required
@require_POST
def save_meal(request, meal_id):
    if request.method == 'POST':
        meal = get_meal_details(meal_id)
        if meal:
            SavedMeal.objects.get_or_create(
                user=request.user,
                meal_id=meal_id,
                # FatSecret Basic permits persisting IDs, not food content.
                # Keep the existing schema for legacy Nutritionix snapshots.
                defaults={'meal_name': '', 'restaurant': '', 'calories': 0,
                          'protein': 0, 'carbs': 0, 'fat': 0},
            )
            messages.success(request, 'Meal saved to your favorites!')
        else:
            messages.error(request, 'Could not save meal.')

    return redirect('meal_detail', meal_id=meal_id)

@login_required
@never_cache
def saved_meals(request):
    page = Paginator(SavedMeal.objects.filter(user=request.user).order_by('-saved_at'), 6).get_page(request.GET.get('page'))
    meals = list(page.object_list)
    current = [meal for meal in meals if meal.meal_id.startswith('fs-')]
    if current:
        with ThreadPoolExecutor(max_workers=3) as pool:
            details = list(pool.map(get_meal_details, [meal.meal_id for meal in current]))
        for meal, detail in zip(current, details):
            meal.unavailable = detail is None
            if detail:
                # Display-only attributes: never save fetched content to the DB.
                meal.meal_name = detail['food_name']
                meal.restaurant = detail['brand_name']
                meal.calories = detail['nf_calories']
                meal.protein = detail['nf_protein']
                meal.carbs = detail['nf_total_carbohydrate']
                meal.fat = detail['nf_total_fat']
            else:
                meal.meal_name = 'Saved meal'
    return render(request, 'nutrition/saved_meals.html', {'meals': meals, 'page_obj': page})


def health(request):
    """Process health, independent of nutrition provider availability."""
    return JsonResponse({"status": "ok"})
