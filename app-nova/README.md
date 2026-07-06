# App nova (v2) — CN Terrassa Waterpolo

Reconstrucció multi-categoria. Veure [ROADMAP.md](ROADMAP.md) i
[DATA-MODEL.md](DATA-MODEL.md).

## Estructura

```
app-nova/
├─ shared/          codi compartit entre les dues apps
│  ├─ theme.css     sistema de disseny (light, net i minimalista)
│  ├─ firebase.js   connexió Firebase/Firestore (projecte cnt-wp-stats-bb7dc)
│  └─ store.js      model de dades + magatzem (localStorage) + sync Firestore
├─ entrada/         APP D'ENTRADA DE DADES (escriu)
│  └─ index.html
└─ app/             APP PRINCIPAL (llegeix) — primera llesca
   └─ index.html
```

## Provar en local

Les apps usen mòduls ES (`import`), que **no funcionen amb `file://`**.
Cal servir la carpeta amb un servidor HTTP local:

```bash
# des de l'arrel del repo
python -m http.server 8000
# o:  npx serve .
```

Després obrir:
- Entrada de dades: http://localhost:8000/app-nova/entrada/
- App principal:    http://localhost:8000/app-nova/app/

Totes dues comparteixen el mateix `localStorage`, així que un partit registrat
a l'app d'entrada apareix immediatament a l'app principal (mateix navegador).

## Estat actual (offline-first)

- ✅ Funciona **100% offline** amb `localStorage` (font de veritat).
- ✅ Entrada: categories, plantilla, crear partit, registrar gols/exclusions/
  penals fallats/parades per jugador i quart, marcador i parcials automàtics,
  registre cronològic amb desfer, finalitzar partit.
- ✅ App principal: llista de partits, detall amb marcador, parcials, golejadors
  i taula d'estadístiques CNT.
- ⏳ Sync a Firestore: el codi hi és (`store.syncMatch` + botó ☁️), però cal
  **activar Firestore a la consola** perquè funcioni (veure sota).

## Activar Firestore (quan es vulgui sync al núvol)

1. Firebase console → projecte `cnt-wp-stats-bb7dc`.
2. Build → **Firestore Database** → *Create database* (regió `europe-west1`,
   mode producció).
3. Regles inicials (lectura pública, escriptura autenticada):
   ```
   rules_version = '2';
   service cloud.firestore {
     match /databases/{database}/documents {
       match /{document=**} {
         allow read: if true;
         allow write: if request.auth != null;   // afegir Firebase Auth a l'entrada
       }
     }
   }
   ```
   *(Per començar a provar ràpid es pot posar `allow write: if true;` i endurir després.)*
4. El botó ☁️ de l'app d'entrada ja escriurà a `matches/` i subcol·leccions.

## Pendent (properes fases)

- Firebase Auth a l'app d'entrada (només entrenadors escriuen).
- Escriptura de plantilles/equips a Firestore (ara només local).
- Zones de gol/camp i temps de joc a l'entrada.
- App principal: llegir de Firestore, selector de categoria, gràfics, temporada.
- Federació (FCN/RFEN) per validació — quan les webs tornin a estar actives.
