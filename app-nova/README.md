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
└─ app/             ESTADÍSTIQUES (llegeix): acta nostra vs acta FCN, per partit i totals
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
- ✅ Estadístiques (`app/`, refeta l'octubre del 2026): partits jugats i totals per
  jugador (vegeu sota).
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
partit, `fcn` (còpia de l'acta oficial).

**App d'estadístiques (`app/`)**, mateix disseny que l'acta, sense SDK:
llegeix les actes (`matches` amb `source:'acta'`, només Juvenil) i, per a cada
partit, l'acta oficial de la RTDB `federacio/{matchId}` (si no hi és, la còpia
`fcn`). Pestanya **Partits** (resum de temporada i un partit per fila amb
"✓ quadra / ≠ N dif.") i **Jugadors** (PJ, titularitats, minuts, gols i
expulsions). Gols i expulsions sempre els nostres; en vermell, `nosaltres · FCN`
quan no quadra. Expulsions = EX + P + EP (com el botó EX de l'acta). Minuts i
titulars només surten de la nostra acta (`lineups` + `playerWaterChanges`). Els
totals agrupen per nom (el dorsal pot canviar). Els partits que el lector ha
llegit però sense acta nostra surten com a "només FCN" i no compten als totals.

**Corregir una acta ja penjada** (botó ✏️ al detall del partit, des de
qualsevol mòbil): pestanyes *Gols i expulsions* (canviar jugador, quart o
tipus d'una acció, esborrar-ne, afegir-ne; amb les diferències amb la FCN com a
pista) i *Titulars i canvis* (els 7 de l'inici de cada quart i els canvis amb
el seu temps de joc; avisa dels trams de ≥10 s amb ≠7 a l'aigua). L'app passa
l'acta a un format editable (`normalize`: accions `{q, team, num, k}` i, per
quart, `{len, start, changes:[{t, num, dir}]}`) i en calcula tot (marcador,
parcials, minuts, titulars). Les correccions es desen senceres a Firestore
`matches/edit_<id de l'acta>` amb `source:'acta_edit'` i **sense `teamId`**
(les regles només deixen escriure a `matches`; sense `teamId` cap altra app
les llista) i l'app les fa servir en lloc de l'acta, també als totals. El
mòbil de l'acta no les veu; si l'acta es torna a penjar, manen les
correccions (l'app ho avisa). "↺ Original" les esborra.

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
   el cron demana cada 15 min, però **GitHub només n'executa una cada 3-9 h**
   (el 07/10/2026 el lector va arribar al tercer quart). Per això la primera
   execució que veu un partit del CNT en les **12 h** següents s'hi queda
   esperant (a la RTDB, `lector.status:'waiting'` + `connectAt`), es connecta a
   l'acta **2 h abans** i el segueix fins que acaba; si no hi cap abans del
   límit de 6 h d'una feina, n'engega una altra (relleu amb
   `gh workflow run`). L'acta avisa "⚠️ lector sense connectar" si 1 h 40 min
   abans encara no ha llegit res. Necessita el secret
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
- Federació (FCN/RFEN) per validació — quan les webs tornin a estar actives.
