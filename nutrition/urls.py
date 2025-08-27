from django.urls import path
from django.contrib.auth.views import LogoutView
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('register/', views.register, name='register'),
    path('preferences/', views.set_preferences, name='set_preferences'),
    path('guest-preferences/', views.guest_preferences, name='guest_preferences'),
    path('recommendations/', views.recommendations, name='recommendations'),
    path('meal/<str:meal_id>/', views.meal_detail, name='meal_detail'),
    path('save-meal/<str:meal_id>/', views.save_meal, name='save_meal'),
    path('saved-meals/', views.saved_meals, name='saved_meals'),
    path('accounts/logout/', LogoutView.as_view(), name='logout'),
]