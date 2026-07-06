// ============================================================
// CN Terrassa Waterpolo · App v2 · Connexió Firebase / Firestore
// Reutilitza el projecte existent (cnt-wp-stats-bb7dc).
// IMPORTANT: cal activar Firestore a la consola de Firebase
//   (Build > Firestore Database > Create database) i pujar al pla Blaze
//   si es volen Cloud Functions més endavant. La lectura/escriptura
//   funcionarà quan Firestore estigui actiu; mentrestant l'app treballa
//   offline amb localStorage.
// ============================================================

import { initializeApp } from "https://www.gstatic.com/firebasejs/10.7.1/firebase-app.js";
import {
  getFirestore, collection, doc,
  setDoc, getDoc, getDocs, deleteDoc,
  onSnapshot, serverTimestamp, writeBatch, query, where, orderBy
} from "https://www.gstatic.com/firebasejs/10.7.1/firebase-firestore.js";

const firebaseConfig = {
  apiKey: "AIzaSyCmJwgJvh10LcpPjeWhLbN5EDYeHT3tAoU",
  authDomain: "cnt-wp-stats-bb7dc.firebaseapp.com",
  databaseURL: "https://cnt-wp-stats-bb7dc-default-rtdb.europe-west1.firebasedatabase.app",
  projectId: "cnt-wp-stats-bb7dc",
  storageBucket: "cnt-wp-stats-bb7dc.firebasestorage.app",
  messagingSenderId: "3430713575",
  appId: "1:3430713575:web:d580671a5d19049b187a42",
  measurementId: "G-VZVL8MZV4K"
};

const app = initializeApp(firebaseConfig);
export const db = getFirestore(app);

export {
  collection, doc, setDoc, getDoc, getDocs, deleteDoc,
  onSnapshot, serverTimestamp, writeBatch, query, where, orderBy
};

// Comprova si Firestore respon (per mostrar l'estat de sync a la UI).
export async function firestoreOnline() {
  try {
    await getDoc(doc(db, "clubs", "cnt"));
    return true;
  } catch (e) {
    console.warn("Firestore no disponible:", e.message);
    return false;
  }
}
