import json
import requests
import os

def send_notification(title, message, url="https://joseprico.github.io/"):
    """Envia notificació via OneSignal"""
    app_id = os.environ.get('ONESIGNAL_APP_ID', '')
    api_key = os.environ.get('ONESIGNAL_API_KEY', '')
    
    if not app_id or not api_key:
        print("⚠️ OneSignal credentials no configurades")
        return False
    
    headers = {
        "Authorization": f"Basic {api_key}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "app_id": app_id,
        "included_segments": ["Subscribed Users"],
        "headings": {"ca": title, "es": title, "en": title},
        "contents": {"ca": message, "es": message, "en": message},
        "url": url
    }
    
    try:
        response = requests.post(
            "https://onesignal.com/api/v1/notifications",
            headers=headers,
            json=payload,
            timeout=10
        )
        if response.status_code == 200:
            print(f"✅ Notificació enviada: {message}")
            return True
        else:
            print(f"❌ Error enviant notificació ({response.status_code}): {response.text}")
            return False
    except Exception as e:
        print(f"❌ Error de connexió: {e}")
        return False

def check_team_changes(team_name, old_file, new_file):
    """Comprova canvis per un equip específic"""
    
    print(f"\n{'='*60}")
    print(f"🔍 Comprovant canvis per {team_name}...")
    print(f"{'='*60}")
    
    try:
        # Carregar dades antigues
        try:
            with open(old_file, 'r', encoding='utf-8') as f:
                old_data = json.load(f)
            print(f"✅ Dades antigues carregades: {old_file}")
        except FileNotFoundError:
            print(f"⚠️ No hi ha dades antigues per {team_name} (primera execució)")
            return
        except Exception as e:
            print(f"⚠️ Error llegint dades antigues: {e}")
            return
        
        # Carregar dades noves
        try:
            with open(new_file, 'r', encoding='utf-8') as f:
                new_data = json.load(f)
            print(f"✅ Dades noves carregades: {new_file}")
        except Exception as e:
            print(f"❌ Error llegint dades noves: {e}")
            return
        
        notifications_sent = 0
        
        # 1. COMPROVAR NOUS RESULTATS
        print("\n📊 Comprovant nous resultats...")
        old_results = old_data.get('last_results', [])
        new_results = new_data.get('last_results', [])
        
        print(f"   Resultats antics: {len(old_results)}")
        print(f"   Resultats nous: {len(new_results)}")
        
        if len(new_results) > len(old_results):
            # Hi ha nous resultats!
            num_new = len(new_results) - len(old_results)
            print(f"   🎉 {num_new} nou(s) resultat(s) detectat(s)!")
            
            # Processar cada nou resultat
            for i in range(num_new):
                latest = new_results[i]
                team1 = latest.get('team1', '?')
                team2 = latest.get('team2', '?')
                score = latest.get('score', '?-?')
                jornada = latest.get('jornada', '?')
                
                # Determinar si és CN Terrassa i resultat
                is_cnt = 'TERRASSA' in team1.upper()
                our_score = latest.get('score_team1', 0) if is_cnt else latest.get('score_team2', 0)
                their_score = latest.get('score_team2', 0) if is_cnt else latest.get('score_team1', 0)
                
                if our_score > their_score:
                    emoji = "🎉"
                    result = "Victòria!"
                elif our_score < their_score:
                    emoji = "💪"
                    result = "Derrota"
                else:
                    emoji = "🤝"
                    result = "Empat"
                
                message = f"{emoji} J{jornada}: {team1} {score} {team2}"
                title = f"CN Terrassa {team_name} - {result}"
                
                print(f"   📤 Enviant: {message}")
                if send_notification(title, message):
                    notifications_sent += 1
        else:
            print("   ℹ️ No hi ha nous resultats")
        
        # 2. COMPROVAR CANVIS DE DATA/HORA
        print("\n📅 Comprovant canvis de calendari...")
        old_upcoming = {m['match_id']: m for m in old_data.get('upcoming_matches', [])}
        new_upcoming = {m['match_id']: m for m in new_data.get('upcoming_matches', [])}
        
        changes_detected = 0
        for match_id, new_match in new_upcoming.items():
            if match_id in old_upcoming:
                old_match = old_upcoming[match_id]
                
                # Comprovar si ha canviat la data/hora
                if old_match.get('date_time') != new_match.get('date_time'):
                    changes_detected += 1
                    team1 = new_match.get('team1', '?')
                    team2 = new_match.get('team2', '?')
                    new_date = new_match.get('date', '?')
                    new_time = new_match.get('time', '?')
                    old_date = old_match.get('date', '?')
                    jornada = new_match.get('jornada', '?')
                    
                    message = f"📅 J{jornada}: {team1} vs {team2}\nNova data: {new_date} {new_time}\n(abans: {old_date})"
                    title = f"CN Terrassa {team_name} - Partit ajornat"
                    
                    print(f"   🔄 Canvi detectat: {team1} vs {team2}")
                    print(f"      Antiga: {old_match.get('date_time')}")
                    print(f"      Nova: {new_match.get('date_time')}")
                    print(f"   📤 Enviant notificació...")
                    
                    if send_notification(title, message):
                        notifications_sent += 1
        
        if changes_detected == 0:
            print("   ℹ️ No hi ha canvis de calendari")
        else:
            print(f"   ✅ {changes_detected} canvi(s) de calendari detectat(s)")
        
        # 3. RESUM
        print(f"\n{'='*60}")
        print(f"📊 RESUM {team_name}:")
        print(f"   - Notificacions enviades: {notifications_sent}")
        print(f"{'='*60}")
        
    except Exception as e:
        print(f"❌ Error processant {team_name}: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    print("""
╔══════════════════════════════════════════════════════════════╗
║           🔔 SISTEMA DE NOTIFICACIONS ONESIGNAL              ║
║                    CN Terrassa Waterpolo                     ║
╚══════════════════════════════════════════════════════════════╝
""")
    
    total_notifications = 0
    
    # Comprovar Cadet
    check_team_changes("CADET", "old_actawp_cadet.json", "actawp_cadet_data.json")
    
    # Comprovar Juvenil
    check_team_changes("JUVENIL", "old_actawp_juvenil.json", "actawp_juvenil_data.json")
    
    print(f"\n✅ Procés completat!")