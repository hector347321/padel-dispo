#!/usr/bin/env python3
"""
Collecteur de créneaux de padel libres — région lausannoise (usage privé).

Sources : Playtomic, Matchpoint, Plugin.ch, "Tennis Online" (FIT SA).
Sortie  : docs/data.json  (lu par docs/index.html, la page iPhone)
Option  : notification push via ntfy.sh si la variable NTFY_TOPIC est définie.

Python 3.9+, aucune dépendance.
"""

import http.cookiejar
import urllib.error
import json
import os
import re
import sys
import traceback
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Zurich")
JOURS = 7
ROOT = Path(__file__).resolve().parent
OUT = ROOT / "docs" / "data.json"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"

# ─────────────────────────── CLUBS ───────────────────────────
# type: playtomic | matchpoint | plugin | tennisonline | lien
CLUBS = [
    {"nom": "Padel Parc Préverenges", "ville": "Préverenges", "type": "playtomic",
     "slug": "padel-parc-preverenges", "tenant": "dbfb6961-6d55-4075-baae-f5966c0e4f03"},
    {"nom": "Padel Parc Etoy", "ville": "Etoy", "type": "playtomic",
     "slug": "padel-parc-etoy", "tenant": "6e4cde43-4fa9-45a9-9326-d94dcb526c6b"},
    {"nom": "Vaudoise aréna", "ville": "Prilly", "type": "playtomic",
     "slug": "vaudoise-arena", "tenant": "53b5aaf2-7449-4691-96f8-a582ce37144b",
     "note": "Extérieur, avril–été"},
    {"nom": "Urban Padel", "ville": "Lausanne (Beaulieu)", "type": "matchpoint",
     "base": "https://urbanpadellausanne.matchpoint.com.es",
     "prix": "Prix dans l'app"},
    {"nom": "Green Club", "ville": "Romanel", "type": "tennisonline",
     "base": "https://reservations.green-club.ch",
     "prix": "44 CHF", "note": "11 CHF/h par joueur, 5 pour les membres"},
    {"nom": "Centre Fairplay", "ville": "Puidoux", "type": "tennisonline",
     "base": "https://online.centrefairplay.ch",
     "prix": "60 CHF"},
    {"nom": "TC Stade-Lausanne", "ville": "Lausanne (Vidy)", "type": "plugin",
     "base": "https://reservation.tcstadelausanne.ch",
     "prix": "42 CHF", "note": "Extérieur, non-membres bienvenus"},
    {"nom": "TC Morges", "ville": "Morges", "type": "plugin",
     "base": "https://tcmorges.plugin.ch", "note": "Extérieur"},
    {"nom": "Padel One", "ville": "Echandens", "type": "lien",
     "url": "https://www.padel-one.ch/jouer",
     "note": "Réservation uniquement dans l'app Padel One"},
    # Un peu plus loin (désactive en mettant "off": True)
    {"nom": "Padel Parc Yverdon", "ville": "Yverdon", "type": "playtomic",
     "slug": "padel-parc-yverdon", "tenant": "4613ab9b-740d-4226-ab3a-28651fd33ef5"},
    {"nom": "Padel One Payerne", "ville": "Payerne", "type": "playtomic",
     "slug": "padel-one-payerne", "tenant": "e03e742b-c7fe-4fcf-b3de-ea555a0750e3"},
]


