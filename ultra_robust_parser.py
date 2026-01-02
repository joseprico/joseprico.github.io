"""
Parser ACTAWP v5.7 - AMB FORMA DELS RIVALS
Estructura correcta segons captures:
- Pròxims: [Equip1] [Data/Hora/Lloc] [Equip2]
- Resultats: [Equip1] [MARCADOR] [Equip2]
- NOVITAT: Extreu logos dels equips en tots els partits i classificació
- NOVITAT v5.5: Afegeix número de jornada basat en l'ordre d'aparició
- NOVITAT v5.6: Sistema de correccions manuals per jornades ajornades
- NOVITAT v5.7: Obté els últims resultats de cada equip de la classificació
"""

import requests
import json
import os
from bs4 import BeautifulSoup
import re
from datetime import datetime

class ActawpParserV53:
    
    def __init__(self):
        self.session = requests.Session()
        self.jornada_corrections = self.load_jornada_corrections()
    
    def load_jornada_corrections(self):
        """Carrega correccions manuals de jornades"""
        try:
            corrections_file = 'jornades_correccions.json'
            if os.path.exists(corrections_file):
                with open(corrections_file, 'r', encoding='utf-8') as f:
                    corrections = json.load(f)
                    print(f"✅ Correccions de jornades carregades: {corrections_file}")
                    return corrections
        except Exception as e:
            print(f"⚠️ No s'han pogut carregar correccions: {e}")
        return {}
    
    def get_csrf_token(self, team_id, language='es'):
        """Obté el token CSRF"""
        url = f"https://actawp.natacio.cat/{language}/team/{team_id}"
        response = self.session.get(url)
        
        match = re.search(r'csrf_token["\']?\s*[:=]\s*["\']([^"\']+)["\']', response.text)
        if match:
            return match.group(1)
        
        soup = BeautifulSoup(response.text, 'html.parser')
        csrf_input = soup.find('input', {'name': 'csrf_token'})
        if csrf_input:
            return csrf_input.get('value')
        
        return None
    
    def get_tab_content(self, team_id, tab_name, language='es'):
        """Obté el contingut d'una pestanya"""
        csrf_token = self.get_csrf_token(team_id, language)
        
        if not csrf_token:
            return None
        
        url = f"https://actawp.natacio.cat/{language}/ajax/team/{team_id}/change-tab"
        
        data = {
            'csrf_token': csrf_token,
            'tab': tab_name
        }
        
        headers = {
            'accept': '*/*',
            'content-type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'x-requested-with': 'XMLHttpRequest',
            'referer': f'https://actawp.natacio.cat/{language}/team/{team_id}'
        }
        
        response = self.session.post(url, data=data, headers=headers)
        
        if response.status_code == 200:
            return response.json()
        else:
            return None
    
    def extract_header_text(self, th):
        """Extreu el text del header"""
        candidates = []
        
        title = th.get('title', '').strip()
        if title:
            candidates.append(('title', title))
        
        span = th.find('span')
        if span:
            span_title = span.get('title', '').strip()
            if span_title:
                candidates.append(('span_title', span_title))
            
            span_text = span.get_text(strip=True)
            if span_text:
                candidates.append(('span_text', span_text))
        
        th_text = th.get_text(strip=True)
        if th_text:
            candidates.append(('th_text', th_text))
        
        data_title = th.get('data-original-title', '').strip()
        if data_title:
            candidates.append(('data_title', data_title))
        
        priority = ['title', 'span_title', 'data_title', 'span_text', 'th_text']
        
        for method in priority:
            for candidate_method, candidate_text in candidates:
                if candidate_method == method and candidate_text:
                    return candidate_text
        
        if candidates:
            return candidates[0][1]
        
        return ''
    
    def clean_player_name(self, name):
        """Neteja el nom del jugador eliminant Ver/Veure"""
        if not name:
            return name
        
        name = re.sub(r'^Veure', '', name, flags=re.IGNORECASE)
        name = re.sub(r'^Ver', '', name, flags=re.IGNORECASE)
        
        return name.strip()
    
    def normalize_field_name(self, field_name):
        """Normalitza nom de camp al format curt esperat per l'index.html"""
        field_mapping = {
            'Nom': 'Nombre',
            'Partits jugats': 'PJ',
            'Total goals': 'GT',
            'Gols': 'G',
            'Gols penal': 'GP',
            'Gols en tanda de penals': 'G5P',
            'Targetes grogues': 'TA',
            'Targetes vermelles': 'TR',
            'Expulsions per 20 segons': 'EX',
            'Expulsions definitives, amb substitució disciplinària': 'ED',
            'Expulsions definitives per brutalitat, amb substitució als 4 minuts': 'EB',
            'Expulsions definitives, amb substitució no disciplinària': 'EN',
            'Expulsions i penal': 'EP',
            'Faltes per penal': 'P',
            'Penals fallats': 'PF',
            'Altres': 'O',
            'Temps morts': 'TM',
            'Joc net': 'JL',
            'Vinculat': 'Vinculado',
            'Nombre': 'Nombre',
            'Partidos jugados': 'PJ',
            'Goles totales': 'GT',
            'Goles': 'G',
            'Goles de penalti': 'GP',
            'Goles en tanda de penaltis': 'G5P',
            'Tarjetas amarillas': 'TA',
            'Tarjetas rojas': 'TR',
            'Expulsiones por 20 segundos': 'EX',
            'Expulsiones definitivas, con sustitución disciplinaria': 'ED',
            'Expulsiones definitivas por brutalidad, con sustitución a los 4 minutos': 'EB',
            'Expulsiones definitivas, con sustitución no disciplinaria': 'EN',
            'Expulsiones y penalti': 'EP',
            'Faltas por penalti': 'P',
            'Penaltis fallados': 'PF',
            'Otros': 'O',
            'Tiempos muertos': 'TM',
            'Juego limpio': 'JL',
            'Vinculado': 'Vinculado',
            'MVP': 'MVP'
        }
        
        return field_mapping.get(field_name, field_name)
    
    def parse_players(self, html_content):
        """Parser de jugadors amb normalització automàtica"""
        soup = BeautifulSoup(html_content, 'html.parser')
        players = []
        
        table = soup.find('table')
        if not table:
            return players
        
        headers = []
        thead = table.find('thead')
        if thead:
            for th in thead.find_all('th'):
                header_text = self.extract_header_text(th)
                headers.append(header_text)
        
        if not headers:
            return players
        
        tbody = table.find('tbody')
        if not tbody:
            return players
        
        rows = tbody.find_all('tr')
        
        for row in rows:
            cells = row.find_all('td')
            
            if len(cells) < 2:
                continue
            
            player_data = {}
            
            for i, cell in enumerate(cells):
                if i >= len(headers):
                    break
                
                header = headers[i]
                if not header:
                    continue
                
                normalized_field = self.normalize_field_name(header)
                value = cell.get_text(strip=True)
                value = re.sub(r'\s+', ' ', value)
                
                if normalized_field == 'Nombre' and value:
                    value = self.clean_player_name(value)
                
                if value and value not in ['', '-', '—', 'N/A']:
                    try:
                        if value.isdigit():
                            value = int(value)
                    except:
                        pass
                    player_data[normalized_field] = value
            
            if player_data:
                players.append(player_data)
        
        return players
    
    def parse_upcoming_matches(self, html_content):
        """Parser de pròxims partits amb jornada"""
        soup = BeautifulSoup(html_content, 'html.parser')
        matches = []
        
        rows = soup.find_all('tr')
        jornada_counter = 1
        
        for row in rows:
            try:
                cols = row.find_all('td')
                if len(cols) < 3:
                    continue
                
                # Buscar logos
                team1_logo = ''
                team2_logo = ''
                
                img1 = cols[0].find('img')
                if img1 and img1.get('src'):
                    team1_logo = img1['src']
                
                img2 = cols[-1].find('img')
                if img2 and img2.get('src'):
                    team2_logo = img2['src']
                
                team1 = cols[0].get_text(strip=True)
                team2 = cols[-1].get_text(strip=True)
                
                # Info central
                middle_text = ''
                for col in cols[1:-1]:
                    middle_text += col.get_text(separator=' ', strip=True) + ' '
                middle_text = middle_text.strip()
                
                # Extreure data/hora
                date_match = re.search(r'(\d{2}/\d{2}/\d{4})\s+(\d{2}:\d{2})', middle_text)
                
                if team1 and team2:
                    match_data = {
                        'team1': team1,
                        'team2': team2,
                        'team1_logo': team1_logo,
                        'team2_logo': team2_logo,
                        'date_time': middle_text,
                        'jornada': jornada_counter
                    }
                    
                    if date_match:
                        match_data['date'] = date_match.group(1)
                        match_data['time'] = date_match.group(2)
                    
                    matches.append(match_data)
                    jornada_counter += 1
                    
            except Exception as e:
                continue
        
        return matches
    
    def parse_last_results(self, html_content):
        """Parser d'últims resultats amb jornada"""
        soup = BeautifulSoup(html_content, 'html.parser')
        results = []
        
        rows = soup.find_all('tr')
        jornada_counter = 1
        
        for row in rows:
            try:
                cols = row.find_all('td')
                if len(cols) < 3:
                    continue
                
                # Buscar logos
                team1_logo = ''
                team2_logo = ''
                
                img1 = cols[0].find('img')
                if img1 and img1.get('src'):
                    team1_logo = img1['src']
                
                img2 = cols[-1].find('img')
                if img2 and img2.get('src'):
                    team2_logo = img2['src']
                
                team1 = cols[0].get_text(strip=True)
                team2 = cols[-1].get_text(strip=True)
                
                # Buscar marcador
                score = ''
                date = ''
                for col in cols[1:-1]:
                    col_text = col.get_text(strip=True)
                    
                    score_match = re.search(r'(\d+)\s*[-–]\s*(\d+)', col_text)
                    if score_match:
                        score = f"{score_match.group(1)}-{score_match.group(2)}"
                    
                    date_match = re.search(r'(\d{2}/\d{2}/\d{4})', col_text)
                    if date_match:
                        date = date_match.group(1)
                
                if team1 and team2 and score:
                    results.append({
                        'team1': team1,
                        'team2': team2,
                        'team1_logo': team1_logo,
                        'team2_logo': team2_logo,
                        'score': score,
                        'date': date,
                        'jornada': jornada_counter
                    })
                    jornada_counter += 1
                    
            except Exception as e:
                continue
        
        return results
    
    def parse_ranking(self, ranking_url):
        """Parser de classificació - ara també extreu l'ID de cada equip"""
        try:
            print(f"  📊 Obtenint classificació de: {ranking_url}")
            response = self.session.get(ranking_url)
            
            if response.status_code != 200:
                print(f"  ❌ Error HTTP: {response.status_code}")
                return []
            
            soup = BeautifulSoup(response.text, 'html.parser')
            table = soup.find('table')
            
            if not table:
                print("  ❌ No s'ha trobat taula de classificació")
                return []
            
            tbody = table.find('tbody')
            if not tbody:
                print("  ❌ No s'ha trobat tbody")
                return []
            
            rows = tbody.find_all('tr')
            ranking = []
            
            for idx, row in enumerate(rows, 1):
                try:
                    cols = row.find_all('td')
                    if len(cols) < 3:
                        continue
                    
                    # Buscar columna amb nom d'equip i logo
                    equip_text = ''
                    logo_url = ''
                    equip_idx = -1
                    team_id = ''
                    
                    for i, col in enumerate(cols):
                        # Buscar link amb ID de l'equip
                        link = col.find('a', href=True)
                        if link and '/team/' in link.get('href', ''):
                            href = link['href']
                            # Extreure ID: /ca/team/15621223 -> 15621223
                            id_match = re.search(r'/team/(\d+)', href)
                            if id_match:
                                team_id = id_match.group(1)
                        
                        img = col.find('img')
                        if img:
                            logo_url = img.get('src', '')
                        
                        text = col.get_text(strip=True)
                        if len(text) > 3 and not text.isdigit():
                            equip_text = text
                            equip_idx = i
                            break
                    
                    if not equip_text or equip_idx < 0:
                        continue
                    
                    posicio_text = str(idx)
                    stats_start = equip_idx + 1
                    
                    team_data = {
                        'posicio': posicio_text,
                        'equip': equip_text,
                        'team_id': team_id,
                        'logo': logo_url,
                        'punts': 0,
                        'partits': 0,
                        'guanyats': 0,
                        'empatats': 0,
                        'perduts': 0,
                        'gols_favor': 0,
                        'gols_contra': 0,
                        'diferencia': 0
                    }
                    
                    stat_fields = ['punts', 'partits', 'guanyats', 'empatats', 'perduts', 'gols_favor', 'gols_contra', 'diferencia']
                    
                    for i, field in enumerate(stat_fields):
                        col_idx = stats_start + i
                        if col_idx < len(cols):
                            value_text = cols[col_idx].get_text(strip=True)
                            if value_text.isdigit():
                                team_data[field] = int(value_text)
                    
                    if team_data['equip'] and len(team_data['equip']) > 1:
                        ranking.append(team_data)
                    
                except Exception as e:
                    continue
            
            return ranking
            
        except Exception as e:
            return []
    
    def get_rival_last_results(self, team_id, team_name, language='es'):
        """🆕 Obté els últims resultats d'un equip rival"""
        try:
            results_data = self.get_tab_content(team_id, 'last-results', language)
            if results_data and results_data.get('code') == 0:
                results = self.parse_last_results(results_data.get('content', ''))
                return results[:5]  # Només últims 5
            return []
        except Exception as e:
            print(f"    ⚠️ Error obtenint resultats de {team_name}: {e}")
            return []
    
    def get_all_rivals_form(self, ranking, language='es'):
        """🆕 Obté la forma de tots els rivals de la classificació"""
        rivals_form = {}
        
        print("\n6️⃣ FORMA DELS RIVALS:")
        
        for team in ranking:
            team_name = team.get('equip', '')
            team_id = team.get('team_id', '')
            
            # Saltar el nostre equip
            if 'TERRASSA' in team_name.upper():
                continue
            
            if not team_id:
                print(f"    ⚠️ {team_name}: sense ID")
                continue
            
            print(f"    📊 {team_name}...", end=' ')
            
            results = self.get_rival_last_results(team_id, team_name, language)
            
            if results:
                # Calcular forma (V/E/D)
                form = []
                for r in results:
                    score = r.get('score', '0-0')
                    score_parts = score.split('-')
                    if len(score_parts) == 2:
                        try:
                            g1, g2 = int(score_parts[0]), int(score_parts[1])
                        except:
                            g1, g2 = 0, 0
                        # Determinar si l'equip és team1 o team2
                        is_team1 = team_name.upper() in r.get('team1', '').upper()
                        if is_team1:
                            if g1 > g2: form.append('W')
                            elif g1 < g2: form.append('L')
                            else: form.append('D')
                        else:
                            if g2 > g1: form.append('W')
                            elif g2 < g1: form.append('L')
                            else: form.append('D')
                
                rivals_form[team_name] = {
                    'team_id': team_id,
                    'last_results': results,
                    'form': form,
                    'form_string': ''.join(form)
                }
                print(f"✅ {len(results)} resultats ({'-'.join(form)})")
            else:
                print(f"❌ sense resultats")
        
        return rivals_form
    
    def generate_json(self, team_id, team_key, team_name, coach, language='es', ranking_url=None):
        """Genera JSON amb normalització automàtica"""
        self.current_team_key = team_key
        
        print(f"\n{'='*70}")
        print(f"🔥 {team_name} - Parser v5.7 (AMB FORMA RIVALS)")
        print(f"{'='*70}")
        
        result = {
            "metadata": {
                "source": "ACTAWP",
                "team_key": team_key,
                "team_id": team_id,
                "team_name": team_name,
                "coach": coach,
                "downloaded_at": datetime.now().isoformat(),
                "parser_version": "5.7_rivals_form"
            }
        }
        
        print("\n1️⃣ JUGADORS:")
        players_data = self.get_tab_content(team_id, 'players', language)
        if players_data and players_data.get('code') == 0:
            result['players'] = self.parse_players(players_data.get('content', ''))
            print(f"  ✅ {len(result['players'])} jugadors")
            
            if result['players']:
                first = result['players'][0]
                print(f"  📊 Primer: {first.get('Nombre', '?')} - PJ:{first.get('PJ', 0)} GT:{first.get('GT', 0)}")
        else:
            result['players'] = []
        
        print("\n2️⃣ ESTADÍSTIQUES:")
        stats_data = self.get_tab_content(team_id, 'stats', language)
        team_stats = {}
        if stats_data and stats_data.get('code') == 0:
            soup = BeautifulSoup(stats_data.get('content', ''), 'html.parser')
            table = soup.find('table')
            if table:
                for row in table.find_all('tr'):
                    cells = row.find_all('td')
                    if len(cells) >= 2:
                        key = cells[0].get_text(strip=True)
                        value = cells[1].get_text(strip=True)
                        try:
                            if value.isdigit():
                                value = int(value)
                            elif ',' in value:
                                value = float(value.replace(',', '.'))
                        except:
                            pass
                        team_stats[key] = value
        result['team_stats'] = team_stats
        print(f"  ✅ {len(team_stats)} estadístiques")
        
        print("\n3️⃣ PRÒXIMS PARTITS:")
        upcoming_data = self.get_tab_content(team_id, 'upcoming-matches', language)
        if upcoming_data and upcoming_data.get('code') == 0:
            result['upcoming_matches'] = self.parse_upcoming_matches(upcoming_data.get('content', ''))
            print(f"  ✅ {len(result['upcoming_matches'])} partits")
            if result['upcoming_matches']:
                first = result['upcoming_matches'][0]
                print(f"  📅 Pròxim: J{first.get('jornada', '?')} - {first.get('team1', '?')} vs {first.get('team2', '?')} - {first.get('date', '?')}")
        else:
            result['upcoming_matches'] = []
        
        print("\n4️⃣ ÚLTIMS RESULTATS:")
        results_data = self.get_tab_content(team_id, 'last-results', language)
        if results_data and results_data.get('code') == 0:
            result['last_results'] = self.parse_last_results(results_data.get('content', ''))
            print(f"  ✅ {len(result['last_results'])} resultats")
            if result['last_results']:
                first = result['last_results'][0]
                score = first.get('score', '?')
                print(f"  📊 Últim: J{first.get('jornada', '?')} - {first.get('team1', '?')} {score} {first.get('team2', '?')}")
        else:
            result['last_results'] = []
        
        if ranking_url:
            print("\n5️⃣ CLASSIFICACIÓ:")
            result['ranking'] = self.parse_ranking(ranking_url)
            print(f"  ✅ {len(result['ranking'])} equips")
            if result['ranking']:
                cnt_position = None
                for team in result['ranking']:
                    if 'TERRASSA' in team['equip'].upper():
                        cnt_position = team
                        break
                if cnt_position:
                    print(f"  🏆 CN Terrassa: Posició {cnt_position['posicio']} - {cnt_position['punts']} punts")
            
            # 🆕 Obtenir forma dels rivals
            result['rivals_form'] = self.get_all_rivals_form(result['ranking'], language)
        else:
            result['ranking'] = []
            result['rivals_form'] = {}
        
        from datetime import timezone, timedelta
        tz_madrid = timezone(timedelta(hours=1))
        result['last_update'] = datetime.now(tz_madrid).isoformat()
        
        return result


