# Padel libre

Créneaux de padel libres autour de Lausanne, mis à jour toutes les 15 minutes (6h–minuit). Usage privé.
Page : https://hector347321.github.io/padel-dispo/

| Système | Clubs | Où ça tourne |
|---|---|---|
| Matchpoint | Urban Padel Lausanne | GitHub |
| Tennis Online | Green Club Romanel, Centre Fairplay Puidoux | GitHub |
| Plugin.ch | TC Stade-Lausanne, TC Morges | GitHub |
| Playtomic | Padel Parc Préverenges, Etoy, Yverdon, Vaudoise aréna, Padel One Payerne | **Mac** (Playtomic refuse les serveurs GitHub) |
| — | Padel One Echandens | lien seulement (réservation via leur app) |

## Sur iPhone
Safari → la page → Partager → **Sur l'écran d'accueil**. Filtres (jour, heures, durée, clubs) mémorisés sur le téléphone.

## Alertes (dates précises)
Bouton **🔔 Alertes** sur la page : choisis une ou plusieurs dates, une plage horaire, une durée et éventuellement des clubs.
Une notification ntfy part **uniquement** quand un créneau se libère dans une de ces plages. Les dates passées sont retirées automatiquement.
L'enregistrement se fait dans `alertes.json` via un jeton GitHub (fine-grained, ce dépôt seulement, *Contents : Read and write*), saisi une fois sur le téléphone.

## Partie Mac (Playtomic)
```
bash <(curl -fsSL https://raw.githubusercontent.com/hector347321/padel-dispo/main/mac/installer.sh)
```
Demande le même jeton GitHub. Tourne toutes les 15 min quand le Mac est allumé et télécharge toujours la dernière version du collecteur.

## Fichiers
- `collect.py` : collecteur (Python, sans dépendance). `python3 collect.py` (GitHub) · `python3 collect.py --mac` (Playtomic)
- `docs/` : la page (`index.html`), `data.json` (GitHub), `playtomic.json` (Mac)
- `alertes.json` : tes alertes
- `.github/workflows/collect.yml` : exécution toutes les 15 min
- `tests/test_collect.py` : tests hors-ligne des lecteurs
