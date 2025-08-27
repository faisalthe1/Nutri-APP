from django.db import models
from django.contrib.auth.models import User



class UserPreferences(models.Model):
    GOAL_CHOICES = [
        ('bulking', 'Bulking'),
        ('cutting', 'Cutting'),
    ]
    
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    goal = models.CharField(max_length=10, choices=GOAL_CHOICES)
    calorie_limit = models.PositiveIntegerField()
    protein_target = models.PositiveIntegerField()
    carb_target = models.PositiveIntegerField()
    fat_target = models.PositiveIntegerField()
    allergies = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username}'s Preferences"



class SavedMeal(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    meal_id = models.CharField(max_length=100)
    meal_name = models.CharField(max_length=200)
    restaurant = models.CharField(max_length=200)
    calories = models.PositiveIntegerField()
    protein = models.PositiveIntegerField()
    carbs = models.PositiveIntegerField()
    fat = models.PositiveIntegerField()
    saved_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.meal_name} saved by {self.user.username}"

    class Meta:
        unique_together = ('user', 'meal_id')