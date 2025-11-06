import json
import requests
import os

# Carregar dades antigues i noves
with open('old_data.json', 'r') as f:
    old_data = json.load(f)
    
with open('actawp_cadet_data.json', 'r') as f:
    new_data = json.load(f)

# Comparar resultats
old_results = old_data.get('last_results', [])
new_results = new_data.get('last_results', [])

if len(new_results) > len(old_results):
    # Hi ha un nou resultat!
    latest_result = new_results[0]
    score = latest_result.get('score', '?-?')
    team1 = latest_result.get('team1', '?')
    team2 = latest_result.get('team2', '?')
    
    message = f"⚽ Nou resultat: {team1} {score} {team2}"
    
    # Enviar notificació via OneSignal
    headers = {
        "Authorization": f"Basic {os.environ['ONESIGNAL_API_KEY']}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "app_id": os.environ['ONESIGNAL_APP_ID'],
        "included_segments": ["Subscribed Users"],
        "headings": {"en": "CN Terrassa - Nou resultat!"},
        "contents": {"en": message}
    }
    
    requests.post(
        "https://onesignal.com/api/v1/notifications",
        headers=headers,
        json=payload
    )
    
    print(f"✅ Notificació enviada: {message}")

# Comparar canvis de data als pròxims partits
# (similar al de dalt)
