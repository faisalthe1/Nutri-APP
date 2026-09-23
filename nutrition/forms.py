import ast
import json

from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from .models import UserPreferences

TARGET_BOUNDS = {'calorie_limit': (1000, 5000), 'protein_target': (50, 300),
                 'carb_target': (50, 500), 'fat_target': (20, 200)}

class SignUpForm(UserCreationForm):
    email = forms.EmailField(max_length=254, required=True, help_text='Required. Inform a valid email address.')

    class Meta:
        model = User
        fields = ('username', 'email', 'password1', 'password2')

class PreferencesForm(forms.ModelForm):
    ALLERGY_CHOICES = [
        ('dairy', 'Dairy'),
        ('eggs', 'Eggs'),
        ('gluten', 'Gluten'),
        ('peanuts', 'Peanuts'),
        ('tree_nuts', 'Tree Nuts'),
        ('soy', 'Soy'),
        ('fish', 'Fish'),
        ('shellfish', 'Shellfish'),
    ]

    allergies = forms.MultipleChoiceField(
        choices=ALLERGY_CHOICES,
        widget=forms.CheckboxSelectMultiple,
        required=False
    )

    class Meta:
        model = UserPreferences
        fields = ['goal', 'calorie_limit', 'protein_target', 'carb_target', 'fat_target', 'allergies']
        widgets = {
            'goal': forms.RadioSelect,
            'calorie_limit': forms.NumberInput(attrs={
                'min': 1000,
                'max': 5000,
                'step': 1,
                'class': 'form-input'
            }),
            'protein_target': forms.NumberInput(attrs={
                'min': 50,
                'max': 300,
                'step': 1,
                'class': 'form-input'
            }),
            'carb_target': forms.NumberInput(attrs={
                'min': 50,
                'max': 500,
                'step': 1,
                'class': 'form-input'
            }),
            'fat_target': forms.NumberInput(attrs={
                'min': 20,
                'max': 200,
                'step': 1,
                'class': 'form-input'
            }),
        }
        labels = {
            'goal': 'Your Fitness Goal',
            'calorie_limit': 'Daily Calories (kcal)',
            'protein_target': 'Protein (grams)',
            'carb_target': 'Carbs (grams)',
            'fat_target': 'Fat (grams)',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Convert stored allergies string to list for initial data
        if self.instance and self.instance.pk and self.instance.allergies:
            try:
                saved = ast.literal_eval(self.instance.allergies)
                self.initial['allergies'] = saved if isinstance(saved, list) else []
            except (ValueError, SyntaxError):
                self.initial['allergies'] = []

    def clean(self):
        cleaned_data = super().clean()
        goal = cleaned_data.get('goal')
        calorie_limit = cleaned_data.get('calorie_limit')

        # Convert allergies list to string for storage
        if 'allergies' in cleaned_data:
            cleaned_data['allergies'] = json.dumps(cleaned_data['allergies'])

        # Enforce the same limits on the server for accounts and guests.
        for name, (minimum, maximum) in TARGET_BOUNDS.items():
            value = cleaned_data.get(name)
            if value is not None and not minimum <= value <= maximum:
                self.add_error(name, f'Enter a value between {minimum} and {maximum}.')

        return cleaned_data


class GuestPreferencesForm(forms.Form):
    GOAL_CHOICES = [
        ('bulking', 'Bulking'),
        ('cutting', 'Cutting'),
    ]

    ALLERGY_CHOICES = [
        ('dairy', 'Dairy'),
        ('eggs', 'Eggs'),
        ('gluten', 'Gluten'),
        ('peanuts', 'Peanuts'),
        ('tree_nuts', 'Tree Nuts'),
        ('soy', 'Soy'),
        ('fish', 'Fish'),
        ('shellfish', 'Shellfish'),
    ]

    goal = forms.ChoiceField(choices=GOAL_CHOICES, widget=forms.RadioSelect, initial='bulking', label='Your fitness goal')
    calorie_limit = forms.IntegerField(min_value=1000, max_value=5000, initial=2500, label='Daily calories (kcal)')
    protein_target = forms.IntegerField(min_value=50, max_value=300, initial=150, label='Protein (g)')
    carb_target = forms.IntegerField(min_value=50, max_value=500, initial=300, label='Carbs (g)')
    fat_target = forms.IntegerField(min_value=20, max_value=200, initial=70, label='Fat (g)')
    allergies = forms.MultipleChoiceField(
        choices=ALLERGY_CHOICES,
        widget=forms.CheckboxSelectMultiple,
        required=False
    )
