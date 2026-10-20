"""Tests hors-ligne des lecteurs, avec des réponses au format réel des sites."""
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import collect as c  # noqa: E402

H = Path(__file__).parent
today = datetime.now(c.TZ).date()
c.JOURS = 2


class Fake:
    def __init__(self, routes):
        self.routes, self.calls = routes, []

    def get(self, url, headers=None):
        self.calls.append(url)
        for k, v in self.routes.items():
            if k in url:
                return v(url) if callable(v) else v
        raise AssertionError("route manquante: " + url)

    def post_json(self, url, payload, headers=None):
        self.calls.append((url, payload))
        for k, v in self.routes.items():
            if k in url:
                return v(payload)
        raise AssertionError("route manquante: " + url)


def check(nom, cond):
    print(("OK  " if cond else "ÉCHEC ") + nom)
    if not cond:
        global echecs
        echecs += 1


echecs = 0

# ── Tennis Online : Fairplay (une colonne d'heures commune) ──
fp = (H / "fixture_fairplay.html").read_text()
r = c._parse_tennisonline(fp, today, {"nom": "Fairplay", "ville": "Puidoux", "prix": "60 CHF / 90 min"}, "u")
p1 = [x["debut"][11:] for x in r if x["court"] == "Padel 1"]
check("Fairplay Padel 1 libres", p1 == ["09:00", "10:30", "13:30", "15:00", "21:00"])
check("Fairplay durée 90", all(x["durees"][0]["min"] == 90 for x in r))
check("Fairplay Padel 2", len([x for x in r if x["court"] == "Padel 2"]) == 5)

# ── Tennis Online : Green Club (colonnes d'heures par terrain) ──
gc = (H / "fixture_green.html").read_text()
r = c._parse_tennisonline(gc, today, {"nom": "Green", "ville": "Romanel"}, "u")
check("Green n°1", [x["debut"][11:] for x in r if x["court"] == "Padel n°1"] == ["10:15", "12:15"])
check("Green n°4 90 min", [(x["debut"][11:], x["durees"][0]["min"]) for x in r if x["court"] == "Padel n°4"]
      == [("08:45", 90), ("11:45", 90)])

# ── Tennis Online : navigation jours ──
tok_demain = "TOKDEMAIN"
accueil = '<a href="tableau_padel.php?responsive=false&amp;d=TOK0">Padel</a>'
jour0 = fp.replace(">Me 21<", f">Xx {(today + timedelta(days=1)).day}<").replace("ZwNlAv0kZP0lZD==", tok_demain)
f = Fake({"tableau.php": accueil, "d=TOK0": jour0, f"d={tok_demain}": fp})
r = c.tennisonline({"nom": "Fairplay", "ville": "P", "base": "https://x"}, f)
jours_vus = sorted({x["debut"][:10] for x in r})
check("Tennis Online 2 jours", jours_vus == [str(today), str(today + timedelta(days=1))])

# ── Plugin.ch ──
home = '<a class="x" href="https://p/dashboard/sport/272/2096"><b>Tennis</b></a><a href="https://p/dashboard/sport/299/2165">Padel <small>Padel 2026</small></a>'


def dash(_):
    cells = "".join(f'<div class="slot free" id="1_{h}" data-terrain="1" data-heure="{h}" data-atrname="Padel"></div>'
                    for h in ["1700", "1730", "1800", "1830", "2000", "2030"])
    cells += '<div class="slot book" data-heure="1900" data-atrname="Padel"><span class="slot-time">19:00</span></div>'
    return cells


f = Fake({"dashboardV2": lambda u: home if not any("sport/299" in str(x) for x in f.calls[:-1]) else dash(u),
          "sport/299": "", "dashboard/date": ""})
r = c.plugin({"nom": "TC", "ville": "L", "base": "https://p", "prix": "42 CHF/h"}, f)
d0 = [(x["debut"][11:], [y["min"] for y in x["durees"]]) for x in r if x["debut"][:10] == str(today)]
check("Plugin catégorie Padel choisie", any("sport/299/2165" in str(x) for x in f.calls))
check("Plugin créneaux", d0 == [("17:00", [60, 90]), ("17:30", [60, 90]), ("18:00", [60]), ("20:00", [60])])

# ── Matchpoint ──
grid = "<script>\n//<![CDATA[\nhl90njda2b89k='eNEe29kXfZBL0pXBd1U4YgbPPQMRMSwaQEeW1v1rIUTglvloaKL4JA==';var __cultureInfo = {}"
cuadro = {"d": {"Columnas": [{"TextoPrincipal": "Terrain 1", "HorariosFijos": [
    {"StrHoraInicio": "21:15", "Minutos": 90}, {"StrHoraInicio": "09:15", "Minutos": 60}]}]}}
f = Fake({"Grid.aspx": grid, "ObtenerCuadros": lambda p: {"d": [{"Id": 4, "Nombre": "Padel"}]},
          "ObtenerCuadro": lambda p: cuadro})
r = c.matchpoint({"nom": "Urban", "ville": "L", "base": "https://m"}, f)
check("Matchpoint clé", f.calls[1][1]["key"].startswith("eNEe29"))
check("Matchpoint date fr", f.calls[2][1]["fecha"] == today.strftime("%d/%m/%Y"))
check("Matchpoint créneaux", sorted(x["debut"][11:] for x in r if x["debut"][:10] == str(today)) == ["09:15", "21:15"])

# ── Playtomic ──
page = ('x \\"tenant_id\\":\\"dbfb6961-6d55-4075-baae-f5966c0e4f03\\" y '
        '\\"resourceId\\":\\"502a3a3e-ac6d-4bdb-9a1c-c05c56644f97\\",\\"name\\":\\"Single Padel\\",'
        '\\"sport\\":\\"PADEL\\",\\"features\\":[\\"indoor\\",\\"single\\",\\"panoramic\\"]}')
av = json.dumps([{"resource_id": "502a3a3e-ac6d-4bdb-9a1c-c05c56644f97", "start_date": str(today), "slots": [
    {"start_time": "16:00:00", "duration": 30, "price": "20 CHF"},
    {"start_time": "16:00:00", "duration": 60, "price": "40 CHF"},
    {"start_time": "16:00:00", "duration": 90, "price": "60 CHF"}]}])
f = Fake({"/fr/clubs/": page, "api/clubs/availability": av})
r = c.playtomic({"nom": "Prev", "ville": "P", "slug": "padel-parc-preverenges"}, f)
x = [y for y in r if y["debut"][:10] == str(today)][0]
check("Playtomic UTC→local", x["debut"][11:] in ("17:00", "18:00"))
check("Playtomic durées", [(d["min"], d["prix"]) for d in x["durees"]] == [(60, "40 CHF"), (90, "60 CHF")])
check("Playtomic tag single", x["tags"] == ["single"] and x["court"] == "Single Padel")

print("\n" + ("Tout est OK" if not echecs else f"{echecs} échec(s)"))
sys.exit(1 if echecs else 0)
