# Padel libre

Créneaux de padel libres autour de Lausanne, mis à jour toutes les 15 minutes (6h–minuit). Usage privé.

**Clubs suivis** : Padel Parc Préverenges, Etoy, Yverdon, Vaudoise aréna (Playtomic) · Padel One Payerne (Playtomic) · Urban Padel Lausanne (Matchpoint) · Green Club Romanel et Centre Fairplay Puidoux (Tennis Online) · TC Stade-Lausanne et TC Morges (Plugin.ch) · Padel One Echandens (lien seulement, réservation via leur app).

## Sur iPhone
1. Ouvre la page dans **Safari** : `https://<ton-pseudo>.github.io/padel-dispo/`
2. Bouton Partager → **Sur l'écran d'accueil**. Elle s'ouvre ensuite comme une app.
3. Filtres (jour, heures, durée, clubs) : ils sont mémorisés sur le téléphone.

## Notifications
- Installe l'app gratuite **ntfy** et abonne-toi au sujet enregistré dans le secret `NTFY_TOPIC` du dépôt.
- Les règles sont dans `alertes.json` (modifiable directement sur github.com, icône crayon) :
  jours, plage horaire, durée minimale, clubs. Une notification part **seulement** quand un créneau
  se libère et correspond à une règle.

## Fichiers
- `collect.py` : récupère les créneaux (Python, sans dépendance) → `docs/data.json`
- `docs/index.html` : la page iPhone
- `alertes.json` : tes règles de notification
- `.github/workflows/collect.yml` : exécution automatique toutes les 15 min
- `tests/` : `python3 tests/test_collect.py`

Lancer à la main : `python3 collect.py`
