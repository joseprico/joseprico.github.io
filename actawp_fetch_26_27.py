#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ACTAWP 26/27 → JSON per a l'app v2 (app-nova/app)

La web de la federació (actawp.natacio.cat) ha afegit una "comprovació del
navegador" en JavaScript, així que `requests` ja no serveix. Aquest script fa
les peticions amb Chrome/Edge headless (executa la comprovació com qualsevol
usuari) i parseja l'HTML resultant amb BeautifulSoup.

Genera `app-nova/data/actawp_<categoria>_data.json` amb la MATEIXA forma que
produïa `ultra_robust_parser.py` (upcoming_matches, last_results, ranking,
rivals_form, metadata...) perquè l'app no hagi de canviar de format, més
alguns blocs nous (group_matches, groups, other_cnt_teams).

Ús:
    python actawp_fetch_26_27.py                # totes les categories amb torneig configurat
    python actawp_fetch_26_27.py juvenil        # només una
    python actawp_fetch_26_27.py juvenil cadet
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone

from bs4 import BeautifulSoup

BASE = "https://actawp.natacio.cat/ca"
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app-nova", "data")
SEASON = "2026-27"

# Tornejos 26/27 (ids trobats a la home d'ACTAWP el 2026-09-11).
# `cnt_team` és el nom EXACTE de l'equip a ACTAWP; `cnt_match` és el text que
# identifica qualsevol equip del club (per detectar els altres equips CNT).
CONFIG = {
    "juvenil": {
        "tournament": 1339807,
        "tournament_name": "LLIGA CATALANA JUVENIL MASCULI 26/27",
        "cnt_team": "C.N. TERRASSA A",
        "coach": "Jordi Busquets",
        "team_name": "CN Terrassa Juvenil",
    },
    "cadet": {
        "tournament": 1339808,
        "tournament_name": "LLIGA CATALANA CADET MASCULI 26/27",
        "cnt_team": None,  # es detecta (primer equip que contingui TERRASSA)
        "coach": "Dídac Cobacho",
        "team_name": "CN Terrassa Cadet",
    },
    "infantil": {
        "tournament": 1339809,
        "tournament_name": "LLIGA CATALANA INFANTIL MIXTE 26/27",
        "cnt_team": None,
        "coach": "",
        "team_name": "CN Terrassa Infantil",
    },
    "absolut": {
        "tournament": 1339803,
        "tournament_name": "LLIGA CATALANA 1A DIV.ABSOLUTA MASCULINA 26/27",
        "cnt_team": None,
        "coach": "Sergi Mora",
        "team_name": "CN Terrassa Absolut",
    },
}
CNT_MATCH = "TERRASSA"

# ----------------------------------------------------------------------------
# Descàrrega amb navegador headless
# ----------------------------------------------------------------------------
BROWSERS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    "/usr/bin/google-chrome", "/usr/bin/chromium", "/usr/bin/chromium-browser",
]
PROFILE_DIR = os.path.join(tempfile.gettempdir(), "actawp_chrome_profile")
_last_fetch = 0.0


def find_browser():
    env = os.environ.get("ACTAWP_BROWSER")
    if env and os.path.exists(env):
        return env
    for p in BROWSERS:
        if os.path.exists(p):
            return p
    raise SystemExit("No trobo Chrome/Edge. Defineix ACTAWP_BROWSER=<ruta a chrome.exe>")


def fetch(url, min_gap=2.0, retries=2):
    """Carrega la pàgina amb el navegador headless i retorna el DOM final."""
    global _last_fetch
    browser = find_browser()
    for attempt in range(retries + 1):
        wait = min_gap - (time.time() - _last_fetch)
        if wait > 0:
            time.sleep(wait)
        cmd = [
            browser, "--headless=new", "--disable-gpu", "--no-first-run",
            f"--user-data-dir={PROFILE_DIR}",
            "--virtual-time-budget=20000", "--timeout=40000",
            "--dump-dom", url,
        ]
        res = subprocess.run(cmd, capture_output=True, timeout=90)
        _last_fetch = time.time()
        html = res.stdout.decode("utf-8", errors="replace")
        if "Comprovant el teu navegador" in html or len(html) < 5000:
            print(f"   ⚠️ comprovació/pàgina buida ({len(html)} bytes), reintent {attempt + 1}...")
            time.sleep(5)
            continue
        return html
    raise RuntimeError(f"No s'ha pogut carregar {url}")


