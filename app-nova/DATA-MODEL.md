# Model de dades — App nova (v2)

Contracte compartit: l'**app d'entrada** escriu, l'**app principal** llegeix.
Basat en l'estructura real de la temporada 25-26, generalitzat a multi-categoria
i ampliat amb parades / temps de joc / zones.

## Backend

- **Firestore** com a font única (històric + partit en curs). Un sol sistema,
  més simple que separar RTDB/JSON. Els listeners de Firestore ja donen temps
  real suficient per l'ús (un anotador + uns quants espectadors).
- Estratègia de l'app d'entrada: **offline-first**. Es treballa sobre
  `localStorage` (funciona sense connexió a la piscina) i se sincronitza a
  Firestore quan hi ha xarxa. Mai es perd un partit per falta de cobertura.

## Col·leccions

```
clubs/cnt
  └─ meta { nom, escut }

teams/{teamId}                 // teamId: "alevi" | "infantil" | "cadet" | "juvenil" | "absolut"
  {
    categoria: "cadet",
    genere: "masculi" | "femeni",
    temporada: "2026-27",
    entrenador: "…",
    font: "fcn" | "rfen",       // només per validació federativa (fase futura)
    sourceId: "…",              // id competició a la federació
    accentColor: "#0891b2",     // color de tema per categoria
    actiu: true
  }

teams/{teamId}/players/{playerId}       // plantilla persistent (no per partit)
  { numero: 4, nom: "…", posicio: "…", actiu: true }

matches/{matchId}                        // matchId = `${teamId}_${YYYY-MM-DD}_${rivalSlug}`
  {
    teamId: "cadet",
    temporada: "2026-27",
    data: <timestamp>,
    competicio: "lliga" | "copa" | "campionat" | "amistos",
    rival: "CN Montjuic",
    rivalSlug: "cn_montjuic",
    location: "home" | "away",
    estat: "live" | "finished",
    scoreCNT: 21,
    scoreRival: 8,
    periodScores: [ {cnt,rival}, … ],    // un per quart
    tempsMort: { cnt: 0, rival: 2 },
    lineups: { q1:[nums], q2:[…], q3:[…], q4:[…] },
    observacions: "",
    lastUpdate: <timestamp>              // per detectar "en directe"
  }

matches/{matchId}/playerStats/{docId}    // agregat per jugador (CNT i rival)
  {
    num: 1, nom: "DAVID CASADO", team: "cnt" | "rival",
    gols: 0,
    goalTypes:      { normal:0, "h+":0, penalty:0, contra:0, boya:0 },
    exclusions: 0,
    exclusionTypes: { normal:0, penalty:0 },
    penaltyMissed: 0,
    parades: 0,                          // porters
    tempsJoc: 0                          // segons
  }

matches/{matchId}/actions/{actionId}     // registre cronològic d'events
  {
    timestamp: <ms>,
    quarter: "q1" | "q2" | "q3" | "q4" | "p1"…,   // suport pròrrogues
    type: "goal" | "exclusion" | "penalty-missed" | "save" | "timeout" | "sub",
    team: "cnt" | "rival",
    playerNum: 11, playerName: "…",
    goalType?: "normal" | "h+" | "penalty" | "contra" | "boya",
    exclusionType?: "normal" | "penalty",
    zona?: <int>                          // zona de gol/camp (heatmaps)
  }
```

## Notes de disseny

- **`playerStats` és derivable** de `actions` (es pot recalcular). Es desa
  igualment per lectures ràpides a l'app principal sense recórrer tots els events.
- **Multi-categoria sense hardcoding**: afegir un equip = un document a `teams/`.
  La UI llegeix `teams/` i pinta un selector; el color surt d'`accentColor`.
- **Zones i parades** ja queden al model des del principi, encara que la primera
  versió de l'entrada no les capturi totes — així no cal migrar després.
- **Federació**: els camps `font`/`sourceId` són per la fase de validació (quan
  les webs FCN/RFEN tornin a estar actives). Ara no es toca.

## Seguretat (Firestore rules, resum)

- Lectura pública de `teams/`, `matches/` i subcol·leccions (l'app principal és oberta).
- Escriptura només autenticada (Firebase Auth) → l'app d'entrada. Evita que
  qualsevol pugui modificar estadístiques.
