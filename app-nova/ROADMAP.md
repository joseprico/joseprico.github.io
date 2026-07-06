# App nova — CN Terrassa Waterpolo Stats (v2)

Reconstrucció de zero de l'app d'estadístiques, multi-categoria i escalable.
L'històric 25-26 es conserva congelat a `../historic-2025-26/`.

## Objectiu

Una plataforma que cobreixi **totes les categories** del club (aleví, infantil,
cadet, juvenil, absolut), amb:

- Base de dades centralitzada i escalable (no repos JSON dispersos).
- Entrada de dades pròpia millorada (font primària de les estadístiques).
- Disseny clar (tema light per defecte, accent de color per categoria).

## Decisions preses

| Tema | Decisió |
|---|---|
| **Base de dades** | **Firestore** per l'històric (estructurat, consultable, multi-equip). RTDB es manté només pel live. Reutilitzar el projecte Firebase `cnt-wp-stats-bb7dc` (activar Firestore + pla Blaze). |
| **Ingesta federació** | **Cloud Functions 2a gen en Python** (reaprofitar `ultra_robust_parser.py` / Leverade). Programades. **Només per validar** dades, no són la font. |
| **Frontend** | **Híbrid**: nucli vanilla + build lleuger (Vite + Web Components/Lit) a `app-nova/`, en paral·lel a l'app actual. Migració categoria a categoria. |
| **Abast inicial** | **Prova de concepte** amb una categoria abans d'escalar a les 5. |
| **Font de dades** | Les estadístiques surten **SEMPRE de la nostra app** (seguiment partit a partit). La federació (FCN / RFEN-Leverade) només serveix per **validar** resultats/classificació. |

## Realitat temporal (important)

Les webs de la federació catalana (FCN/ACTAWP) i RFEN **no estan muntades fins
a l'inici de temporada**. Per tant, ara **no es pot connectar amb la federació**.

**Focus actual**: millorar l'**entrada de dades** i tot el que NO depengui de la
federació. La part de Cloud Functions + Leverade/ACTAWP queda per quan les webs
tornin a estar actives (inici temporada 2026-27).

## Model de dades (esborrany Firestore)

```
clubs/cnt/
  teams/{teamId}          -> { categoria: "cadet"|"juvenil"|..., temporada,
                               entrenador, font: "fcn"|"rfen", sourceId, accentColor }
  matches/{matchId}       -> { teamId, data, rival, competicio,
                               scoreCNT, scoreRival, periodScores, ... }
     .../actions/{...}     (subcol·leccio: gols, exclusions, parades, temps...)
     .../players/{...}
  players/{playerId}      -> normalitzats per club
live/{matchId}            (RTDB, com ara)
```

Sense hardcoding de Cadet/Juvenil: afegir categoria = un document a `teams/`.
La UI passa d'un toggle Cadet/Juvenil a un **selector de categoria** genèric.

## Fases

1. **[EN CURS] Entrada de dades v2** — millorar l'app d'entrada (partint de
   `waterpolo_app_entrada_dades_ct.html` com a referència), escrivint a Firestore,
   amb Firebase Auth, validació i offline. Sense federació.
2. **Model Firestore + migració** — definir col·leccions, migrar l'històric útil.
3. **Frontend v2** — vista de lectura amb disseny clar, multi-categoria.
4. **Federació (quan torni)** — Cloud Functions Python (Leverade/ACTAWP) → Firestore,
   només per validar.

## Referències al repo

- `../historic-2025-26/index.html` — app antiga completa (referència de features/stats).
- `../waterpolo_app_entrada_dades_ct.html` — app d'entrada de dades actual (punt de partida).
- `../_reference/cnt_cadet_25-26/` — scripts Python i JSON de dades de la temporada.
