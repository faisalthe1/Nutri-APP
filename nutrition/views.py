from django.shortcuts import render

# Create your views here.
from django.shortcuts import render, redirect
from django.contrib.auth import login, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib import messages
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
        form = GuestPreferencesForm()
    return render(request, 'nutrition/guest_preferences.html', {'form': form})


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
                'allergies': preferences.allergies,
            }
        except UserPreferences.DoesNotExist:
            messages.warning(request, 'Please set your preferences first.')
            return redirect('set_preferences')
    else:
        if 'guest_prefs' not in request.session:
            return redirect('guest_preferences')
        context = request.session['guest_prefs']
    
    meals = search_fast_foods(
        query="fast food", 
        goal=context['goal'],
        max_calories=context['calorie_limit'] if context['goal'] == 'cutting' else None,
        min_protein=context['protein_target'] if context['goal'] == 'bulking' else None
    )
    print('measl', meals)
    
    if meals is None:
        messages.error(request, 'We encountered an issue fetching recommendations. Please try again later.')
        meals = []
    elif not meals:
        messages.warning(request, 'No meals found matching your criteria. Try adjusting your preferences.')
    
    return render(request, 'nutrition/results.html', {
        'meals': meals,
        'preferences': context,
    })


def meal_detail(request, meal_id):
    meal = get_meal_details(meal_id)
    if not meal:
        messages.error(request, 'Could not retrieve meal details.')
        return redirect('recommendations')
    
    is_saved = False
    if request.user.is_authenticated:
        is_saved = SavedMeal.objects.filter(user=request.user, meal_id=meal_id).exists()
    
    return render(request, 'nutrition/meal_detail.html', {
        'meal': meal,
        'is_saved': is_saved,
    })

@login_required
def save_meal(request, meal_id):
    if request.method == 'POST':
        meal = get_meal_details(meal_id)
        if meal:
            SavedMeal.objects.get_or_create(
                user=request.user,
                meal_id=meal_id,
                defaults={
                    'meal_name': meal.get('food_name', ''),
                    'restaurant': meal.get('brand_name', 'Unknown'),
                    'calories': meal.get('nf_calories', 0),
                    'protein': meal.get('nf_protein', 0),
                    'carbs': meal.get('nf_total_carbohydrate', 0),
                    'fat': meal.get('nf_total_fat', 0),
                }
            )
            messages.success(request, 'Meal saved to your favorites!')
        else:
            messages.error(request, 'Could not save meal.')
    
    return redirect('meal_detail', meal_id=meal_id)

@login_required
def saved_meals(request):
    meals = SavedMeal.objects.filter(user=request.user).order_by('-saved_at')
    return render(request, 'nutrition/saved_meals.html', {'meals': meals})