# ----------------------------------------------------------------------------
# Parsers
# ----------------------------------------------------------------------------
def clean(s):
    return re.sub(r"\s+", " ", (s or "")).strip()


def discover_groups(tid, html):
    """Del resum del torneig: [(group_id, 'Grup B 1a Fase'), ...]"""
    soup = BeautifulSoup(html, "html.parser")
    groups, seen = [], set()
    for a in soup.find_all("a", href=re.compile(rf"/tournament/{tid}/calendar/(\d+)$")):
        gid = a["href"].rsplit("/", 1)[-1]
        name = clean(a.get_text(" ", strip=True))
        if gid in seen or not name or name.lower() in ("calendari", "jornada actual"):
            continue
        seen.add(gid)
        groups.append((gid, name))
    return groups


def parse_calendar(html):
    """Calendari complet d'un grup → llista de partits (inclou descansos)."""
    soup = BeautifulSoup(html, "html.parser")
    matches = []
    for tbl in soup.find_all("table"):
        if not tbl.select_one("td.colstyle-equipo"):
            continue
        jtxt = tbl.find_previous(string=re.compile(r"Jornada\s+\d+"))
        jornada = int(re.search(r"Jornada\s+(\d+)", jtxt).group(1)) if jtxt else None
        for tr in tbl.select("tbody tr"):
            eq = tr.select_one("td.colstyle-equipo")
            if not eq:
                continue
            teams, logos = [], []
            for sp in eq.find_all("span", recursive=False):
                img = sp.find("img")
                name = clean(sp.get_text(" ", strip=True))
                if name:
                    teams.append(name)
                    logos.append(img["src"] if img else "")
            if not teams:
                continue
            a = eq.find("a", href=re.compile(r"/match/\d+"))
            url = a["href"] if a else ""
            date_txt = clean(tr.select_one("td.colstyle-fecha").get_text(" ", strip=True)) if tr.select_one("td.colstyle-fecha") else ""
            dm = re.search(r"(\d{2})/(\d{2})/(\d{4})\s+(\d{2}):(\d{2})", date_txt)
            venue_el = tr.select_one("td.colstyle-fecha .ellipsis")
            venue = clean(venue_el.get("data-original-title") or venue_el.get("title") or venue_el.get_text()) if venue_el else ""
            res_txt = clean(tr.select_one("td.colstyle-resultado").get_text(" ", strip=True)) if tr.select_one("td.colstyle-resultado") else ""
            # Resultat i parcials: a la columna "Parcials" el primer bloc
            # (.partial-result.strong) és el marcador final i els següents
            # són els quarts (Q1..Q4 + pròrroga). Sense jugar, tot són "‐".
            score, partials = "", []
            for i, vr in enumerate(tr.select("td.colstyle-parciales .vertical-result")):
                vals = [clean(x.get_text()) for x in vr.select(".partial-result")]
                if len(vals) == 2 and all(v.isdigit() for v in vals):
                    if i == 0 or vr.select_one(".partial-result.strong"):
                        score = f"{vals[0]}-{vals[1]}"
                    else:
                        partials.append([int(vals[0]), int(vals[1])])
            if not score:
                sm = re.fullmatch(r"(\d{1,2})\s*[-–]\s*(\d{1,2})", res_txt)
                score = f"{sm.group(1)}-{sm.group(2)}" if sm else ""
            m = {
                "team1": teams[0],
                "team2": teams[1] if len(teams) > 1 else "",
                "team1_logo": logos[0] if logos else "",
                "team2_logo": logos[1] if len(logos) > 1 else "",
                "jornada": jornada,
                "url": url,
            }
            if len(teams) < 2:
                m["bye"] = True  # l'equip descansa aquesta jornada
            if dm:
                d, mo, y, hh, mm = dm.groups()
                m["date"] = f"{d}/{mo}/{y}"
                m["time"] = f"{hh}:{mm}"
                m["date_time"] = f"{d}/{mo}/{y} {hh}:{mm}"
                m["iso_date"] = f"{y}-{mo}-{d}"
            else:
                m["date"] = m["time"] = m["date_time"] = ""
                m["iso_date"] = ""
            m["venue"] = venue
            if score:
                m["score"] = score
            if partials:
                m["partials"] = partials
            matches.append(m)
    return matches


