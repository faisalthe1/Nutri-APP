"""FatSecret Basic API adapter. Cache OAuth tokens, never food content."""
import hashlib
import logging
import math
import re
import threading

import requests
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)
API_URL = 'https://platform.fatsecret.com/rest/'
TOKEN_URL = 'https://oauth.fatsecret.com/connect/token'
_token_lock = threading.Lock()


def _number(value):
    try:
        number = float(value)
        return number if math.isfinite(number) and number >= 0 else None
    except (TypeError, ValueError, OverflowError):
        return None


def _token_key():
    credentials = f'{settings.FATSECRET_CLIENT_ID}:{settings.FATSECRET_CLIENT_SECRET}'
    return 'fatsecret:token:' + hashlib.sha256(credentials.encode()).hexdigest()


def _log_failure(endpoint, error):
    response = getattr(error, 'response', None)
    status = getattr(response, 'status_code', None)
    # Never log response bodies, URLs, tokens or exception messages.
    logger.warning('FatSecret request failed for %s: %s (HTTP %s).',
                   endpoint, type(error).__name__, status or 'unavailable')


def _access_token():
    if not settings.FATSECRET_CLIENT_ID or not settings.FATSECRET_CLIENT_SECRET:
        logger.warning('FatSecret credentials are not configured.')
        return None
    key = _token_key()
    with _token_lock:
        token = cache.get(key)
        if token:
            return token
        try:
            response = requests.post(
                TOKEN_URL,
                auth=(settings.FATSECRET_CLIENT_ID, settings.FATSECRET_CLIENT_SECRET),
                data={'grant_type': 'client_credentials', 'scope': 'basic'},
                timeout=settings.FATSECRET_TIMEOUT,
            )
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, dict):
                return None
            token, expiry = data.get('access_token'), _number(data.get('expires_in'))
            if not isinstance(token, str) or not token or not expiry:
                return None
            cache.set(key, token, max(1, min(int(expiry), 86400) - 60))
            return token
        except (requests.RequestException, ValueError) as error:
            _log_failure('oauth', error)
            return None


def _request(endpoint, params):
    for attempt in range(2):
        token = _access_token()
        if not token:
            return None
        try:
            response = requests.get(
                API_URL + endpoint, headers={'Authorization': f'Bearer {token}'},
                params={**params, 'format': 'json'}, timeout=settings.FATSECRET_TIMEOUT,
            )
            if response.status_code == 401 and attempt == 0:
                cache.delete(_token_key())
                continue
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, dict):
                return None
            if 'error' in data:
                error = data['error']
                code = str(error.get('code', '')) if isinstance(error, dict) else ''
                if code == '13' and attempt == 0:
                    cache.delete(_token_key())
                    continue
                logger.warning('FatSecret API error for %s (code %s).',
                               endpoint, code if code.isdigit() else 'unknown')
                return None
            return data
        except (requests.RequestException, ValueError) as error:
            _log_failure(endpoint, error)
            return None
    return None


def _items(value):
    if isinstance(value, dict):
        return [value]
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _base_meal(item):
    food_id = str(item.get('food_id', ''))
    if not re.fullmatch(r'[0-9]{1,20}', food_id) or not item.get('food_name'):
        return None
    return {'meal_id': f'fs-{food_id}', 'food_name': item['food_name'],
            'brand_name': item.get('brand_name') or 'Generic food'}


def search_fast_foods(query, goal=None, max_calories=None, min_protein=None):
    data = _request('foods/search/v1', {'search_expression': query, 'max_results': 50})
    if data is None or not isinstance(data.get('foods'), dict):
        return None
    foods = []
    for item in _items(data['foods'].get('food')):
        meal = _base_meal(item)
        description = item.get('food_description')
        if not meal or not isinstance(description, str):
            continue
        serving, separator, nutrients = description.removeprefix('Per ').partition(' - ')
        if not separator or not serving:
            continue
        # Basic search supplies nutrition as a description, not structured fields.
        values = {}
        for label, unit, field in [('Calories', 'kcal', 'nf_calories'),
                                   ('Protein', 'g', 'nf_protein'),
                                   ('Carbs', 'g', 'nf_total_carbohydrate'),
                                   ('Fat', 'g', 'nf_total_fat')]:
            match = re.search(rf'\b{label}:\s*([0-9]+(?:\.[0-9]+)?)\s*{unit}\b', nutrients)
            values[field] = _number(match.group(1)) if match else None
        if any(value is None for value in values.values()):
            continue
        calories, protein = values['nf_calories'], values['nf_protein']
        if goal == 'cutting' and max_calories and calories > max_calories:
            continue
        if goal == 'bulking' and min_protein and (not calories or protein * 4 / calories < .15):
            continue
        foods.append({**meal, **values, 'serving_description': serving})
    if goal == 'bulking':
        foods.sort(key=lambda meal: (-meal['nf_protein'], -meal['nf_calories']))
    elif goal == 'cutting':
        foods.sort(key=lambda meal: (meal['nf_calories'], -meal['nf_protein']))
    return foods[:20]


def get_meal_details(meal_id):
    # Keep legacy Nutritionix identifiers separate from FatSecret numeric IDs.
    if not re.fullmatch(r'fs-[0-9]{1,20}', meal_id):
        return None
    data = _request('food/v5', {'food_id': meal_id[3:]})
    item = data.get('food') if data else None
    if not isinstance(item, dict):
        return None
    meal = _base_meal(item)
    container = item.get('servings')
    servings = _items(container.get('serving')) if isinstance(container, dict) else []
    if not meal or meal['meal_id'] != meal_id or not servings:
        return None
    # Match Basic search: generic foods use 100g; brands use their real portion,
    # not v5's additional derived servings (which have serving_id=0).
    if item.get('food_type') == 'Generic':
        serving = next((s for s in servings if _number(s.get('metric_serving_amount')) == 100
                        and s.get('metric_serving_unit') == 'g'), servings[0])
    else:
        serving = next((s for s in servings if str(s.get('serving_id', '0')) != '0'), servings[0])
    meal['serving_description'] = serving.get('serving_description') or '1 serving'
    for source, field in [('calories', 'nf_calories'), ('protein', 'nf_protein'),
                          ('carbohydrate', 'nf_total_carbohydrate'), ('fat', 'nf_total_fat'),
                          ('sodium', 'nf_sodium'), ('fiber', 'nf_dietary_fiber'), ('sugar', 'nf_sugars')]:
        meal[field] = _number(serving.get(source))
    if any(meal[field] is None for field in ('nf_calories', 'nf_protein', 'nf_total_carbohydrate', 'nf_total_fat')):
        return None
    return meal
