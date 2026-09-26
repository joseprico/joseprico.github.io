#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Lector de l'acta ACTAWP en directe → Firebase RTDB `federacio/{matchId}`

L'app `app-nova/acta/` compara el que anotem a la piscina amb l'acta oficial.
Les dades d'EQUIP (marcador, parcials, quarts acabats) les llegeix l'app
directament de l'API pública de Leverade. Les dades per JUGADOR i el MINUT A
MINUT només surten a la pàgina del partit de l'ACTAWP, que té comprovació
anti-bot i no permet peticions des d'una altra web: aquest script obre la
pàgina un cop amb Chrome headless (controlat per CDP), i després en demana les
pestanyes "Estadístiques" i "Minut a minut" per AJAX, com fa la web quan hi
cliques. Així es pot llegir cada pocs segons i publicar-ho a la RTDB.
L'acta dels partits del juvenil s'omple en directe (no la de tots els partits:
els de Copa Catalunya del 25/09/2026 no es van omplir durant el joc).

Un sol script per als dos llocs on pot córrer:
  - GitHub Actions (.github/workflows/actawp_live.yml): cada 15 min mira el
    calendari; si hi ha un partit del CNT a punt o en joc, el segueix fins que
    acaba.
  - PC (reserva si l'anti-bot bloqueja GitHub): `python actawp_live.py --watch`

Ús:
    python actawp_live.py                  # un cop: segueix els partits actius i surt
    python actawp_live.py --watch          # bucle continu (PC)
    python actawp_live.py --match 144027416 --tournament 1317474   # un partit concret
    python actawp_live.py --dry-run ...    # no escriu a Firebase: JSON a app-nova/data/federacio/
    python actawp_live.py --check          # només diu si hi ha partit actiu (sense dependències)

Dependències (per seguir partits): pip install beautifulsoup4 firebase-admin websocket-client

Credencials (compte de servei de Firebase, NO la config pública del client):
    FIREBASE_SERVICE_ACCOUNT='{"type":"service_account",...}'   (secret de GitHub)
    o GOOGLE_APPLICATION_CREDENTIALS=C:\\ruta\\clau.json          (PC)
    o --key C:\\ruta\\clau.json
"""
import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.request
from datetime import datetime, timedelta, timezone

API = "https://api.leverade.com/"
BASE = "https://actawp.natacio.cat/ca"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) CNT-WP-Stats"
RTDB_URL = "https://cnt-wp-stats-bb7dc-default-rtdb.europe-west1.firebasedatabase.app"
DRY_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app-nova", "data", "federacio")
# Tornejos 26/27 que seguim (ids d'ACTAWP = ids de Leverade) i el nom EXACTE
# del nostre equip. Només el Juvenil A (decisió de l'usuari, 25/09/2026);
# per afegir-ne un altre: cadet 1339808, infantil 1339809, absolut 1339803, aleví 1339810.
TOURNAMENTS = {
    "juvenil": 1339807,
}
CNT_TEAMS = {
    "juvenil": "C.N. TERRASSA A",
}

PRE_START = timedelta(minutes=25)    # comença a vigilar abans de l'hora oficial
MAX_AFTER = timedelta(minutes=150)   # deixa de vigilar si l'acta no es tanca mai
READ_EVERY_LIVE = 10                 # s entre lectures del minut a minut amb el partit en joc (~0,5 s cadascuna)
READ_EVERY_PRE = 300                 # s entre lectures abans de començar
STATS_EVERY = 60                     # s màxim entre lectures per jugador (abans si el minut a minut canvia)
API_EVERY = 45                       # s entre lectures de l'API pública
AFTER_FINISH_READS = (180, 600)      # lectures extra després d'acabar (correccions de l'acta)

# Classe CSS de la capçalera de l'acta → clau curta (llegenda de l'ACTAWP)
COLS = {
    "colstyle-goles": "G",                                     # Gols
    "colstyle-goles-penalti": "GP",                            # Gols penal
    "colstyle-goals-shootout-5-period": "G5P",                 # Gols en tanda de penals
    "colstyle-tarjetas-amarillas": "TG",                       # Targetes grogues
    "colstyle-tarjetas-rojas": "TV",                           # Targetes vermelles
    "colstyle-expulsiones-20-segundos": "EX",                  # Expulsions per 20 segons
    "colstyle-expulsiones-definitivas-disciplinarias": "ED",   # Definitives, substitució disciplinària
    "colstyle-expulsiones-definitivas-brutalidad": "EB",       # Definitives per brutalitat
    "colstyle-expulsiones-definitivas-no-disciplinarias": "EN",  # Definitives, substitució no disciplinària
    "colstyle-expulsiones-penalti": "EP",                      # Expulsions i penal
    "colstyle-faltas-por-penalti": "P",                        # Faltes per penal
    "colstyle-penaltis-fallados": "PF",                        # Penals fallats
    "colstyle-otros": "ALT",                                   # Altres
    "colstyle-fair-play": "JN",                                # Joc net
    "colstyle-mvp": "MVP",
}

# Text d'una incidència del minut a minut → mateixa clau curta (l'ordre importa).
# Vistos: Gol, Gol penal, Expulsió per 20 segons, Falta per penal, Temps Mort, Targeta groga.
EVENT_KEYS = [
    (r"^gol.*tanda|tanda.*gol", "G5P"),
    (r"^gol.*penal", "GP"),
    (r"^gol", "G"),
    (r"expulsi.*20", "EX"),
    (r"expulsi.*penal", "EP"),
    (r"definitiv.*brutal", "EB"),
    (r"definitiv.*no disc", "EN"),
    (r"definitiv", "ED"),
    (r"falta.*penal", "P"),
    (r"penal.*fallat|fallat", "PF"),
    (r"groga", "TG"),
    (r"vermella", "TV"),
    (r"temps mort", "TM"),
]
QUARTERS = {"I": 1, "II": 2, "III": 3, "IV": 4}


def log(*a):
    print(datetime.now().strftime("%H:%M:%S"), *a, flush=True)


def utc_now():
    return datetime.now(timezone.utc)


def ms(dt=None):
    return int((dt or utc_now()).timestamp() * 1000)


def norm(s):
    return re.sub(r"\s+", " ", (s or "")).strip().upper()


# ----------------------------------------------------------------------------
# API pública Leverade (sense anti-bot; cal un User-Agent de navegador)
# ----------------------------------------------------------------------------
def api(path):
    req = urllib.request.Request(API + path, headers={"Accept": "application/vnd.api+json", "User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def parse_dt(s):
    return datetime.strptime(s, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc) if s else None


def cnt_matches(cat, tid):
    """Partits d'un torneig on juga el nostre equip (les hores de Leverade són UTC)."""
    d = api(f"tournaments/{tid}?include=teams,groups.rounds.matches")
    inc = d.get("included", [])
    teams = {i["id"]: i["attributes"]["name"] for i in inc if i["type"] == "team"}
    round_group = {i["id"]: i["relationships"]["group"]["data"]["id"] for i in inc if i["type"] == "round"}
    ours = norm(CNT_TEAMS[cat])
    out = []
    for m in inc:
        if m["type"] != "match":
            continue
        h, a = m["meta"].get("home_team"), m["meta"].get("away_team")
        if not h or not a or not m["attributes"].get("datetime"):
            continue
        if ours not in (norm(teams.get(h)), norm(teams.get(a))):
            continue
        out.append({
            "matchId": m["id"], "tournamentId": str(tid), "category": cat,
            "groupId": round_group.get(m["relationships"]["round"]["data"]["id"]),
            "start": parse_dt(m["attributes"]["datetime"]),
            "home": {"id": h, "name": teams.get(h, "")},
            "away": {"id": a, "name": teams.get(a, "")},
            "finished": bool(m["attributes"].get("finished")),
        })
    return out


def team_state(group_id, match_id):
    """Marcador, parcials i quarts acabats d'un partit (una crida pel grup)."""
    d = api(f"groups/{group_id}?include=rounds.matches.results,rounds.matches.periods.results")
    inc = d.get("included", [])
    by = {(i["type"], i["id"]): i for i in inc}
    m = by.get(("match", match_id))
    if not m:
        return None
    home, away = m["meta"].get("home_team"), m["meta"].get("away_team")
    res = [i for i in inc if i["type"] == "result" and i["relationships"]["match"]["data"]["id"] == match_id]

    def per(r):
        return ((r["relationships"].get("period") or {}).get("data") or {}).get("id")

    tot = {r["relationships"]["team"]["data"]["id"]: r["attributes"]["value"] for r in res if not per(r)}
    periods = []
    for ref in m["relationships"].get("periods", {}).get("data", []):
        p = by.get(("period", ref["id"]))
        if not p:
            continue
        pv = {r["relationships"]["team"]["data"]["id"]: r["attributes"]["value"] for r in res if per(r) == p["id"]}
        periods.append({"name": p["attributes"]["name"], "finished": bool(p["attributes"]["finished"]),
                        "home": pv.get(home), "away": pv.get(away)})
    return {
        "finished": bool(m["attributes"].get("finished")),
        "score": {"home": tot.get(home), "away": tot.get(away)},
        "periods": periods,
        "apiUpdatedAt": m["attributes"].get("updated_at"),
    }


# ----------------------------------------------------------------------------
# Acta per jugador (pàgina HTML amb anti-bot → Chrome headless)
# ----------------------------------------------------------------------------
def parse_stats(html):
    """→ [(nom_equip, [jugador...])] en l'ordre de la pàgina."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    tables = []
    for t in soup.find_all("table"):
        keys = []
        for th in t.find_all("th"):
            cls = next((c for c in th.get("class", []) if c.startswith("colstyle-")), "")
            keys.append(cls)
        if "colstyle-dorsal" not in keys:
            continue
        head = t.find_previous(["h2", "h3", "h4"])
        players = []
        for tr in t.select("tbody tr"):
            tds = tr.find_all("td")
            if len(tds) < len(keys):
                continue
            cell = {k: re.sub(r"\s+", " ", tds[i].get_text(" ", strip=True)) for i, k in enumerate(keys) if k}
            num = cell.get("colstyle-dorsal", "")
            name = cell.get("colstyle-jugador", "")
            if not num.isdigit():
                continue
            st = {}
            for cls, key in COLS.items():
                v = cell.get(cls, "")
                st[key] = int(v) if v.isdigit() else 0
            players.append({
                "num": int(num),
                "name": re.sub(r"\s*\(c\)\s*$", "", name, flags=re.I),
                "captain": bool(re.search(r"\(c\)\s*$", name, re.I)),
                "titular": cell.get("colstyle-titular", "").lower().startswith("titular"),
                "s": st,
            })
        tables.append((head.get_text(" ", strip=True) if head else "", players))
    return tables


def side_of(match, team_name, fallback):
    if norm(team_name) == norm(match["home"]["name"]):
        return "home"
    if norm(team_name) == norm(match["away"]["name"]):
        return "away"
    return fallback


def parse_events(html, match):
    """Pestanya "Minut a minut" → [{q, t, side, num, name, k, txt, score}] en ordre de joc.
    `t` és el rellotge del quart (compte enrere des de 8:00); `score` només surt als gols."""
    from bs4 import BeautifulSoup
    box = BeautifulSoup(html, "html.parser").select_one(".live-scoring")
    out, q = [], 0
    if not box:
        return out
    for el in box.find_all(lambda t: t.name == "div" and {"separator", "incidence"} & set(t.get("class", []))):
        if "separator" in el["class"]:
            label = norm(el.get_text())
            q = QUARTERS.get(label, 5)  # després del IV: tanda de penals
            continue
        bubble, who = el.select_one(".bubble"), el.select_one(".strong.ellipsis")
        if not bubble or not who:
            continue
        sc = bubble.find("strong")
        score = re.sub(r"\s+", "", sc.get_text()) if sc else None
        if sc:
            sc.extract()
        clock = re.findall(r"\d+", bubble.get_text())
        dorsal = who.select_one('[title="Dorsal"]')
        num = norm(dorsal.get_text()) if dorsal else ""
        if dorsal:
            dorsal.extract()
        what = who.find_next_sibling("div")
        txt = re.sub(r"\s+", " ", what.get_text(" ", strip=True)) if what else ""
        team = el.select_one(".visible-xs")
        e = {
            "q": q,
            "t": f"{clock[0]}:{clock[1]}" if len(clock) >= 2 else "",
            "side": side_of(match, team.get_text() if team else "", "home" if "left" in el["class"] else "away"),
            "num": int(num) if num.isdigit() else num,  # "E1" = entrenador
            "name": re.sub(r"\s+", " ", who.get_text(" ", strip=True)),
            "k": next((k for rx, k in EVENT_KEYS if re.search(rx, txt, re.I)), None),
            "txt": txt,
        }
        if score:
            e["score"] = score
        out.append({k: v for k, v in e.items() if v is not None})
    return out


def teams_by_side(match, tables):
    out, names = {"home": [], "away": []}, {}
    for i, (name, players) in enumerate(tables[:2]):
        # nom inesperat: ordre de la pàgina, sense trepitjar l'altre
        side = side_of(match, name, "home" if (i == 0 and not out["home"]) or out["away"] else "away")
        out[side] = sorted(players, key=lambda p: p["num"])
        names[side] = name
    return out, names


class RateLimited(RuntimeError):
    pass


# Clic a una pestanya del partit, fet des de la mateixa pàgina (galetes de l'anti-bot + token CSRF)
JS_TAB = """(async tab => {
  const a = [...document.querySelectorAll('a.ml-trigger')].find(x => x.querySelector('input[name=tab]')?.value === tab);
  if (!a) return {status: 0, body: 'sense pestanya'};
  const fd = new URLSearchParams();
  a.querySelectorAll('input').forEach(i => fd.append(i.name, i.value));
  const r = await fetch(a.getAttribute('ml-controller'), {method: 'POST', body: fd, credentials: 'include',
    headers: {'X-Requested-With': 'XMLHttpRequest', 'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8'}});
  return {status: r.status, body: await r.text()};
})(%s)"""


class ActaBrowser:
    """Chrome headless obert durant tot el partit i controlat per CDP (DevTools).
    Carrega la pàgina de l'acta un cop (passa la comprovació anti-bot) i després només fa
    les peticions AJAX de les pestanyes: molt més lleuger que obrir un Chrome per lectura."""

    def __init__(self, url, tag):
        self.url = url
        self.profile = os.path.join(tempfile.gettempdir(), f"actawp_live_{tag}")
        self.proc = self.ws = None
        self.seq = 0

    def start(self):
        import websocket  # websocket-client (només cal si hi ha partit)
        from actawp_fetch_26_27 import find_browser
        os.makedirs(self.profile, exist_ok=True)
        port_file = os.path.join(self.profile, "DevToolsActivePort")
        if os.path.exists(port_file):
            os.remove(port_file)
        self.proc = subprocess.Popen(
            [find_browser(), "--headless=new", "--disable-gpu", "--no-first-run",
             f"--user-data-dir={self.profile}", "--remote-debugging-port=0", "about:blank"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        port = None
        for _ in range(100):
            time.sleep(0.2)
            try:
                port = open(port_file).read().split()[0]
                break
            except (OSError, IndexError):
                pass
        if not port:
            raise RuntimeError("Chrome no obre el port de depuració")
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/list", timeout=10) as r:
            page = next(t for t in json.load(r) if t["type"] == "page")
        self.ws = websocket.create_connection(page["webSocketDebuggerUrl"], timeout=60, suppress_origin=True)
        self.load()

    def call(self, method, **params):
        self.seq += 1
        self.ws.send(json.dumps({"id": self.seq, "method": method, "params": params}))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == self.seq:
                if "error" in msg:
                    raise RuntimeError(f"CDP {method}: {msg['error'].get('message')}")
                return msg.get("result", {})

    def evaluate(self, expr):
        r = self.call("Runtime.evaluate", expression=expr, awaitPromise=True, returnByValue=True)
        if r.get("exceptionDetails"):
            raise RuntimeError(f"JS: {r['exceptionDetails'].get('text')}")
        return r.get("result", {}).get("value")

    def load(self):
        self.call("Page.navigate", url=self.url)
        for _ in range(60):
            time.sleep(1)
            try:
                if self.evaluate("!!document.querySelector('input[name=csrf_token]') && "
                                 "!document.body.innerText.includes('Comprovant el teu navegador')"):
                    return
            except RuntimeError:  # la pàgina de comprovació redirigeix: context destruït
                pass
        raise RuntimeError(f"No s'ha pogut carregar {self.url} (comprovació anti-bot?)")

    def tab(self, name):
        """Contingut HTML d'una pestanya: 'statistics' o 'minute_by_minute'."""
        status = None
        for attempt in range(2):
            r = self.evaluate(JS_TAB % json.dumps(name)) or {}
            status = r.get("status")
            if status == 429:
                raise RateLimited(f"L'ACTAWP diu prou peticions (429) a '{name}'")
            if status == 200:
                try:
                    d = json.loads(r.get("body") or "")
                    if d.get("code") == 0 and d.get("content"):
                        return d["content"]
                except ValueError:
                    pass
            if attempt == 0:  # sessió/CSRF caducats o comprovació anti-bot: recarrega la pàgina
                self.load()
        raise RuntimeError(f"L'acta no respon a '{name}' (HTTP {status})")

    def close(self):
        try:
            if self.ws:
                self.ws.close()
        except Exception:
            pass
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        self.proc = self.ws = None


# ----------------------------------------------------------------------------
# Destí: RTDB (compte de servei) o fitxers locals (--dry-run)
# ----------------------------------------------------------------------------
class Sink:
    def __init__(self, dry, key_path=None):
        self.dry = dry
        if dry:
            os.makedirs(DRY_DIR, exist_ok=True)
            return
        import firebase_admin
        from firebase_admin import credentials, db
        raw = os.environ.get("FIREBASE_SERVICE_ACCOUNT")
        path = key_path or os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
        if raw:
            cred = credentials.Certificate(json.loads(raw))
        elif path:
            cred = credentials.Certificate(path)
        else:
            raise SystemExit("Falten credencials: defineix FIREBASE_SERVICE_ACCOUNT o GOOGLE_APPLICATION_CREDENTIALS "
                             "(o fes servir --key / --dry-run).")
        firebase_admin.initialize_app(cred, {"databaseURL": RTDB_URL})
        self.db = db

    def update(self, mid, data):
        if self.dry:
            fn = os.path.join(DRY_DIR, f"{mid}.json")
            cur = json.load(open(fn, encoding="utf-8")) if os.path.exists(fn) else {}
            cur.update(data)
            with open(fn, "w", encoding="utf-8") as f:
                json.dump(cur, f, ensure_ascii=False, indent=2)
        else:
            self.db.reference(f"federacio/{mid}").update(data)


# ----------------------------------------------------------------------------
# Seguiment
# ----------------------------------------------------------------------------
class Tracker:
    def __init__(self, match, sink, host):
        self.m, self.sink, self.host = match, sink, host
        self.next_api = self.next_read = self.next_stats = utc_now()
        self.finished_at = None
        self.after_reads = list(AFTER_FINISH_READS)
        self.backoff = 0
        self.last_state = self.last_players = self.last_events = None
        self.last_status = (None, None, 0.0)
        self.browser = None
        self.done = False
        m = match
        self.url = f"{BASE}/tournament/{m['tournamentId']}/match/{m['matchId']}/stats"
        sink.update(m["matchId"], {
            "matchId": m["matchId"], "tournamentId": m["tournamentId"], "groupId": m["groupId"],
            "category": m["category"], "datetime": m["start"].strftime("%Y-%m-%dT%H:%M:%SZ"),
            "home": m["home"], "away": m["away"], "actaUrl": self.url,
        })

    def label(self):
        return f"{self.m['home']['name']} – {self.m['away']['name']} ({self.m['matchId']})"

    def status(self, st, msg=""):
        # Cada lectura "ok" no cal escriure-la: només canvis o, com a molt, un cop per minut
        if (st, msg) == self.last_status[:2] and time.time() - self.last_status[2] < 60:
            return
        self.last_status = (st, msg, time.time())
        self.sink.update(self.m["matchId"], {"checkedAt": ms(), "lector": {"host": self.host, "status": st, "msg": msg, "at": ms()}})

    def close(self):
        if self.browser:
            self.browser.close()
            self.browser = None

    def read(self, now):
        mid = self.m["matchId"]
        if not self.browser:
            self.browser = ActaBrowser(self.url, mid)
            self.browser.start()
        events = parse_events(self.browser.tab("minute_by_minute"), self.m)
        fresh = events != self.last_events
        if fresh:
            prev = self.last_events or []
            self.last_events = events
            self.sink.update(mid, {"events": events, "eventsAt": ms()})
            if events[:len(prev)] != prev:
                log(f"🔁 minut a minut corregit: {len(prev)} → {len(events)} accions")
            for e in events[len(prev):] if events[:len(prev)] == prev else []:
                side = self.m[e["side"]]["name"]
                log(f"⏱️ Q{e['q']} {e['t']} {e['txt']} · {side} #{e['num']} {e['name']} {e.get('score', '')}")
        # Per jugador: quan el minut a minut canvia (hi haurà coses noves) i, si no, cada STATS_EVERY
        if fresh or self.last_players is None or now >= self.next_stats:
            players, names = teams_by_side(self.m, parse_stats(self.browser.tab("statistics")))
            self.next_stats = now + timedelta(seconds=STATS_EVERY)
            if players != self.last_players:
                self.last_players = players
                self.sink.update(mid, {"players": players, "tableNames": names, "statsAt": ms()})
                g = {s: sum(p["s"]["G"] + p["s"]["GP"] for p in players[s]) for s in ("home", "away")}
                log(f"🧾 acta {self.label()}: {len(players['home'])}+{len(players['away'])} jugadors, gols {g['home']}-{g['away']}")

    def tick(self):
        now = utc_now()
        mid = self.m["matchId"]
        if now >= self.next_api:
            self.next_api = now + timedelta(seconds=API_EVERY)
            try:
                st = team_state(self.m["groupId"], mid)
                if st and st != self.last_state:
                    self.last_state = st
                    self.sink.update(mid, {**st, "apiAt": ms()})
                    sc = st["score"]
                    log(f"📊 {self.label()}: {sc['home']}-{sc['away']} {'(acabat)' if st['finished'] else ''}")
                if st and st["finished"] and not self.finished_at:
                    self.finished_at = now
                    self.next_read = now + timedelta(seconds=self.after_reads.pop(0))
            except Exception as e:
                log(f"⚠️ API {mid}: {e}")

        if now >= self.next_read:
            try:
                self.read(now)
                self.backoff = 0
                self.status("ok")
            except Exception as e:
                limited = isinstance(e, RateLimited)
                self.backoff = min(max(self.backoff * 2, 60 if limited else 20), 300)
                blocked = "comprovació" in str(e).lower() or "No s'ha pogut carregar" in str(e)
                log(f"⚠️ acta {mid}: {e} (espero {self.backoff}s)")
                self.status("blocked" if blocked else "error", str(e)[:200])
                if not limited:  # sessió trencada: la propera lectura torna a obrir Chrome
                    self.close()

            if self.finished_at:
                if self.after_reads:
                    self.next_read = self.finished_at + timedelta(seconds=self.after_reads.pop(0))
                else:
                    self.done = True
                    log(f"🏁 {self.label()}: acta final desada")
                    return
            else:
                gap = READ_EVERY_LIVE if now >= self.m["start"] - timedelta(minutes=3) else READ_EVERY_PRE
                self.next_read = now + timedelta(seconds=max(gap, self.backoff))

        if now > self.m["start"] + MAX_AFTER:
            self.done = True
            log(f"⏹️ {self.label()}: temps màxim de seguiment")


def active_matches(now, only=None):
    found = []
    if only:
        mid, tid = only
        cat = next((c for c, t in TOURNAMENTS.items() if str(t) == str(tid)), "")
        for m in all_matches_of(tid):
            if m["matchId"] == str(mid):
                return [{**m, "category": cat}]
        raise SystemExit(f"No trobo el partit {mid} al torneig {tid}")
    for cat, tid in TOURNAMENTS.items():
        try:
            for m in cnt_matches(cat, tid):
                if m["start"] - PRE_START <= now <= m["start"] + MAX_AFTER:
                    found.append(m)
        except Exception as e:
            log(f"⚠️ calendari {cat}: {e}")
    return found


def all_matches_of(tid):
    """Per --match fora dels tornejos del CNT 26/27 (p.ex. proves amb temporades passades)."""
    d = api(f"tournaments/{tid}?include=teams,groups.rounds.matches")
    inc = d.get("included", [])
    teams = {i["id"]: i["attributes"]["name"] for i in inc if i["type"] == "team"}
    round_group = {i["id"]: i["relationships"]["group"]["data"]["id"] for i in inc if i["type"] == "round"}
    for m in inc:
        if m["type"] == "match" and m["meta"].get("home_team") and m["meta"].get("away_team"):
            h, a = m["meta"]["home_team"], m["meta"]["away_team"]
            yield {"matchId": m["id"], "tournamentId": str(tid), "category": "",
                   "groupId": round_group.get(m["relationships"]["round"]["data"]["id"]),
                   "start": parse_dt(m["attributes"].get("datetime")) or utc_now(),
                   "home": {"id": h, "name": teams.get(h, "")}, "away": {"id": a, "name": teams.get(a, "")},
                   "finished": bool(m["attributes"].get("finished"))}


def check():
    """Per GitHub Actions: `active=true|false` sense instal·lar res (només biblioteca estàndard)."""
    ms_ = active_matches(utc_now())
    for m in ms_:
        log(f"⏳ {m['category']}: {m['home']['name']} – {m['away']['name']} ({m['start']:%d/%m %H:%M} UTC)")
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as f:
            f.write(f"active={'true' if ms_ else 'false'}\n")
    log("Partit actiu" if ms_ else "Cap partit del CNT a punt o en joc.")


def run(args):
    sink = Sink(args.dry_run, args.key)
    host = os.environ.get("LECTOR_HOST", "pc")
    only = (args.match, args.tournament) if args.match else None
    trackers = {}
    try:
        follow(args, sink, host, only, trackers)
    finally:
        for t in trackers.values():
            t.close()


def follow(args, sink, host, only, trackers):
    started = utc_now()
    next_discover = started
    while True:
        now = utc_now()
        if now >= next_discover:
            next_discover = now + timedelta(minutes=5 if trackers or args.watch else 10)
            for m in active_matches(now, only):
                if m["matchId"] not in trackers:
                    log(f"👀 Segueixo {m['home']['name']} – {m['away']['name']} ({m['category']}, {m['start']:%d/%m %H:%M} UTC)")
                    trackers[m["matchId"]] = Tracker(m, sink, host)
                    if only and m["finished"]:  # partit ja jugat: una lectura i prou
                        trackers[m["matchId"]].after_reads = []
                        trackers[m["matchId"]].finished_at = now
            if not trackers and not args.watch:
                log("Cap partit del CNT a punt o en joc. Surto.")
                return
        for t in list(trackers.values()):
            t.tick()
            if t.done:
                t.close()
                trackers.pop(t.m["matchId"])
        if not trackers and (only or not args.watch):
            log("Fet.")
            return
        if not args.watch and now - started > timedelta(minutes=args.max_minutes):
            log("Límit de temps de la feina assolit.")
            return
        time.sleep(5 if trackers else 60)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Lector de l'acta ACTAWP en directe → RTDB federacio/")
    ap.add_argument("--watch", action="store_true", help="bucle continu (PC)")
    ap.add_argument("--match", help="id del partit (Leverade/ACTAWP)")
    ap.add_argument("--tournament", help="id del torneig del partit (amb --match)")
    ap.add_argument("--dry-run", action="store_true", help="no escriu a Firebase; JSON a app-nova/data/federacio/")
    ap.add_argument("--key", help="ruta al JSON del compte de servei")
    ap.add_argument("--check", action="store_true", help="només diu si hi ha partit actiu (GitHub Actions)")
    ap.add_argument("--max-minutes", type=int, default=225, help="durada màxima en mode un cop (GitHub)")
    a = ap.parse_args()
    if a.match and not a.tournament:
        ap.error("--match necessita --tournament")
    check() if a.check else run(a)
