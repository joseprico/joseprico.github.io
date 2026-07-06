// ============================================================
// CN Terrassa Waterpolo · App v2 · Model de dades + magatzem
// Offline-first: font de veritat = localStorage. Firestore = sync.
// Compartit entre app d'entrada i app principal (lectura).
// ============================================================

export const SEASON = "2026-27";

// Equips per defecte (editables). Afegir categoria = afegir aquí o a Firestore.
export const TEAMS_SEED = [
  { id: "alevi",    nom: "Aleví",    genere: "masculi", accent: "cat-alevi",    icon: "🐟" },
  { id: "infantil", nom: "Infantil", genere: "masculi", accent: "cat-infantil", icon: "🐬" },
  { id: "cadet",    nom: "Cadet",    genere: "masculi", accent: "cat-cadet",    icon: "🦈" },
  { id: "juvenil",  nom: "Juvenil",  genere: "masculi", accent: "cat-juvenil",  icon: "🌊" },
  { id: "absolut",  nom: "Absolut",  genere: "masculi", accent: "cat-absolut",  icon: "🏆" },
];

export const GOAL_TYPES = [
  { id: "normal",  lab: "Normal" },
  { id: "h+",      lab: "Home +" },
  { id: "penalty", lab: "Penal" },
  { id: "contra",  lab: "Contraatac" },
  { id: "boya",    lab: "Boia" },
];
export const EXCLUSION_TYPES = [
  { id: "normal",  lab: "Normal" },
  { id: "penalty", lab: "Penal" },
];
export const QUARTERS = ["q1", "q2", "q3", "q4"];

// ---------- localStorage helpers ----------
const K = {
  teams:   "cntv2_teams",
  roster:  (t) => `cntv2_roster_${t}`,
  matches: "cntv2_matches",        // índex: [{id, ...meta}]
  match:   (id) => `cntv2_match_${id}`,
};
const read  = (k, def) => { try { return JSON.parse(localStorage.getItem(k)) ?? def; } catch { return def; } };
const write = (k, v) => localStorage.setItem(k, JSON.stringify(v));

// ---------- Equips ----------
export function getTeams() {
  const t = read(K.teams, null);
  if (!t) { write(K.teams, TEAMS_SEED); return TEAMS_SEED; }
  return t;
}
export function getTeam(id) { return getTeams().find(t => t.id === id); }
export function saveTeams(teams) { write(K.teams, teams); }

// ---------- Plantilla (roster) ----------
export function getRoster(teamId) { return read(K.roster(teamId), []); }
export function saveRoster(teamId, players) {
  players = players.slice().sort((a, b) => a.num - b.num);
  write(K.roster(teamId), players);
}

// ---------- Partits ----------
export function listMatches() {
  return read(K.matches, []).sort((a, b) => b.data - a.data);
}
export function getMatch(id) { return read(K.match(id), null); }

export function saveMatch(match) {
  match.lastUpdate = Date.now();
  write(K.match(match.id), match);
  const idx = read(K.matches, []).filter(m => m.id !== match.id);
  idx.push(matchMeta(match));
  write(K.matches, idx);
}
export function deleteMatch(id) {
  localStorage.removeItem(K.match(id));
  write(K.matches, read(K.matches, []).filter(m => m.id !== id));
}
function matchMeta(m) {
  return { id: m.id, teamId: m.teamId, data: m.data, rival: m.rival,
           location: m.location, competicio: m.competicio, estat: m.estat,
           scoreCNT: m.scoreCNT, scoreRival: m.scoreRival, synced: !!m.synced };
}

// ---------- Crear partit ----------
export function slug(s) {
  return (s || "").toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "")
    .replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "");
}
export function newMatch({ teamId, rival, location, competicio, data }) {
  const d = data ? new Date(data).getTime() : Date.now();
  const ymd = new Date(d).toISOString().slice(0, 10);
  const id = `${teamId}_${ymd}_${slug(rival)}`;
  const roster = getRoster(teamId);
  const match = {
    id, teamId, temporada: SEASON, data: d,
    rival: rival || "Rival", rivalSlug: slug(rival),
    location: location || "home", competicio: competicio || "lliga",
    estat: "live",
    scoreCNT: 0, scoreRival: 0,
    periodScores: QUARTERS.map(() => ({ cnt: 0, rival: 0 })),
    tempsMort: { cnt: 0, rival: 0 },
    lineups: { q1: [], q2: [], q3: [], q4: [] },
    currentQuarter: "q1",
    observacions: "",
    actions: [],
    players: roster.map(p => blankStat(p.num, p.nom, "cnt")),
    synced: false,
    lastUpdate: Date.now(),
  };
  return match;
}

