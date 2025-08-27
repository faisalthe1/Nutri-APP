import requests
from django.conf import settings


NUTRITIONIX_APP_ID = 'e0e5e05b'
NUTRITIONIX_APP_KEY = '91e677d88cf7c382b4525c36e71e0c2e'
NUTRITIONIX_API_URL = 'https://trackapi.nutritionix.com/v2/'

def search_fast_foods(query, goal=None, max_calories=None, min_protein=None):
    headers = {
        'x-app-id': NUTRITIONIX_APP_ID,
        'x-app-key': NUTRITIONIX_APP_KEY,
        'x-remote-user-id': '0',
    }
    
    params = {
        'query': query,
        'branded': True,
        'common': False,
        'detailed': True,
    }
    
    try:
        response = requests.get(
            f"{NUTRITIONIX_API_URL}search/instant",
            headers=headers,
            params=params
        )
        response.raise_for_status()
        data = response.json()
        
        foods = []
        for item in data.get('branded', [])[:20]:  # Limit to 20 results
            # Extract nutrition data properly
            protein = next(
                (nutrient['value'] for nutrient in item.get('full_nutrients', []) 
                 if nutrient.get('attr_id') == 203),
                0
            )
            
            nutrition_data = {
                'nf_calories': item.get('nf_calories', 0),
                'nf_protein': protein,
                'nf_total_carbohydrate': next(
                    (n['value'] for n in item.get('full_nutrients', [])
                     if n.get('attr_id') == 205), 0),
                'nf_total_fat': next(
                    (n['value'] for n in item.get('full_nutrients', [])
                     if n.get('attr_id') == 204), 0),
            }
            
            # Apply smarter filtering based on goals
            if goal == 'cutting' and max_calories:
                if nutrition_data['nf_calories'] > max_calories:
                    continue
                    
            if goal == 'bulking' and min_protein:
                protein_ratio = (nutrition_data['nf_protein'] * 4) / nutrition_data['nf_calories'] if nutrition_data['nf_calories'] > 0 else 0
                if protein_ratio < 0.15: 
                    continue
                
            foods.append({
                'food_name': item.get('food_name', ''),
                'brand_name': item.get('brand_name', ''),
                'nix_item_id': item.get('nix_item_id', ''),
                'photo': item.get('photo', {}),
                'serving_qty': item.get('serving_qty', 1),
                'serving_unit': item.get('serving_unit', 'serving'),
                **nutrition_data
            })
        
        # Sort based on goal with better prioritization
        if goal == 'bulking':
            foods = sorted(
                foods,
                key=lambda x: (
                    -x.get('nf_protein', 0),  # Highest protein first
                    -x.get('nf_calories', 0)  # Then highest calories
                )
            )
        elif goal == 'cutting':
            foods = sorted(
                foods,
                key=lambda x: (
                    x.get('nf_calories', 0),  # Lowest calories first
                    -x.get('nf_protein', 0)   # Then highest protein
                )
            )
        
        return foods
    
    except requests.exceptions.RequestException as e:
        print(f"Error fetching data from Nutritionix: {e}")
        return None

def get_meal_details(meal_id):
    headers = {
        'x-app-id': NUTRITIONIX_APP_ID,
        'x-app-key': NUTRITIONIX_APP_KEY,
    }
    
    try:
        response = requests.get(
            f"{NUTRITIONIX_API_URL}search/item",
            params={'nix_item_id': meal_id},
            headers=headers
        )
        response.raise_for_status()
        data = response.json()
        return data.get('foods', [{}])[0]
    except requests.exceptions.HTTPError as http_err:
        print(f"HTTP error fetching meal details: {http_err}")
        print(f"Response content: {response.text}") 
    except requests.exceptions.RequestException as e:
        print(f"Error fetching meal details: {e}")
    return None