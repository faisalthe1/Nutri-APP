"""Bounded, cached access to Nutritionix without credentials in source control."""
import hashlib
import json
import logging
import math

import requests
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)
API_URL = 'https://trackapi.nutritionix.com/v2/'


def _request(endpoint, params):
    if not settings.NUTRITIONIX_APP_ID or not settings.NUTRITIONIX_APP_KEY:
        logger.warning('Nutritionix credentials are not configured.')
        return None
    digest = hashlib.sha256(json.dumps(params, sort_keys=True).encode()).hexdigest()
    key = f'nutritionix:{endpoint}:{digest}'
    cached = cache.get(key)
    if cached is not None:
        return cached
    try:
        response = requests.get(
            API_URL + endpoint,
            headers={'x-app-id': settings.NUTRITIONIX_APP_ID,
                     'x-app-key': settings.NUTRITIONIX_APP_KEY,
                     'x-remote-user-id': '0'},
            params=params,
            timeout=settings.NUTRITIONIX_TIMEOUT,
        )
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            return None
        field = 'branded' if endpoint == 'search/instant' else 'foods'
        if not isinstance(data.get(field), list):
            return None
        cache.set(key, data, 300)
        return data
    except (requests.RequestException, ValueError):
        # Do not log response bodies or headers containing provider/account data.
        logger.warning('Nutritionix request failed for %s.', endpoint)
        return None


def _number(value):
    try:
        number = float(value)
        return max(0, number) if math.isfinite(number) else 0
    except (TypeError, ValueError, OverflowError):
        return 0


def search_fast_foods(query, goal=None, max_calories=None, min_protein=None):
    data = _request('search/instant', {'query': query, 'branded': True,
                                     'common': False, 'detailed': True})
    if data is None:
        return None
    foods = []
    for item in data['branded']:
        if not isinstance(item, dict) or not item.get('nix_item_id'):
            continue
        raw_nutrients = item.get('full_nutrients')
        nutrients = {n.get('attr_id'): _number(n.get('value'))
                     for n in (raw_nutrients if isinstance(raw_nutrients, list) else [])
                     if isinstance(n, dict)}
        calories = _number(item.get('nf_calories'))
        protein = nutrients.get(203, _number(item.get('nf_protein')))
        if goal == 'cutting' and max_calories and calories > max_calories:
            continue
        # Preserve the existing protein-density ranking; the target is daily,
        # so it should not be interpreted as a minimum for a single meal.
        if goal == 'bulking' and min_protein and (not calories or protein * 4 / calories < .15):
            continue
        foods.append({
            'food_name': item.get('food_name') or 'Restaurant meal',
            'brand_name': item.get('brand_name') or '',
            'nix_item_id': item['nix_item_id'],
            'serving_qty': item.get('serving_qty') or 1,
            'serving_unit': item.get('serving_unit') or 'serving',
            'nf_calories': calories, 'nf_protein': protein,
            'nf_total_carbohydrate': nutrients.get(205, 0),
            'nf_total_fat': nutrients.get(204, 0),
        })
    if goal == 'bulking':
        foods.sort(key=lambda meal: (-meal['nf_protein'], -meal['nf_calories']))
    elif goal == 'cutting':
        foods.sort(key=lambda meal: (meal['nf_calories'], -meal['nf_protein']))
    return foods[:20]


def get_meal_details(meal_id):
    data = _request('search/item', {'nix_item_id': meal_id})
    if not data or not data['foods'] or not isinstance(data['foods'][0], dict):
        return None
    meal = data['foods'][0].copy()
    if not meal.get('food_name'):
        return None
    meal['nix_item_id'] = meal_id
    for field in ('nf_calories', 'nf_protein', 'nf_total_carbohydrate', 'nf_total_fat'):
        meal[field] = _number(meal.get(field))
    return meal
