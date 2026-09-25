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
├─ acta/            ACTA EN DIRECTE: gols, exclusions i canvis + comparació amb l'acta FCN
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
- Acta en directe:  http://localhost:8000/app-nova/acta/
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

## Acta en directe (`acta/`) i lector de l'acta FCN

App lleugera per a la piscina: per jugador, gol (⚽) i exclusió (EX), amb toast
per precisar el tipus com a l'acta (penal, falta de penal, excl.+penal,
brutalitat, definitiva); tocar el nom = dins/fora (temps de joc) i 🔄 canvi guiat.
Tot és un registre d'accions (`acts`) a `localStorage` (`acta_v1_*`), d'on es
deriven marcador, parcials, titulars i temps. Agafa la plantilla de l'entrada
(`cntv2_roster_juvenil`).

**Només Juvenil, equip `C.N. TERRASSA A`** (el B i les altres categories estan
fora; per tornar-les a afegir: `CATS`/`CNT_TEAM` a l'acta i
`TOURNAMENTS`/`CNT_TEAMS` a `actawp_live.py`).

**Font de l'app d'estadístiques (`app/`):** cada canvi es publica (4 s de
debounce, REST sense SDK) a Firestore `matches/acta_<id>` amb `source:'acta'`,
en el mateix format que l'entrada v2 (`jugadors`, `periodScores`,
`chronologicalActions`, `lineups`, `playerWaterChanges`...). El temps es
converteix a temps de joc (cada quart acabat = 8:00 exactes), així
`calculateMatchPlayingTimes` de l'app dona els mateixos minuts que l'acta.
Cada jugador porta també `estadistiques.acta` (totes les columnes) i el
partit, `fcn` (còpia de l'acta oficial). L'app `app/` només mostra Juvenil i
només partits amb `source:'acta'`.

La pestanya **🆚 Acta FCN** compara amb la federació (l'ACTAWP és Leverade):
- **Equip** (marcador, parcials, quarts acabats): API pública
  `api.leverade.com` directament des del mòbil, cada 30 s durant el partit.
- **Jugador** (totes les columnes de l'acta: G, GP, G5P, EX, P, EP, ED, EB, EN,
  PF, TG, TV...): la pàgina `stats` de l'ACTAWP té anti-bot i no permet CORS,
  així que la llegeix [`actawp_live.py`](../actawp_live.py) amb Chrome headless
  i la publica a la **RTDB** `federacio/{matchId}`; l'app l'escolta amb
  `EventSource` (streaming REST, sense SDK).

On corre el lector:
1. **GitHub Actions** ([`.github/workflows/actawp_live.yml`](../.github/workflows/actawp_live.yml)):
   cada 15 min mira el calendari; si hi ha un partit del CNT a punt (25 min
   abans) o en joc, el segueix fins que acaba. Necessita el secret
   `FIREBASE_SERVICE_ACCOUNT` (JSON del compte de servei de Firebase).
2. **PC (reserva)** si l'anti-bot bloqueja GitHub:
   `python actawp_live.py --watch --key C:\ruta\clau.json`
   (`pip install beautifulsoup4 firebase-admin`).

Proves sense credencials: `python actawp_live.py --dry-run --match <id> --tournament <id>`
desa el JSON a `app-nova/data/federacio/`, que l'app llegeix com a reserva en local.

## Pendent (properes fases)

- Firebase Auth a l'app d'entrada (només entrenadors escriuen).
- Escriptura de plantilles/equips a Firestore (ara només local).
- Zones de gol/camp i temps de joc a l'entrada.
- App principal: llegir de Firestore, selector de categoria, gràfics, temporada.
- Federació (FCN/RFEN) per validació — quan les webs tornin a estar actives.