# ─────────────────────────── HTTP ───────────────────────────
class Session:
    def __init__(self):
        self.jar = http.cookiejar.CookieJar()
        self.op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))

    def get(self, url, headers=None):
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "fr-CH,fr;q=0.9", **(headers or {})})
        with self.op.open(req, timeout=30) as r:
            return r.read().decode("utf-8", "replace")

    def post_json(self, url, payload, headers=None):
        data = json.dumps(payload).encode()
        req = urllib.request.Request(url, data=data, method="POST", headers={
            "User-Agent": UA, "Content-Type": "application/json; charset=utf-8",
            "X-Requested-With": "XMLHttpRequest", **(headers or {})})
        with self.op.open(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8", "replace"))


def jours():
    t = datetime.now(TZ).date()
    return [t + timedelta(days=i) for i in range(JOURS)]


def slot(club, court, debut, durees, url, tags=()):
    """debut: datetime locale ; durees: liste de (minutes, prix_texte|None)"""
    return {
        "club": club["nom"], "ville": club["ville"], "court": court.strip(),
        "debut": debut.strftime("%Y-%m-%dT%H:%M"),
        "durees": [{"min": m, "prix": p} for m, p in durees],
        "url": url, "tags": list(tags),
    }


# ─────────────────────────── MINI DOM ───────────────────────────
VOID = {"br", "img", "input", "meta", "link", "hr", "area", "base", "col", "source", "wbr"}


class Node:
    __slots__ = ("tag", "attrs", "children", "parent", "text")

    def __init__(self, tag, attrs, parent):
        self.tag, self.attrs, self.children, self.parent, self.text = tag, attrs, [], parent, []

    @property
    def cls(self):
        return (self.attrs.get("class") or "").split()

    def has(self, c):
        return c in self.cls

    def els(self):
        return [c for c in self.children if isinstance(c, Node)]

    def all_text(self):
        out = []
        for c in self.children:
            out.append(c.all_text() if isinstance(c, Node) else c)
        return "".join(out)

    def walk(self):
        for c in self.els():
            yield c
            yield from c.walk()

    def find_all(self, pred):
        return [n for n in self.walk() if pred(n)]


class Tree(HTMLParser):
    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.root = Node("root", {}, None)
        self.cur = self.root
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        n = Node(tag, dict(attrs), self.cur)
        self.cur.children.append(n)
        if tag not in VOID:
            self.cur = n

    def handle_endtag(self, tag):
        n = self.cur
        while n is not self.root and n.tag != tag:
            n = n.parent
        if n is not self.root:
            self.cur = n.parent

    def handle_data(self, data):
        self.cur.children.append(data)


# ─────────────────────────── PLAYTOMIC ───────────────────────────
# Terrains connus (lus sur playtomic.com le 20.10.2026) : permet d'interroger les
# disponibilités sans charger la page du club, que Playtomic refuse aux serveurs.
PLAYTOMIC_COURTS = {
    "dbfb6961-6d55-4075-baae-f5966c0e4f03": {
        "01103cf2-06e8-4517-8b5d-8725d86b240d": ("Padel 1 - ACE Electroménager", []),
        "887ab023-f4d0-4119-ac44-debbda270f59": ("Padel 2 - Entretiens Rodriguez", []),
        "4ef0b95b-f071-4da1-aa4f-b9f5481435dc": ("Padel 3", []),
        "502a3a3e-ac6d-4bdb-9a1c-c05c56644f97": ("Single Padel", ["single"])},
    "6e4cde43-4fa9-45a9-9326-d94dcb526c6b": {
        "1445aa3a-9976-4ea1-8b74-48fd58a15e87": ("1 - GROUPE FACCHINETTI", []),
        "c0d9e142-21bd-45d0-9606-d28d305fe4ba": ("2 - SCHENK IMMOBILIER", []),
        "96f4a9af-dc8f-4333-b87d-67b37423e6c9": ("Padel 3", [])},
    "53b5aaf2-7449-4691-96f8-a582ce37144b": {
        "97a1c33c-5720-41ea-bbdf-cd1cbbcc34f4": ("Padel 1", ["outdoor"]),
        "757bacaf-0247-49b3-bf49-4ed5c13b9f45": ("Padel 2", ["outdoor"])},
    "4613ab9b-740d-4226-ab3a-28651fd33ef5": {
        "fad17f7c-b594-4ebc-a6b5-6c021869aeeb": ("1 - Terrasport", []),
        "472359fe-bbdb-4cff-9e85-ccaa27d659ba": ("Padel 2", [])},
    "e03e742b-c7fe-4fcf-b3de-ea555a0750e3": {
        "bd7144a2-cb97-4705-bd4e-18cceaf11f82": ("Padel 1", [])},
}
PT_HDR = {"Accept": "application/json, text/plain, */*", "Sec-Fetch-Site": "same-origin",
          "Sec-Fetch-Mode": "cors", "Sec-Fetch-Dest": "empty"}


def _playtomic_direct(club, s):
    """Appel direct à l'API de disponibilités du site, terrains connus."""
    tid = club["tenant"]
    courts = PLAYTOMIC_COURTS.get(tid, {})
    ref = {"Referer": f"https://playtomic.com/fr/clubs/{club['slug']}", **PT_HDR}

    def dispo(d):
        return json.loads(s.get(
            f"https://playtomic.com/api/clubs/availability?tenant_id={tid}&date={d}&sport_id=PADEL", ref))
    return courts, dispo


def _playtomic_web(club, s):
    """Page du club sur playtomic.com (plan B si les terrains changent)."""
    page_url = f"https://playtomic.com/fr/clubs/{club['slug']}"
    h = s.get(page_url).replace('\\\\"', '"').replace('\\"', '"')
    tid = club.get("tenant") or re.search(r'"tenant_id":"([0-9a-f-]{36})"', h).group(1)
    courts = {}
    for rid, name, feats in re.findall(
            r'"resourceId":"([0-9a-f-]{36})","name":"([^"]+)","sport":"PADEL","features":\[([^\]]*)\]', h):
        courts[rid] = (name, re.findall(r'"(\w+)"', feats))

    def dispo(d):
        return json.loads(s.get(
            f"https://playtomic.com/api/clubs/availability?tenant_id={tid}&date={d}&sport_id=PADEL",
            {"Accept": "application/json"}))
    return courts, dispo


def playtomic(club, s):
    page_url = f"https://playtomic.com/fr/clubs/{club['slug']}"
    erreurs = []
    for mode in ((_playtomic_direct, _playtomic_web) if club.get("tenant") else (_playtomic_web,)):
        try:
            courts, dispo = mode(club, s)
            dispo(jours()[0])
            break
        except Exception as e:
            erreurs.append(f"{mode.__name__}: {e}")
    else:
        raise RuntimeError(" | ".join(erreurs))
    out = []
    for d in jours():
        data = dispo(d)
        for bloc in data:
            name, feats = courts.get(bloc["resource_id"], ("Terrain", []))
            par_debut = {}
            for sl in bloc.get("slots", []):
                if int(sl.get("duration", 0)) < 60:
                    continue
                par_debut.setdefault(sl["start_time"], []).append((int(sl["duration"]), sl.get("price")))
            for hhmmss, durees in par_debut.items():
                # Playtomic renvoie l'heure en UTC (vérifié le 20.10.2026)
                debut = datetime.fromisoformat(f"{bloc.get('start_date', d)}T{hhmmss}").replace(
                    tzinfo=timezone.utc).astimezone(TZ)
                tags = sorted({f for f in feats if f in ("single", "outdoor")})
                out.append(slot(club, name, debut, sorted(durees), page_url, tags))
    return out


# ─────────────────────────── MATCHPOINT ───────────────────────────
def matchpoint(club, s):
    base = club["base"]
    grid = s.get(f"{base}/Booking/Grid.aspx")
    m = re.search(r"\n\s*(\w+)='([A-Za-z0-9+/=]{16,})';\s*var __cultureInfo", grid) or \
        re.search(r"(\w{8,})='([A-Za-z0-9+/=]{24,})';", grid)
    key = m.group(2)
    srv = f"{base}/booking/srvc.aspx"
    hdr = {"Referer": f"{base}/Booking/Grid.aspx", "Origin": base,
           "Accept": "application/json, text/javascript, */*; q=0.01"}
    _post = s.post_json
    s.post_json = lambda url, payload, headers=None: _post(url, payload, {**hdr, **(headers or {})})
    cuadros = s.post_json(f"{srv}/ObtenerCuadros", {"key": key})["d"]
    info = {"cle": key[:6], "cuadros": [(c.get("Id"), c.get("Nombre")) for c in (cuadros or [])], "jours": []}
    club["_info"] = info
    cuadros = [c for c in cuadros if "padel" in (c.get("Nombre") or "").lower()] or cuadros
    out = []
    for c in cuadros:
        for d in jours():
            q = s.post_json(f"{srv}/ObtenerCuadro",
                            {"idCuadro": c["Id"], "fecha": d.strftime("%d/%m/%Y"), "key": key})["d"]
            if not isinstance(q, dict):
                info["jours"].append(str(q)[:120])
                continue
            info["jours"].append([str(q.get("StrFecha")), len(q.get("Columnas") or []),
                                  sum(len(col.get("HorariosFijos") or []) for col in q.get("Columnas") or []),
                                  {k: str(v)[:40] for k, v in q.items() if v not in (None, "", [], False, 0)}
                                  if not q.get("Columnas") else ""])
            for col in q.get("Columnas", []):
                for h in col.get("HorariosFijos", []) or []:
                    hh, mm = map(int, h["StrHoraInicio"].split(":"))
                    debut = datetime(d.year, d.month, d.day, hh, mm, tzinfo=TZ)
                    out.append(slot(club, col.get("TextoPrincipal", "Terrain"), debut,
                                    [(int(h.get("Minutos", 60)), None)], f"{base}/Booking/Grid.aspx"))
    return out


# ─────────────────────────── PLUGIN.CH ───────────────────────────
def plugin(club, s):
    base = club["base"]
    home = s.get(f"{base}/dashboardV2")
    lien = None
    for href, txt in re.findall(r'<a[^>]+href="([^"]*dashboard/sport/\d+/\d+)"[^>]*>(.*?)</a>', home, re.S):
        if "padel" in re.sub(r"<[^>]+>", " ", txt).lower():
            lien = urllib.parse.urljoin(base + "/", href)
            break
    if not lien:
        raise RuntimeError("catégorie Padel introuvable")
    s.get(lien)
    out = []
    for d in jours():
        s.get(f"{base}/dashboard/date/{d:%Y%m%d}")
        t = Tree(s.get(f"{base}/dashboardV2")).root
        libres = {}
        for n in t.find_all(lambda n: n.has("slot") and n.has("free")):
            hm = n.attrs.get("data-heure", "")
            if not re.fullmatch(r"\d{4}", hm):
                continue
            libres.setdefault(n.attrs.get("data-atrname", "Padel"), set()).add(int(hm[:2]) * 60 + int(hm[2:]))
        for court, mins in libres.items():
            pas = min((b - a for a, b in zip(sorted(mins), sorted(mins)[1:]) if b > a), default=30)
            for st in sorted(mins):
                if st % 30:
                    continue
                n = 1
                while st + n * pas in mins and n * pas < 90:
                    n += 1
                dur = min(n * pas, 90)
                if dur < 60:
                    continue
                durees = [(60, club.get("prix"))] + ([(90, None)] if dur >= 90 else [])
                debut = datetime(d.year, d.month, d.day, st // 60, st % 60, tzinfo=TZ)
                out.append(slot(club, court, debut, durees, f"{base}/dashboardV2", ["outdoor"]))
    return out


# ─────────────────────── TENNIS ONLINE (FIT SA) ───────────────────────
JOURS_ABBR = {"lu": 0, "ma": 1, "me": 2, "je": 3, "ve": 4, "sa": 5, "di": 6}


def _heures(node):
    out = []
    for ch in node.els():
        m = re.search(r"(\d{1,2})h(\d{2})", ch.all_text())
        if m:
            out.append(int(m.group(1)) * 60 + int(m.group(2)))
    return out


def _parse_tennisonline(html, d, club, page_url):
    t = Tree(html).root
    global_heures = next(iter(t.find_all(lambda n: n.has("col-heures"))), None)
    out = []
    for cc in t.find_all(lambda n: n.has("col-courts")):
        heures = _heures(global_heures) if global_heures else []
        for el in cc.els():
            if el.has("col-heures"):
                heures = _heures(el)
                continue
            if not el.has("courts"):
                continue
            kids = el.els()
            if not kids:
                continue
            court = re.sub(r"\s+", " ", kids[0].all_text()).strip() or "Padel"
            cases = [k for k in kids[1:] if not k.has("bottom")]
            if len(cases) != len(heures):
                print(f"  ! {club['nom']} {court}: {len(cases)} cases / {len(heures)} heures", file=sys.stderr)
                continue
            for i, (case, st) in enumerate(zip(cases, heures)):
                if not any(c.endswith("_libre") for c in case.cls):
                    continue
                fin = heures[i + 1] if i + 1 < len(heures) else st + (heures[1] - heures[0] if len(heures) > 1 else 60)
                dur = fin - st
                if dur < 60:
                    continue
                debut = datetime(d.year, d.month, d.day, st // 60, st % 60, tzinfo=TZ)
                out.append(slot(club, court, debut, [(dur, club.get("prix"))], page_url))
    return out


def tennisonline(club, s):
    base = club["base"]
    accueil = s.get(f"{base}/tableau.php")
    m = re.search(r'tableau_padel\.php\?responsive=(?:false|true)&(?:amp;)?d=([A-Za-z0-9+/=]+)', accueil)
    url0 = f"{base}/tableau_padel.php?responsive=false&d={m.group(1)}"
    h0 = s.get(url0)
    # Liens vers les autres jours : <span ... onclick="...tableau_padel.php?...d=XXX'">Me 21</span>
    pages = {}
    today = datetime.now(TZ).date()
    for mm in re.finditer(r"tableau_padel\.php\?responsive=false&(?:amp;)?d=([A-Za-z0-9+/=]+)'[^>]*>\s*([A-Za-z]{2})\s+(\d{1,2})\s*<", h0):
        tok, num = mm.group(1), int(mm.group(3))
        for d in jours():
            if d.day == num:
                pages[d] = tok
    out = []
    # Jour affiché par défaut = celui de la page d'accueil (aujourd'hui)
    out += _parse_tennisonline(h0, today, club, url0)
    for d, tok in sorted(pages.items()):
        if d == today:
            continue
        u = f"{base}/tableau_padel.php?responsive=false&d={tok}"
        out += _parse_tennisonline(s.get(u), d, club, u)
    return out


SOURCES = {"playtomic": playtomic, "matchpoint": matchpoint, "plugin": plugin, "tennisonline": tennisonline}


# ─────────────────────────── NOTIFICATIONS ───────────────────────────
JOURS_NOMS = ["lun", "mar", "mer", "jeu", "ven", "sam", "dim"]


ALERTES_OVERRIDE = None


def charger_alertes():
    if ALERTES_OVERRIDE is not None:
        return ALERTES_OVERRIDE
    f = ROOT / "alertes.json"
    if not f.exists():
        return []
    return json.loads(f.read_text(encoding="utf-8")).get("alertes", [])


def correspond(x, regle):
    if regle.get("actif") is False:
        return False
    dt = datetime.fromisoformat(x["debut"])
    # Uniquement des dates précises ("2026-10-25"), pas de jours récurrents
    if x["debut"][:10] not in (regle.get("dates") or []):
        return False
    if not (regle.get("de", "00:00") <= x["debut"][11:16] <= regle.get("a", "23:59")):
        return False
    if not any(d["min"] >= int(regle.get("duree_min", 60)) for d in x["durees"]):
        return False
    clubs = regle.get("clubs") or []
    if clubs and not any(c.lower() in x["club"].lower() for c in clubs):
        return False
    if regle.get("sans_simple", True) and "single" in x.get("tags", []):
        return False
    return True


def notifier(nouveaux):
    topic = os.environ.get("NTFY_TOPIC")
    regles = charger_alertes()
    if not topic or not nouveaux or not regles:
        return
    ok = [x for x in nouveaux if any(correspond(x, r) for r in regles)]
    if not ok:
        return
    ok.sort(key=lambda x: x["debut"])
    jf = ["lun", "mar", "mer", "jeu", "ven", "sam", "dim"]
    lignes = []
    for x in ok[:6]:
        dt = datetime.fromisoformat(x["debut"])
        lignes.append(f"{jf[dt.weekday()]} {dt:%d.%m %H:%M} · {x['club']} ({x['court']})")
    if len(ok) > 6:
        lignes.append(f"+{len(ok) - 6} autres")
    req = urllib.request.Request(
        f"https://ntfy.sh/{topic}", data="\n".join(lignes).encode(), method="POST",
        headers={"Title": f"{len(ok)} nouveau(x) creneau(x) padel",
                 "Tags": "tennis",
                 "Click": os.environ.get("PAGE_URL", "")})
    try:
        urllib.request.urlopen(req, timeout=15)
    except Exception as e:
        print("ntfy:", e, file=sys.stderr)


# ─────────────────────────── MAIN ───────────────────────────
def cle(x):
    return f"{x['club']}|{x['court']}|{x['debut']}"


REPO = os.environ.get("PADEL_REPO", "hector347321/padel-dispo")
CONF_MAC = Path.home() / ".padel-dispo.json"   # {"token": "...", "ntfy": "..."} sur le Mac


def gh(method, chemin, token, corps=None):
    req = urllib.request.Request(
        f"https://api.github.com/repos/{REPO}/contents/{chemin}",
        data=json.dumps(corps).encode() if corps else None, method=method,
        headers={"Accept": "application/vnd.github+json", "Authorization": f"Bearer {token}",
                 "User-Agent": "padel-dispo"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def lire_gh(chemin, token):
    import base64
    try:
        j = gh("GET", chemin, token)
        return json.loads(base64.b64decode(j["content"]).decode()), j["sha"]
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None, None
        raise


def collecter(clubs):
    creneaux, statuts = [], []
    for club in clubs:
        st = {"club": club["nom"], "ville": club["ville"], "type": club["type"],
              "note": club.get("note"), "url": club.get("url") or club.get("base")
              or f"https://playtomic.com/fr/clubs/{club.get('slug')}"}
        if club["type"] == "lien":
            st["etat"] = "lien"
            statuts.append(st)
            continue
        try:
            res = SOURCES[club["type"]](club, Session())
            vus, uniq = set(), []
            for x in res:
                if cle(x) not in vus:
                    vus.add(cle(x))
                    uniq.append(x)
            creneaux += uniq
            st["etat"], st["n"] = "ok", len(uniq)
            print(f"{club['nom']}: {len(uniq)} créneaux")
        except Exception as e:
            st["etat"], st["erreur"] = "erreur", f"{type(e).__name__}: {e}"[:200]
            print(f"{club['nom']}: ERREUR {e}", file=sys.stderr)
            traceback.print_exc()
        if club.get("_info"):
            st["info"] = club["_info"]
        statuts.append(st)
    maintenant = datetime.now(TZ)
    creneaux = [x for x in creneaux if datetime.fromisoformat(x["debut"]).replace(tzinfo=TZ) > maintenant]
    creneaux.sort(key=lambda x: (x["debut"], x["club"], x["court"]))
    return {"maj": maintenant.isoformat(timespec="minutes"), "clubs": statuts, "creneaux": creneaux}


def nouveaux(data, prev):
    """'Se libère' = absent au passage précédent, sur un jour déjà couvert, pour un club
    qui fonctionnait déjà (évite les alertes en masse à minuit ou après une panne)."""
    if not prev:
        return []
    anciens = {cle(x) for x in prev["creneaux"]}
    jours_prev = {x["debut"][:10] for x in prev["creneaux"]}
    clubs_prev = {c["club"] for c in prev["clubs"] if c.get("etat") == "ok"}
    return [x for x in data["creneaux"] if cle(x) not in anciens
            and x["debut"][:10] in jours_prev and x["club"] in clubs_prev]


def main():
    mac = "--mac" in sys.argv
    actifs = [c for c in CLUBS if not c.get("off")]
    if mac:
        # Sur le Mac : seulement Playtomic (qui refuse les serveurs GitHub), envoyé dans le dépôt
        conf = json.loads(CONF_MAC.read_text())
        os.environ.setdefault("NTFY_TOPIC", conf.get("ntfy", ""))
        os.environ.setdefault("PAGE_URL", f"https://{REPO.split('/')[0]}.github.io/{REPO.split('/')[1]}/")
        data = collecter([c for c in actifs if c["type"] == "playtomic"])
        if not any(c["etat"] == "ok" for c in data["clubs"]):
            print("Playtomic injoignable, rien envoyé", file=sys.stderr)
            return
        try:
            prev, sha = lire_gh("docs/playtomic.json", conf["token"])
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                print(f"JETON GITHUB REFUSÉ ({e.code}). Recrée-le (Contents : Read and write sur padel-dispo), "
                      f"puis : rm ~/.padel-dispo.json et relance l'installateur.", file=sys.stderr)
                sys.exit(1)
            raise
        alertes, _ = lire_gh("alertes.json", conf["token"])
        global ALERTES_OVERRIDE
        ALERTES_OVERRIDE = (alertes or {}).get("alertes", [])
        try:
            notifier(nouveaux(data, prev))
        except Exception as e:
            print("notif:", e, file=sys.stderr)
        import base64
        corps = {"message": f"playtomic {data['maj'][11:16]}",
                 "content": base64.b64encode(json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode()).decode()}
        if sha:
            corps["sha"] = sha
        gh("PUT", "docs/playtomic.json", conf["token"], corps)
        print(f"→ {len(data['creneaux'])} créneaux Playtomic envoyés")
        return

    # Sur GitHub : tous les clubs sauf Playtomic (géré par le Mac)
    data = collecter([c for c in actifs if c["type"] != "playtomic"])
    data["clubs"] += [{"club": c["nom"], "ville": c["ville"], "type": "playtomic", "note": c.get("note"),
                       "url": f"https://playtomic.com/fr/clubs/{c['slug']}", "etat": "mac"}
                      for c in actifs if c["type"] == "playtomic"]
    if OUT.exists():
        try:
            notifier(nouveaux(data, json.loads(OUT.read_text())))
        except Exception as e:
            print("notif:", e, file=sys.stderr)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"→ {len(data['creneaux'])} créneaux, {OUT}")


if __name__ == "__main__":
    main()
