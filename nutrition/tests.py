from unittest.mock import patch

import requests
from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from .forms import GuestPreferencesForm, PreferencesForm
from .models import SavedMeal, UserPreferences
from .services import get_meal_details, search_fast_foods

PREFERENCES = {'goal': 'bulking', 'calorie_limit': 2500, 'protein_target': 150,
               'carb_target': 300, 'fat_target': 70, 'allergies': []}
MEAL = {'nix_item_id': 'example-meal', 'food_name': 'Grilled chicken bowl',
        'brand_name': 'Example Kitchen', 'nf_calories': 480, 'nf_protein': 32,
        'nf_total_carbohydrate': 48, 'nf_total_fat': 18,
        'serving_qty': 1, 'serving_unit': 'bowl'}


class PreferenceTests(SimpleTestCase):
    def test_server_rejects_out_of_range_targets_for_both_forms(self):
        for form_class in (GuestPreferencesForm, PreferencesForm):
            for field, value in [('calorie_limit', 999), ('protein_target', 999),
                                 ('carb_target', -1), ('fat_target', 201)]:
                with self.subTest(form=form_class.__name__, field=field):
                    form = form_class({**PREFERENCES, field: value})
                    self.assertFalse(form.is_valid())
                    self.assertIn(field, form.errors)

    def test_legacy_allergy_lists_still_load_without_evaluation(self):
        instance = UserPreferences(pk=1, allergies="['dairy', 'eggs']")
        self.assertEqual(PreferencesForm(instance=instance).initial['allergies'], ['dairy', 'eggs'])
        instance.allergies = "__import__('os').system('false')"
        self.assertEqual(PreferencesForm(instance=instance).initial['allergies'], [])

    def test_valid_preferences_serialize_as_json(self):
        form = PreferencesForm({**PREFERENCES, 'allergies': ['dairy']})
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['allergies'], '["dairy"]')


@override_settings(NUTRITIONIX_APP_ID='test-id', NUTRITIONIX_APP_KEY='test-key')
class NutritionServiceTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    @patch('nutrition.services.requests.get')
    def test_timeout_is_bounded_and_handled(self, get):
        get.side_effect = requests.Timeout()
        self.assertIsNone(search_fast_foods('chicken'))
        self.assertEqual(get.call_args.kwargs['timeout'], (3.05, 8))

    @patch('nutrition.services.requests.get')
    def test_bad_json_and_empty_details_are_handled(self, get):
        get.return_value.json.side_effect = ValueError('bad JSON')
        self.assertIsNone(get_meal_details('bad'))
        get.return_value.json.side_effect = None
        for payload in ({'foods': []}, {'foods': None}, {'foods': [{}]}, []):
            cache.clear()
            get.return_value.json.return_value = payload
            self.assertIsNone(get_meal_details('empty'))

    @patch('nutrition.services.requests.get')
    def test_search_is_cached_and_ranked_after_filtering(self, get):
        low = {**MEAL, 'nix_item_id': 'low', 'nf_calories': 350,
               'full_nutrients': [{'attr_id': 203, 'value': 20}]}
        high = {**MEAL, 'full_nutrients': [{'attr_id': 203, 'value': 40}]}
        get.return_value.json.return_value = {'branded': [low, high, None, {}]}
        self.assertEqual(search_fast_foods('chicken', 'bulking', min_protein=150)[0]['nf_protein'], 40)
        self.assertEqual(len(search_fast_foods('chicken', 'cutting', max_calories=400)), 1)
        get.assert_called_once()

    @patch('nutrition.services.requests.get')
    def test_http_failure_logs_status_without_credentials_or_body(self, get):
        response = requests.Response()
        response.status_code = 401
        response._content = b'private provider response'
        get.return_value.raise_for_status.side_effect = requests.HTTPError(response=response)
        with self.assertLogs('nutrition.services', level='WARNING') as logs:
            self.assertIsNone(search_fast_foods('chicken'))
        self.assertIn('HTTP 401', logs.output[0])
        self.assertNotIn('test-key', logs.output[0])
        self.assertNotIn('private provider response', logs.output[0])

    @patch('nutrition.services.requests.get')
    def test_missing_and_nonfinite_nutrients_do_not_crash(self, get):
        get.return_value.json.return_value = {'branded': [
            {**MEAL, 'nf_calories': None, 'full_nutrients': None},
            {**MEAL, 'nf_calories': 'NaN', 'full_nutrients': [{'attr_id': 203, 'value': 'bad'}]},
        ]}
        meals = search_fast_foods('chicken')
        self.assertEqual([m['nf_calories'] for m in meals], [0, 0])

    @override_settings(NUTRITIONIX_APP_KEY='')
    @patch('nutrition.services.requests.get')
    def test_missing_credentials_fail_gracefully_without_network(self, get):
        self.assertIsNone(search_fast_foods('chicken'))
        get.assert_not_called()