def parse_ranking(html):
    soup = BeautifulSoup(html, "html.parser")
    ranking = []
    for tbl in soup.find_all("table"):
        if not tbl.find("a", href=re.compile(r"/team/\d+")):
            continue
        for tr in tbl.select("tbody tr"):
            a = tr.find("a", href=re.compile(r"/team/(\d+)"))
            if not a:
                continue
            img = tr.find("img")
            cells = [clean(td.get_text(" ", strip=True)) for td in tr.find_all("td")]
            # [A/D, P, Nom, Punts, PJ, PG, PE, PP, F, C, D, ...]
            name_el = tr.select_one("td.colstyle-nombre") or (tr.find_all("td")[2] if len(tr.find_all("td")) > 2 else None)
            name = clean(name_el.get_text(" ", strip=True)) if name_el else ""
            name = re.sub(r"^Veure\s*", "", name)
            nums = []
            for td in tr.find_all("td"):
                cls = " ".join(td.get("class", []))
                if "colstyle-nombre" in cls or "colstyle-ascenso" in cls or "colstyle-posicion" in cls:
                    continue
                t = clean(td.get_text(" ", strip=True))
                nums.append(int(t) if re.fullmatch(r"-?\d+", t) else 0)
            pos_el = tr.select_one("td.colstyle-posicion")
            pos = clean(pos_el.get_text()) if pos_el else str(len(ranking) + 1)
            nums += [0] * 7
            ranking.append({
                "posicio": pos,
                "equip": name,
                "team_id": re.search(r"/team/(\d+)", a["href"]).group(1),
                "logo": img["src"] if img else "",
                "punts": nums[0], "partits": nums[1], "guanyats": nums[2],
                "empatats": nums[3], "perduts": nums[4],
                "gols_favor": nums[5], "gols_contra": nums[6], "diferencia": nums[7],
            })
        if ranking:
            break
    return ranking


# ----------------------------------------------------------------------------
# Construcció del JSON
# ----------------------------------------------------------------------------
def is_cnt(name, cnt_team):
    return name == cnt_team if cnt_team else (CNT_MATCH in name.upper())


def form_of(team, played):
    form = []
    for m in played:
        if not m.get("score"):
            continue
        a, b = map(int, m["score"].split("-"))
        mine, other = (a, b) if m["team1"] == team else (b, a)
        form.append("W" if mine > other else "L" if mine < other else "D")
    return form


