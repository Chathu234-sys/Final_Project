import json

# Load polish data from JSON
with open('nail_polish_data.json', 'r') as f:
    POLISH_DATA = json.load(f)

# ─── Filtering Helper ─────────────────────────────────
def simple_match(user_input):
    """
    user_input = {
        'age': 25,
        'skin_tone': 'fair',
        'finish_type': 'glossy',
        'occasion': 'party',
        'outfit_color': 'red'
    }
    """
    matches = []
    for polish in POLISH_DATA:
        if (user_input['finish_type'].lower() in polish['name'].lower() or
            user_input['skin_tone'].lower() in polish.get('tags', []) or
            user_input['occasion'].lower() in polish.get('tags', [])):
            matches.append(polish)

    # fallback if too few results
    if len(matches) < 3:
        matches = POLISH_DATA[:3]
    return matches[:3]

# ─── Hybrid Model + Rules Example (optional) ─────────
def hybrid_recommendation(user_input, model_top_ids=None):
    """Combine AI + fallback logic for robustness"""
    if model_top_ids:
        model_based = [p for p in POLISH_DATA if p.get('id') in model_top_ids]
        return model_based[:3] if model_based else simple_match(user_input)
    else:
        return simple_match(user_input)