@override_settings(STORAGES={'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class AppFlowTests(TestCase):
    def guest(self):
        session = self.client.session
        session['guest_prefs'] = PREFERENCES
        session.save()

    def test_public_pages_render_and_health_is_independent(self):
        for name in ('index', 'guest_preferences', 'register', 'login', 'health'):
            with self.subTest(name=name):
                self.assertEqual(self.client.get(reverse(name)).status_code, 200)
        self.assertEqual(self.client.get(reverse('health')).json(), {'status': 'ok'})
        page = self.client.get(reverse('guest_preferences'))
        self.assertContains(page, 'Bulking')
        self.assertContains(page, 'Cutting')

    def test_guest_preferences_roundtrip(self):
        response = self.client.post(reverse('guest_preferences'), PREFERENCES)
        self.assertRedirects(response, reverse('recommendations'), fetch_redirect_response=False)
        self.assertEqual(self.client.session['guest_prefs']['protein_target'], 150)
        self.assertContains(self.client.get(reverse('guest_preferences')), 'value="150"')

    @patch('nutrition.views.search_fast_foods', return_value=[MEAL])
    def test_search_query_and_meal_links(self, search):
        self.guest()
        response = self.client.get(reverse('recommendations'), {'q': 'chicken'})
        self.assertContains(response, MEAL['food_name'])
        self.assertEqual(search.call_args.kwargs['query'], 'chicken')
        self.assertContains(response, reverse('meal_detail', args=['example-meal']))

    @patch('nutrition.views.search_fast_foods', return_value=None)
    def test_api_failure_has_distinct_empty_state(self, search):
        self.guest()
        self.assertContains(self.client.get(reverse('recommendations')), 'A quick pause in the kitchen.')

    @patch('nutrition.views.get_meal_details', return_value=MEAL)
    def test_guest_meal_details_receive_daily_targets(self, details):
        self.guest()
        response = self.client.get(reverse('meal_detail', args=['example-meal']))
        self.assertContains(response, '480 / 2500 kcal')
        self.assertContains(response, '32 / 150g')

    @patch('nutrition.views.get_meal_details', return_value=MEAL)
    def test_saved_meals_are_post_only_idempotent_and_user_scoped(self, details):
        user = User.objects.create_user('tester', password='test-password-42')
        other = User.objects.create_user('other')
        self.client.force_login(user)
        url = reverse('save_meal', args=['example-meal'])
        self.assertEqual(self.client.get(url).status_code, 405)
        self.client.post(url)
        self.client.post(url)
        self.assertEqual(SavedMeal.objects.filter(user=user).count(), 1)
        self.assertContains(self.client.get(reverse('saved_meals')), MEAL['food_name'])
        self.client.force_login(other)
        self.assertNotContains(self.client.get(reverse('saved_meals')), MEAL['food_name'])

    def test_registration_preferences_and_logout(self):
        response = self.client.post(reverse('register'), {
            'username': 'new-user', 'email': 'test@example.com',
            'password1': 'a-unique-test-pass-765', 'password2': 'a-unique-test-pass-765'})
        self.assertRedirects(response, reverse('set_preferences'))
        self.client.post(reverse('set_preferences'), PREFERENCES)
        self.assertEqual(UserPreferences.objects.get(user__username='new-user').goal, 'bulking')
        self.assertRedirects(self.client.post(reverse('logout')), reverse('index'))
