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
MEAL = {'meal_id': 'fs-123', 'food_name': 'Grilled chicken bowl',
        'brand_name': 'Example Kitchen', 'nf_calories': 480, 'nf_protein': 32,
        'nf_total_carbohydrate': 48, 'nf_total_fat': 18,
        'serving_description': '1 bowl'}


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


SEARCH_FOOD = {'food_id': '123', 'food_name': 'Chicken bowl', 'food_type': 'Brand',
               'brand_name': 'Example Kitchen',
               'food_description': 'Per 1 bowl - Calories: 480kcal | Fat: 18.00g | Carbs: 48.00g | Protein: 32.00g'}
SERVING = {'serving_id': '456', 'serving_description': '1 bowl', 'calories': '480',
           'protein': '32', 'carbohydrate': '48', 'fat': '18', 'sodium': '500'}


@override_settings(FATSECRET_CLIENT_ID='test-id', FATSECRET_CLIENT_SECRET='test-secret')
class NutritionServiceTests(SimpleTestCase):
    def setUp(self):
        cache.clear()
        self.post_patch = patch('nutrition.services.requests.post')
        self.post = self.post_patch.start()
        self.addCleanup(self.post_patch.stop)
        self.post.return_value.json.return_value = {'access_token': 'test-token', 'expires_in': 86400}
        self.get_patch = patch('nutrition.services.requests.get')
        self.get = self.get_patch.start()
        self.addCleanup(self.get_patch.stop)
        self.get.return_value.status_code = 200

    def test_tokens_are_reused_but_food_content_is_not_cached(self):
        self.get.return_value.json.return_value = {'foods': {'food': SEARCH_FOOD}}
        first = search_fast_foods('chicken')
        self.assertEqual(first[0]['nf_protein'], 32)
        self.assertEqual(first[0]['meal_id'], 'fs-123')
        self.assertEqual(first[0]['serving_description'], '1 bowl')
        search_fast_foods('chicken')
        self.post.assert_called_once()
        self.assertEqual(self.get.call_count, 2)
        self.assertEqual(self.post.call_args.kwargs['auth'], ('test-id', 'test-secret'))
        self.assertEqual(self.post.call_args.kwargs['data']['scope'], 'basic')

    def test_ranking_and_cutting_filters(self):
        low = {**SEARCH_FOOD, 'food_id': '124', 'food_description': 'Per 1 serving - Calories: 250kcal | Fat: 5g | Carbs: 20g | Protein: 20g'}
        self.get.return_value.json.return_value = {'foods': {'food': [low, SEARCH_FOOD, None, {}]}}
        self.assertEqual(search_fast_foods('chicken', 'bulking', min_protein=150)[0]['nf_protein'], 32)
        self.assertEqual(len(search_fast_foods('chicken', 'cutting', max_calories=300)), 1)

    def test_timeout_is_bounded_and_handled(self):
        self.get.side_effect = requests.Timeout()
        self.assertIsNone(search_fast_foods('chicken'))
        self.assertEqual(self.get.call_args.kwargs['timeout'], (3.05, 8))

    def test_bad_json_and_malformed_details(self):
        self.get.return_value.json.side_effect = ValueError('bad JSON')
        self.assertIsNone(get_meal_details('fs-123'))
        self.get.return_value.json.side_effect = None
        for payload in ({'food': None}, {'food': {}}, [], {'food': {**SEARCH_FOOD, 'servings': {'serving': []}}}):
            self.get.return_value.json.return_value = payload
            self.assertIsNone(get_meal_details('fs-123'))

    def test_empty_search_is_distinct_from_provider_error(self):
        self.get.return_value.json.return_value = {'foods': {'total_results': '0'}}
        self.assertEqual(search_fast_foods('nothing'), [])
        self.get.return_value.json.return_value = {'error': {'code': 21, 'message': 'private'}}
        with self.assertLogs('nutrition.services', level='WARNING') as logs:
            self.assertIsNone(search_fast_foods('chicken'))
        self.assertIn('code 21', logs.output[0])
        self.assertNotIn('private', logs.output[0])

    def test_expired_token_refreshes_once(self):
        self.get.return_value.json.side_effect = [{'error': {'code': 13}}, {'foods': {'food': SEARCH_FOOD}}]
        self.assertEqual(len(search_fast_foods('chicken')), 1)
        self.assertEqual(self.post.call_count, 2)
        self.get.return_value.json.side_effect = None
        self.get.return_value.json.return_value = {'error': {'code': 13}}
        self.get.reset_mock()
        self.assertIsNone(search_fast_foods('chicken'))
        self.assertEqual(self.get.call_count, 2)

    def test_http_failure_logs_no_credentials_or_body(self):
        response = requests.Response()
        response.status_code = 429
        response._content = b'private provider response'
        self.get.return_value.raise_for_status.side_effect = requests.HTTPError(response=response)
        with self.assertLogs('nutrition.services', level='WARNING') as logs:
            self.assertIsNone(search_fast_foods('chicken'))
        self.assertIn('HTTP 429', logs.output[0])
        for value in ('test-secret', 'test-token', 'private provider response'):
            self.assertNotIn(value, logs.output[0])

    def test_missing_and_nonfinite_nutrients_are_not_zero(self):
        self.get.return_value.json.return_value = {'foods': {'food': {**SEARCH_FOOD, 'food_description': 'Per 1 bowl - Calories: NaNkcal'}}}
        self.assertEqual(search_fast_foods('chicken'), [])
        self.get.return_value.json.return_value = {'food': {**SEARCH_FOOD, 'servings': {'serving': {**SERVING, 'calories': 'NaN'}}}}
        self.assertIsNone(get_meal_details('fs-123'))

    def test_detail_uses_real_brand_portion_and_nullable_micronutrients(self):
        self.get.return_value.json.return_value = {'food': {**SEARCH_FOOD, 'servings': {'serving': [
            {**SERVING, 'serving_id': '0', 'calories': '100'}, SERVING]}}}
        meal = get_meal_details('fs-123')
        self.assertEqual(meal['nf_calories'], 480)
        self.assertEqual(meal['nf_sodium'], 500)
        self.assertIsNone(meal['nf_sugars'])

    def test_generic_detail_matches_search_100g_serving(self):
        self.get.return_value.json.return_value = {'food': {**SEARCH_FOOD, 'food_type': 'Generic', 'servings': {'serving': [
            SERVING, {**SERVING, 'metric_serving_amount': '100', 'metric_serving_unit': 'g', 'calories': '100', 'serving_description': '100 g'}]}}}
        self.assertEqual(get_meal_details('fs-123')['nf_calories'], 100)

    def test_legacy_and_invalid_ids_never_reach_provider(self):
        for meal_id in ('old-nutritionix-id', 'fs-../bad', '123'):
            self.assertIsNone(get_meal_details(meal_id))
        self.get.assert_not_called()
        self.post.assert_not_called()

    @override_settings(FATSECRET_CLIENT_SECRET='')
    def test_missing_credentials_do_not_call_network(self):
        self.assertIsNone(search_fast_foods('chicken'))
        self.get.assert_not_called()
        self.post.assert_not_called()


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
        self.assertContains(response, reverse('meal_detail', args=['fs-123']))

    @patch('nutrition.views.search_fast_foods', return_value=None)
    def test_api_failure_has_distinct_empty_state(self, search):
        self.guest()
        self.assertContains(self.client.get(reverse('recommendations')), 'A quick pause in the kitchen.')

    @patch('nutrition.views.get_meal_details', return_value=MEAL)
    def test_guest_meal_details_receive_daily_targets(self, details):
        self.guest()
        response = self.client.get(reverse('meal_detail', args=['fs-123']))
        self.assertContains(response, '480 / 2500 kcal')
        self.assertContains(response, '32 / 150g')

    @patch('nutrition.views.get_meal_details', return_value=MEAL)
    def test_saved_meals_are_post_only_idempotent_and_user_scoped(self, details):
        user = User.objects.create_user('tester', password='test-password-42')
        other = User.objects.create_user('other')
        self.client.force_login(user)
        url = reverse('save_meal', args=['fs-123'])
        self.assertEqual(self.client.get(url).status_code, 405)
        self.client.post(url)
        self.client.post(url)
        self.assertEqual(SavedMeal.objects.filter(user=user).count(), 1)
        saved = SavedMeal.objects.get(user=user)
        self.assertEqual(saved.meal_name, '')
        self.assertEqual(saved.calories, 0)
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

    @patch('nutrition.views.get_meal_details', return_value=None)
    def test_saved_provider_failure_retains_favorite_without_fake_nutrition(self, details):
        user = User.objects.create_user('favorite-user')
        self.client.force_login(user)
        SavedMeal.objects.create(user=user, meal_id='fs-123', meal_name='', restaurant='', calories=0, protein=0, carbs=0, fat=0)
        response = self.client.get(reverse('saved_meals'))
        self.assertContains(response, 'Your favorite is still saved')
        self.assertNotContains(response, '>0<span>kcal')
        self.assertIn('no-store', response.headers['Cache-Control'])

    def test_legacy_saved_snapshot_is_only_visible_to_owner(self):
        user = User.objects.create_user('legacy-owner')
        SavedMeal.objects.create(user=user, meal_id='legacy-id', meal_name='Legacy bowl', restaurant='Old kitchen', calories=450, protein=30, carbs=40, fat=10)
        self.client.force_login(user)
        self.assertContains(self.client.get(reverse('meal_detail', args=['legacy-id'])), 'Legacy bowl')
        self.client.logout()
        self.assertEqual(self.client.get(reverse('meal_detail', args=['legacy-id'])).status_code, 302)