if __name__ == "__main__":
    parser = ActawpParserV53()
    
    print("""
╔══════════════════════════════════════════════════════════════╗
║   PARSER ACTAWP v5.7 - AMB FORMA DELS RIVALS                 ║
║   ✅ Noms nets (sense Ver/Veure)                             ║
║   ✅ Camps normalitzats (PJ, GT, G, EX...)                   ║
║   ✅ MARCADORS correctes dels resultats                       ║
║   ✅ DATES correctes dels pròxims partits                     ║
║   ⭐ LOGOS dels equips en partits i classificació             ║
║   🆕 NÚMERO DE JORNADA en cada partit                         ║
║   🔧 CORRECCIONS MANUALS per partits ajornats                 ║
║   🆕 FORMA DELS RIVALS (últims 5 resultats)                   ║
╚══════════════════════════════════════════════════════════════╝
""")
    
    teams = {
        'juvenil': {
            'id': '15621223',
            'name': 'CN Terrassa Juvenil',
            'coach': 'Jordi Busquets',
            'language': 'es',
            'ranking_url': 'https://actawp.natacio.cat/ca/tournament/1317471/ranking/3669887'
        },
        'cadet': {
            'id': '15621224',
            'name': 'CN Terrassa Cadet',
            'coach': 'Didac Cobacho',
            'language': 'ca',
            'ranking_url': 'https://actawp.natacio.cat/ca/tournament/1317474/ranking/3669890'
        }
    }
    
    for team_key, team_info in teams.items():
        try:
            data = parser.generate_json(
                team_info['id'],
                team_key,
                team_info['name'],
                team_info['coach'],
                team_info['language'],
                team_info.get('ranking_url')
            )
            
            filename = f"actawp_{team_key}_data.json"
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            print(f"\n💾 Guardat: {filename}")
            
        except Exception as e:
            print(f"\n❌ Error: {e}")
            import traceback
            traceback.print_exc()
        
        print("\n" + "="*70)
    
    print("""
✅ JSON GENERATS CORRECTAMENT!

📊 Nova secció 'rivals_form' amb:
   - Últims 5 resultats de cada rival
   - Forma (W/L/D) de cada equip
   - ID de cada equip per futures consultes

📤 Puja'ls a GitHub:
   git add actawp_*.json
   git commit -m "✨ Parser v5.7 amb forma dels rivals"
   git push
""")