function blankStat(num, nom, team) {
  return {
    num, nom, team,
    gols: 0, goalTypes: { normal: 0, "h+": 0, penalty: 0, contra: 0, boya: 0 },
    exclusions: 0, exclusionTypes: { normal: 0, penalty: 0 },
    penaltyMissed: 0, parades: 0, tempsJoc: 0,
  };
}

// ---------- Accions (registre cronològic) ----------
// action = { id, timestamp, quarter, type, team, playerNum, playerName, goalType?, exclusionType? }
export function addAction(match, action) {
  action.id = action.id || `a_${action.timestamp}_${Math.round(action.playerNum || 0)}_${match.actions.length}`;
  match.actions.push(action);
  recompute(match);
  return match;
}
export function removeAction(match, actionId) {
  match.actions = match.actions.filter(a => a.id !== actionId);
  recompute(match);
  return match;
}

// Recalcula marcador + estadístiques a partir del registre d'accions.
export function recompute(match) {
  match.scoreCNT = 0; match.scoreRival = 0;
  match.periodScores = QUARTERS.map(() => ({ cnt: 0, rival: 0 }));

  // Base CNT = plantilla completa (perquè surtin també amb 0)
  const roster = getRoster(match.teamId);
  const map = new Map();
  roster.forEach(p => map.set(`cnt_${p.num}`, blankStat(p.num, p.nom, "cnt")));

  const ensure = (team, num, name) => {
    const key = `${team}_${num}`;
    if (!map.has(key)) map.set(key, blankStat(num, name || `#${num}`, team));
    const s = map.get(key);
    if (name && (!s.nom || s.nom.startsWith("#"))) s.nom = name;
    return s;
  };

  for (const a of match.actions) {
    const qi = Math.max(0, QUARTERS.indexOf(a.quarter));
    const s = ensure(a.team, a.playerNum, a.playerName);
    switch (a.type) {
      case "goal":
        s.gols++; if (a.goalType) s.goalTypes[a.goalType]++;
        if (a.team === "cnt") { match.scoreCNT++; match.periodScores[qi].cnt++; }
        else { match.scoreRival++; match.periodScores[qi].rival++; }
        break;
      case "exclusion":
        s.exclusions++; if (a.exclusionType) s.exclusionTypes[a.exclusionType]++;
        break;
      case "penalty-missed": s.penaltyMissed++; break;
      case "save": s.parades++; break;
    }
  }
  match.players = [...map.values()];
  return match;
}

// ---------- Sync a Firestore ----------
// Escriu el partit + subcol·leccions. Graceful si Firestore no està actiu.
export async function syncMatch(match, fb) {
  const { db, doc, setDoc, writeBatch, collection } = fb;
  const mref = doc(db, "matches", match.id);
  await setDoc(mref, {
    teamId: match.teamId, temporada: match.temporada, data: match.data,
    competicio: match.competicio, rival: match.rival, rivalSlug: match.rivalSlug,
    location: match.location, estat: match.estat,
    scoreCNT: match.scoreCNT, scoreRival: match.scoreRival,
    periodScores: match.periodScores, tempsMort: match.tempsMort,
    lineups: match.lineups, observacions: match.observacions,
    lastUpdate: Date.now(),
  });
  const batch = writeBatch(db);
  match.players.forEach(p => {
    batch.set(doc(db, "matches", match.id, "playerStats", `${p.team}_${p.num}`), p);
  });
  match.actions.forEach(a => {
    batch.set(doc(db, "matches", match.id, "actions", a.id), a);
  });
  await batch.commit();
  match.synced = true;
  saveMatch(match);
}