def build(team_key, cfg):
    tid = cfg["tournament"]
    print(f"\n🏊 {team_key.upper()} · torneig {tid} · {cfg['tournament_name']}")
    # El resum només enllaça el calendari d'UN grup; la llista de grups/fases
    # (selector) és a la pàgina de calendari.
    summary = fetch(f"{BASE}/tournament/{tid}/summary")
    first = re.search(rf"/tournament/{tid}/calendar/(\d+)", summary)
    if not first:
        raise RuntimeError("El resum del torneig no enllaça cap calendari (encara no publicat?)")
    cached = {first.group(1): fetch(f"{BASE}/tournament/{tid}/calendar/{first.group(1)}/all")}
    groups = discover_groups(tid, cached[first.group(1)])
    if not groups:
        groups = [(first.group(1), "Calendari")]
    print(f"   📋 {len(groups)} grups/fases: {', '.join(n for _, n in groups)}")

    all_groups = []
    for gid, gname in groups:
        print(f"   📅 {gname} ({gid})...", end=" ", flush=True)
        html = cached.get(gid) or fetch(f"{BASE}/tournament/{tid}/calendar/{gid}/all")
        ms = parse_calendar(html)
        teams = sorted({t for m in ms for t in (m["team1"], m["team2"]) if t})
        print(f"{len(ms)} files, equips: {', '.join(teams)}")
        all_groups.append({"id": gid, "name": gname, "teams": teams, "matches": ms})

    # Equip CNT principal i el seu grup
    cnt_team = cfg.get("cnt_team")
    if not cnt_team:
        cands = sorted({t for g in all_groups for t in g["teams"] if CNT_MATCH in t.upper()})
        if not cands:
            raise RuntimeError("Cap equip TERRASSA en aquest torneig")
        cnt_team = cands[0]
        print(f"   ℹ️ Equip CNT detectat: {cnt_team}")
    my_group = next((g for g in all_groups if cnt_team in g["teams"]), None)
    if not my_group:
        raise RuntimeError(f"{cnt_team} no apareix a cap grup")
    print(f"   ✅ {cnt_team} és al {my_group['name']}")

    print(f"   🏆 Classificació {my_group['name']}...", end=" ", flush=True)
    ranking = parse_ranking(fetch(f"{BASE}/tournament/{tid}/ranking/{my_group['id']}"))
    print(f"{len(ranking)} equips")
    team_ids = {r["equip"]: r["team_id"] for r in ranking}
    logos = {r["equip"]: r["logo"] for r in ranking}

    gm = [m for m in my_group["matches"] if not m.get("bye")]
    mine = [m for m in gm if cnt_team in (m["team1"], m["team2"])]
    played = sorted([m for m in mine if m.get("score")], key=lambda m: m["iso_date"], reverse=True)
    upcoming = sorted([m for m in mine if not m.get("score")], key=lambda m: m["iso_date"] or "9999")
    byes = [m["jornada"] for m in my_group["matches"] if m.get("bye") and m["team1"] == cnt_team]

    rivals_form = {}
    for rival in my_group["teams"]:
        if rival == cnt_team:
            continue
        rp = sorted([m for m in gm if rival in (m["team1"], m["team2"]) and m.get("score")],
                    key=lambda m: m["iso_date"], reverse=True)[:5]
        form = form_of(rival, rp)
        gf = gc = 0
        for m in rp:
            a, b = map(int, m["score"].split("-"))
            f, c = (a, b) if m["team1"] == rival else (b, a)
            gf += f; gc += c
        n = len(rp)
        rivals_form[rival] = {
            "team_id": team_ids.get(rival, ""),
            "logo": logos.get(rival, ""),
            "last_results": rp,
            "form": form,
            "form_string": "".join(form),
            "top_scorers": [],
            "stats": {
                "total_gf": gf, "total_gc": gc,
                "avg_gf": round(gf / n, 1) if n else 0, "avg_gc": round(gc / n, 1) if n else 0,
                "matches_played": n,
                "wins": form.count("W"), "draws": form.count("D"), "losses": form.count("L"),
                "trend": "hot" if form[:3].count("W") >= 2 else ("cold" if n else "unknown"),
                "total_exclusions": 0,
            },
        }

    other_cnt = {}
    for g in all_groups:
        for t in g["teams"]:
            if t != cnt_team and CNT_MATCH in t.upper():
                other_cnt[t] = {
                    "group": g["name"], "group_id": g["id"],
                    "matches": [m for m in g["matches"] if not m.get("bye") and t in (m["team1"], m["team2"])],
                }

    now = datetime.now(timezone.utc).astimezone()
    data = {
        "metadata": {
            "source": "ACTAWP",
            "season": SEASON,
            "team_key": team_key,
            "team_id": team_ids.get(cnt_team, ""),
            "team_name": cfg["team_name"],
            "actawp_team_name": cnt_team,
            "coach": cfg["coach"],
            "tournament_id": tid,
            "tournament_name": cfg["tournament_name"],
            "tournament_url": f"{BASE}/tournament/{tid}/summary",
            "group_id": my_group["id"],
            "group_name": my_group["name"],
            "group_teams": my_group["teams"],
            "byes": byes,
            "downloaded_at": now.isoformat(),
            "parser_version": "7.0_26-27_headless",
        },
        "players": [],
        "team_stats": {},
        "upcoming_matches": upcoming,
        "last_results": played,
        "ranking": ranking,
        "rivals_form": rivals_form,
        "group_matches": gm,
        "groups": [{"id": g["id"], "name": g["name"], "teams": g["teams"],
                    "matches": [m for m in g["matches"] if not m.get("bye")]} for g in all_groups],
        "other_cnt_teams": other_cnt,
        "last_update": now.isoformat(),
    }
    os.makedirs(OUT_DIR, exist_ok=True)
    out = os.path.join(OUT_DIR, f"actawp_{team_key}_data.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"   💾 {out}  ({len(upcoming)} pròxims, {len(played)} jugats, {len(ranking)} a la classificació)")
    return data


if __name__ == "__main__":
    keys = [k for k in sys.argv[1:] if k in CONFIG] or list(CONFIG)
    bad = [k for k in sys.argv[1:] if k not in CONFIG]
    if bad:
        print(f"Categories desconegudes: {bad}. Vàlides: {list(CONFIG)}")
        sys.exit(1)
    ok = True
    for k in keys:
        try:
            build(k, CONFIG[k])
        except Exception as e:
            ok = False
            print(f"   ❌ {k}: {e}")
    sys.exit(0 if ok else 1)
