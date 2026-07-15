// ============================================================
// CN Terrassa · App v2 · API de dades Firestore
// Font única dels partits (multi-categoria). L'app d'entrada
// PUBLICA aquí; l'app principal LLEGEIX d'aquí.
//   matches/{matchId}  ->  { ...dadesDelPartit, teamId, data, temporada }
// Reutilitza el projecte cnt-wp-stats-bb7dc. Cal activar Firestore
// a la consola (Build > Firestore Database > Create database).
// ============================================================

import { initializeApp, getApps, getApp } from "https://www.gstatic.com/firebasejs/10.7.1/firebase-app.js";
import {
  getFirestore, collection, doc, setDoc, getDoc, getDocs
} from "https://www.gstatic.com/firebasejs/10.7.1/firebase-firestore.js";

const firebaseConfig = {
  apiKey: "AIzaSyCmJwgJvh10LcpPjeWhLbN5EDYeHT3tAoU",
  authDomain: "cnt-wp-stats-bb7dc.firebaseapp.com",
  databaseURL: "https://cnt-wp-stats-bb7dc-default-rtdb.europe-west1.firebasedatabase.app",
  projectId: "cnt-wp-stats-bb7dc",
  storageBucket: "cnt-wp-stats-bb7dc.firebasestorage.app",
  messagingSenderId: "3430713575",
  appId: "1:3430713575:web:d580671a5d19049b187a42",
};

// Reutilitza l'app si ja existeix (evita "app already exists")
const app = getApps().length ? getApp() : initializeApp(firebaseConfig);
export const db = getFirestore(app);

// ---- Publicar un partit (usat per l'app d'entrada) ----
export async function publishMatch(match, teamId) {
  const id = match.id || match.matchID;
  if (!id) throw new Error("El partit no té id");
  await setDoc(doc(db, "matches", id), {
    ...match, teamId, lastUpdate: Date.now(),
  });
  return id;
}

// ---- Llista de partits d'una categoria (usat per l'app principal) ----
// Sense índex compost: filtrem per teamId i ordenem al client per data desc.
export async function listMatches(teamId) {
  const snap = await getDocs(collection(db, "matches"));
  return snap.docs
    .map(d => ({ id: d.id, ...d.data() }))
    .filter(m => m.teamId === teamId)
    .sort((a, b) => new Date(b.data || 0) - new Date(a.data || 0));
}

// ---- Un partit concret ----
export async function getMatch(id) {
  const s = await getDoc(doc(db, "matches", id));
  return s.exists() ? { id: s.id, ...s.data() } : null;
}

// ---- Alineació habitual (plantilla) d'una categoria ----
//   rosters/{teamId} -> { teamId, players: [{num, name}...], lastUpdate }
// L'app d'entrada l'escriu (modal "Alineació habitual"); qualsevol app pot llegir-la.
export async function saveRoster(teamId, players) {
  await setDoc(doc(db, "rosters", teamId), { teamId, players, lastUpdate: Date.now() });
}
export async function getRoster(teamId) {
  const s = await getDoc(doc(db, "rosters", teamId));
  return s.exists() ? (s.data().players || []) : null;
}

// ---- Comprovar si Firestore respon ----
export async function firestoreOnline() {
  try { await getDocs(collection(db, "matches")); return true; }
  catch (e) { console.warn("Firestore no disponible:", e.message); return false; }
}
