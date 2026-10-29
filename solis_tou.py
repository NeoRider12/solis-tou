#!/usr/bin/env python3
"""
solis_tou.py – Akkus des Solis RAI-3K-48ES-5G nachts gezielt "schlafen legen"
über den Time-of-Use-Schalter (SolisCloud-API). Ganzjährig nach Monatsplan.

Prinzip
  * Im Wechselrichter ist ein TOU-Ladeslot mit 0,1 A eingestellt. Ist TOU AN,
    lädt der WR in dieser Zeit minimal → die Pylontech-BMS gehen schlafen.
  * Abends/nachts (Prüfphase, ab dem Abendbeginn des Monats): stündlich SOC
    prüfen. Ist SOC <= Schwelle des Monats, wird TOU EINgeschaltet. In der
    Prüfphase wird TOU NIE ausgeschaltet.
  * ab 07:15: TOU wird AUSgeschaltet (mehrere Läufe bis Vormittag als Sicherung).
  * Morgens wird Ladeslot 1 (Abendbeginn–07:15, 0,1 A) automatisch auf den Plan
    der kommenden Nacht gesetzt, falls die Zeit abweicht oder der Ladestrom
    deutlich zu hoch ist. Das passiert nur bei Monatswechseln mit neuem
    Abendbeginn und bei der Zeitumstellung (ca. 8× im Jahr).

Monatsplan (siehe MONATSPLAN): Abendbeginn = Sonnenuntergang −1 Std., auf die
volle Stunde aufgerundet, Slot jeweils ab Minute 15 (die Sonne hat Vorrang). TOU aus ab 07:15.

Schalten: pro Lauf ein Schreibbefehl je Register. Danach Kontrolle durch
Zurücklesen. Nicht bestätigt → Warnung; der nächste Lauf prüft erneut.
Findet die letzte Aus-Sicherung am Vormittag TOU noch AN → Fehler + E-Mail.

Aufruf
  python3 solis_tou.py status            # Plan, Modus, SOC, Ladeslots, Entscheidung
  python3 solis_tou.py auto [--dry-run]  # automatischer Lauf (GitHub-Zeitplan)
  python3 solis_tou.py on   [--dry-run]  # TOU sofort einschalten
  python3 solis_tou.py off  [--dry-run]  # TOU sofort ausschalten
  python3 solis_tou.py ladeslot [--dry-run]  # Ladeslot 1 (+ Entladegrenze) sofort auf den heutigen Plan
  python3 solis_tou.py grenzen           # SOC-Grenzen im Wechselrichter nur lesen
  python3 solis_tou.py protokoll         # PROTOKOLL.md neu erzeugen und anzeigen

Protokoll (optional): Ist die Umgebungsvariable PROTOKOLL_DIR gesetzt, wird jede
Schaltung (und morgens der SOC) in <PROTOKOLL_DIR>/protokoll/ereignisse.csv
festgehalten. Daraus entsteht <PROTOKOLL_DIR>/PROTOKOLL.md (letzte Nächte,
Monatsübersicht). Der Workflow legt beides in einem separaten, PRIVATEN Repository
ab – so bleiben die Daten privat, auch wenn dieses Repository öffentlich ist.
Ohne PROTOKOLL_DIR läuft die Steuerung ganz normal, nur ohne Protokoll.

Exit-Code 1 bei Fehlern → GitHub markiert den Lauf rot und schickt eine E-Mail.

Benötigt: pip install requests
Umgebungsvariablen: SOLIS_KEY_ID, SOLIS_KEY_SECRET, SOLIS_INVERTER_SN
"""

import argparse
import csv
import base64
import hashlib
import hmac
import json
import os
import sys
import time
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from email.utils import formatdate
from pathlib import Path

import requests

# ============================ EINSTELLUNGEN ================================

# Monatsplan – gilt für die Nacht, die an einem Tag dieses Monats beginnt.
#   abend    = Abendbeginn (Stunde; Slot startet zur Minute SLOT_MINUTE): Start von Ladeslot 1
#              UND Beginn der SOC-Prüfung
#   abend_sz = abweichender Abendbeginn, solange Sommerzeit gilt (nur März und Oktober nötig;
#              die Zeitumstellung erkennt das Skript selbst)
#   soc      = TOU an, wenn SOC <= diesem Wert (kostet keine Schreibvorgänge, frei änderbar)
#   odsoc    = Entladegrenze (Overdischarge-SOC) im Wechselrichter für diesen Monat;
#              fehlt der Eintrag, gilt ODSOC_NORMAL. Wird nur geschrieben, wenn sie sich ändert.
# Abendbeginn = Sonnenuntergang −1 Std., spätester Wert des Monats, auf volle Stunde aufgerundet.
# ACHTUNG: Wird ein Abendbeginn früher als 16 Uhr gelegt, den cron-job.org-Job erweitern
#          (er startet erst ab 16:15).
MONATSPLAN = {
    1:  {"abend": 17, "soc": 30, "odsoc": 30},
    2:  {"abend": 18, "soc": 30, "odsoc": 30},
    3:  {"abend": 18, "abend_sz": 19, "soc": 15},
    4:  {"abend": 20, "soc": 15},
    5:  {"abend": 21, "soc": 15},
    6:  {"abend": 21, "soc": 15},
    7:  {"abend": 21, "soc": 15},
    8:  {"abend": 21, "soc": 15},
    9:  {"abend": 20, "soc": 15},
    10: {"abend": 17, "abend_sz": 19, "soc": 15},
    11: {"abend": 17, "soc": 30, "odsoc": 30},
    12: {"abend": 16, "soc": 30, "odsoc": 30},
}
LADESTROM = "0.1"         # Ladestrom von Slot 1 in A (lässt die Pylontech-BMS schlafen)
SLOT_MINUTE = 15          # Minute für Beginn und Ende von Ladeslot 1 = Startminute bei cron-job.org

# Entladegrenze (Overdischarge-SOC): Darunter entlädt der Wechselrichter den Akku nicht weiter.
# Im Winter (Nov–Feb) 30 % als Puffer, sonst ODSOC_NORMAL.
# CID 158 ist bei RAI-3K-48ES-5G bestätigt. Andere Geräte: erst mit "grenzen" prüfen, welche
# CID den Wert aus der Solis-App zeigt, bevor ODSOC_STEUERN = True gesetzt wird.
# Schwelle (soc) und Entladegrenze (odsoc) bewusst IDENTISCH halten: Der Akku entlädt bis zur
# Grenze, schläft dort ein und bleibt nach dem Ausschalten morgens sparsam im Standby.
ODSOC_STEUERN = True
ODSOC_CID = 158           # bestätigt am 23.10.2026 (Abgleich mit der Solis-App)
ODSOC_NORMAL = 15         # Overdischarge-SOC außerhalb des Winters (bewusst = SOC-Schwelle)
GRENZEN_KANDIDATEN = {    # werden von "grenzen" nur gelesen (beim RAI-3K-48ES-5G bestätigt)
    157: "Reserve-/Backup-SOC",
    158: "Overdischarge-SOC (Entladegrenze)",
    160: "Force-Charge-SOC (darunter Netzladung)",
}
ZEITZONE = ZoneInfo("Europe/Berlin")

PRUEF_ENDE = 6            # letzte Prüfung in der Stunde 06:00–06:59
AUS_BEGINN = 7            # ab 07:00 Uhr wird TOU ausgeschaltet (bis zur nächsten Prüfphase)
LETZTE_AUS_SICHERUNG = 10 # ab diesem Lauf: TOU noch AN → Fehler + E-Mail
LADESLOT_ABGLEICH = True  # morgens Ladeslot 1 automatisch auf den Plan der kommenden Nacht setzen

# Nach dem Schreiben zurücklesen und bestätigen? (False = nur schreiben)
RUECKLESEN = True
RUECKLESE_WARTEZEIT = (15, 30)   # Sekunden: 1. Kontrolle nach 15 s, 2. nach weiteren 30 s

PROTOKOLL_TAGE = 60       # so viele Nächte zeigt die Detailtabelle in PROTOKOLL.md
HINWEISE_MAX = 15         # so viele Nächte mit Hinweisen werden höchstens aufgelistet
MONATS_UEBERSICHT = 60    # so viele Monate zeigt die Monatsübersicht (CSV behält alles)

MAX_LAUFZEIT = 150        # Sekunden: danach bricht das Skript ab (normale Läufe brauchen 10–60 s)
WIEDERHOL_PAUSEN = (10, 30)  # Sekunden Pause vor dem 2. und 3. Versuch, wenn die Cloud hakt
AUSSETZER_FENSTER = 75    # Minuten: zwei Cloud-Aussetzer innerhalb dieser Zeit = Fehler + E-Mail

# ===========================================================================

BASE_URL = "https://www.soliscloud.com:13333"
API_ID = os.environ.get("SOLIS_KEY_ID", "")
API_SECRET = os.environ.get("SOLIS_KEY_SECRET", "")
INVERTER_SN = os.environ.get("SOLIS_INVERTER_SN", "")

CID_STORAGE_MODE = 636       # Bitfeld Speichermodus (≙ Modbus 43110)
CID_CHARGE_DISCHARGE = 103   # Lade-/Entladezeiten und -ströme (3 Slots)
BIT_TOU = 1

BITS = {
    0: "Self-Use",
    1: "Time of Use",
    2: "Off-Grid",
    4: "Batterie-Reserve (Backup)",
    5: "Netzladen erlaubt",
    6: "Feed-in Priority",
    11: "Peak Shaving",
}


class Fehler(Exception):
    pass


class CloudFehler(Fehler):
    """Cloud nicht erreichbar / gestört (Timeout, 502 …) – meist vorübergehend."""


CLOUD_PREFIX = "Cloud-Aussetzer"


def aussetzer_kurz_zuvor(now: datetime) -> bool:
    """True, wenn laut Protokoll schon der vorige Lauf (innerhalb AUSSETZER_FENSTER) an der
    Cloud gescheitert ist. Ohne Protokoll lässt sich das nicht prüfen → True (lieber melden)."""
    if not PROTOKOLL_AKTIV:
        return True
    for e in reversed(lies_ereignisse()):
        try:
            t = datetime.strptime(e["zeit"], "%Y-%m-%d %H:%M")
        except ValueError:
            continue
        if now - t > timedelta(minutes=AUSSETZER_FENSTER):
            return False
        if e["ereignis"] in ("WARNUNG", "FEHLER") and e["info"].startswith(CLOUD_PREFIX):
            return True
    return False


# ----------------------------- Protokoll -----------------------------------
PROTOKOLL_DIR = os.environ.get("PROTOKOLL_DIR", "").strip()
PROTOKOLL_AKTIV = bool(PROTOKOLL_DIR)
_BASIS = Path(PROTOKOLL_DIR).resolve() if PROTOKOLL_AKTIV else Path(__file__).resolve().parent
PROTOKOLL_CSV = _BASIS / "protokoll" / "ereignisse.csv"
PROTOKOLL_MD = _BASIS / "PROTOKOLL.md"
CSV_FELDER = ["zeit", "nacht", "saison", "ereignis", "soc", "quelle", "info"]

LOG = {"aktiv": False, "quelle": "auto", "soc": None, "geaendert": False}


def tou_sicher_aus() -> bool:
    """True, wenn laut Protokoll das letzte TOU-Ereignis ein bestätigtes AUS war
    (oder der Morgenlauf TOU bereits aus vorfand)."""
    for e in reversed(lies_ereignisse()):
        if e["ereignis"] == "TOU_AUS":
            return "bestätigt" in e["info"]
        if e["ereignis"] == "MORGEN":
            return e["info"] == "TOU war aus"
        if e["ereignis"] == "TOU_AN":
            return False
    return False


def lies_ereignisse() -> list[dict]:
    if not PROTOKOLL_AKTIV or not PROTOKOLL_CSV.exists():
        return []
    with PROTOKOLL_CSV.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def protokolliere(ereignis: str, soc: float | None = None, info: str = "") -> None:
    """Hängt ein Ereignis an protokoll/ereignisse.csv an (nicht bei Dry-Run / status)."""
    if not LOG["aktiv"] or not PROTOKOLL_AKTIV:
        return
    now = datetime.now()
    neu = not PROTOKOLL_CSV.exists()
    PROTOKOLL_CSV.parent.mkdir(exist_ok=True)
    with PROTOKOLL_CSV.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FELDER, lineterminator="\n")
        if neu:
            w.writeheader()
        w.writerow({
            "zeit": now.strftime("%Y-%m-%d %H:%M"),
            "nacht": nacht_datum(now).isoformat(),
            "saison": plan(nacht_datum(now))["ladezeit"],   # Spalte heißt historisch "saison"
            "ereignis": ereignis,
            "soc": "" if soc is None else f"{soc:.0f}",
            "quelle": LOG["quelle"],
            "info": info.replace("\n", " ")[:200],
        })
    LOG["geaendert"] = True




def _dauer(minuten: int) -> str:
    return f"{minuten // 60}:{minuten % 60:02d}"


SPAET_AUS = "08:00"         # Ausschalten ab dieser Uhrzeit gilt als auffällig (Hinweis ⚠)


def werte_nacht_aus(d: date, evs: list[dict], vorbei: bool = True) -> dict:
    """Fasst die Ereignisse einer Nacht zusammen. vorbei=False für die laufende Nacht."""
    ladezeit = ladezeit_aus_protokoll(evs[0]["saison"], d)
    an = next((e for e in evs if e["ereignis"] == "TOU_AN"), None)
    aus = next((e for e in evs if e["ereignis"] == "TOU_AUS"), None)
    morgen = next((e for e in evs if e["ereignis"] == "MORGEN"), None)
    hinweise, fehler = [], 0
    for e in evs:
        if e["ereignis"] in ("FEHLER", "WARNUNG", "LADESLOT", "ENTLADEGRENZE"):
            hinweise.append(f"{e['zeit'][11:]} {e['ereignis'].capitalize()}: {e['info']}")
            fehler += e["ereignis"] == "FEHLER"
        elif e["ereignis"] in ("TOU_AN", "TOU_AUS") and e["quelle"] != "auto":
            hinweise.append(f"{e['zeit'][11:]} {e['ereignis'].replace('_', ' ')} manuell")
        if e["ereignis"] in ("TOU_AN", "TOU_AUS") and "unbestätigt" in e["info"]:
            hinweise.append(f"{e['zeit'][11:]} {e['ereignis'].replace('_', ' ')} unbestätigt")

    if an and aus and aus["zeit"][11:] >= SPAET_AUS:
        hinweise.append(f"TOU erst um {aus['zeit'][11:]} aus")
    if an and not aus and vorbei:
        hinweise.append("TOU AUS nicht protokolliert")

    schlaf = None
    if an and not aus and not vorbei:
        pass                     # laufende Nacht: Dauer steht erst morgens fest
    elif an:
        # wirksame Schlafzeit = Überschneidung von "TOU an" und Ladeslot
        von_s, bis_s = ladezeit.split("-")
        slot_von = datetime.combine(d, datetime.strptime(von_s, "%H:%M").time())
        slot_bis = datetime.combine(d + timedelta(days=1), datetime.strptime(bis_s, "%H:%M").time())
        t_an = datetime.strptime(an["zeit"], "%Y-%m-%d %H:%M")
        t_aus = datetime.strptime(aus["zeit"], "%Y-%m-%d %H:%M") if aus else slot_bis
        schlaf = max(0, int((min(t_aus, slot_bis) - max(t_an, slot_von)).total_seconds() // 60))
    return {
        "an": an["zeit"][11:] if an else None,
        "soc_an": float(an["soc"]) if an and an["soc"] else None,
        "aus": aus["zeit"][11:] if aus else None,
        "soc_morgen": float(morgen["soc"]) if morgen and morgen["soc"] else None,
        "schlaf": schlaf,
        "hinweise": hinweise,
        "fehler": fehler,
        "vorbei": vorbei,
    }


def _soc_paar(n: dict) -> str:
    """'15→13%' (SOC beim Einschalten → SOC morgens); ohne Einschalten nur '→44%'."""
    an = f"{n['soc_an']:.0f}" if n["soc_an"] is not None else ""
    frueh = (f"{n['soc_morgen']:.0f}%" if n["soc_morgen"] is not None
             else ("?" if n["vorbei"] else "…") if an else "")
    return f"{an}→{frueh}" if (an or frueh) else ""


def _kennzahlen(naechte: list[dict]) -> tuple[int, int, str, str, int]:
    geschlafen = [n for n in naechte if n["an"]]
    socs = [n["soc_an"] for n in geschlafen if n["soc_an"] is not None]
    schlaf = [n["schlaf"] for n in geschlafen if n["schlaf"]]
    return (len(geschlafen), len(naechte) - len(geschlafen),
            f"{sum(socs) / len(socs):.0f}%" if socs else "–",
            _dauer(int(sum(schlaf) / len(schlaf))) if schlaf else "–",
            sum(n["fehler"] for n in naechte))


def erzeuge_markdown() -> str:
    """Erzeugt PROTOKOLL.md (letzte PROTOKOLL_TAGE Nächte + Monatsübersicht) und gibt den Text zurück."""
    nach_nacht: dict[date, list[dict]] = {}
    for e in lies_ereignisse():
        nach_nacht.setdefault(date.fromisoformat(e["nacht"]), []).append(e)
    laufend = nacht_datum(datetime.now())
    auswertung = {d: werte_nacht_aus(d, evs, vorbei=d < laufend) for d, evs in nach_nacht.items()}

    ende = max([nacht_datum(datetime.now()), *auswertung])
    erste = min(auswertung) if auswertung else ende
    start = max(erste, ende - timedelta(days=PROTOKOLL_TAGE - 1))

    # Detailtabelle der letzten Nächte (schmal, damit sie aufs Handy im Hochformat passt)
    zeilen, im_zeitraum, hinweis_zeilen = [], [], []
    d = ende
    while d >= start:
        tag = f"{d:%d.%m.}"
        n = auswertung.get(d)
        if n is None:
            zeilen.append(f"| {tag} | | | k. D. |")
        else:
            im_zeitraum.append(n)
            if n["hinweise"]:
                hinweis_zeilen.append(f"- **{tag}** " + "; ".join(n["hinweise"]))
            zeilen.append("| " + " | ".join([
                tag,
                # Ein- und Ausschaltzeit mit geschütztem Bindestrich (U+2011) → kein Zeilenumbruch
                (f"{n['an']}\u2011{n['aus'] or ('…' if n['schlaf'] is None else '?')}" if n["an"] else "–"),
                _soc_paar(n) + ("⚠" if n["hinweise"] else ""),
                "läuft" if n["an"] and n["schlaf"] is None else (_dauer(n["schlaf"]) if n["an"] else "∞"),
            ]) + " |")
        d -= timedelta(days=1)
    k = _kennzahlen(im_zeitraum)

    # Monatsübersicht (gesamte Historie, neueste oben)
    monate: dict[tuple[int, int], list[dict]] = {}
    for d, n in auswertung.items():
        monate.setdefault((d.year, d.month), []).append(n)
    monats_zeilen = []
    for (j, m) in sorted(monate, reverse=True)[:MONATS_UEBERSICHT]:
        mk = _kennzahlen(monate[(j, m)])
        monats_zeilen.append(f"| {m:02d}/{j % 100:02d} | {mk[0]} | {mk[1]} | {mk[2]} | {mk[3]} | {mk[4]} |")

    nach_oben = "[↑ Top](#protokoll-akku-schlaf)"
    text = "\n".join([
        "# Protokoll Akku-Schlaf",
        "",
        f"Stand {datetime.now():%d.%m.%Y %H:%M} · automatisch erzeugt",
        "",
        "Springen zu: [Hinweise](#hinweise) · [Monate](#monate) · [Legende](#legende)",
        "",
        "## Nächte",
        "",
        f"Letzte {PROTOKOLL_TAGE} Nächte, neueste oben.",
        "",
        "| 💤 | ∞ | Ø SOC an | Ø Dauer | Fehler |",
        "|---|---|---|---|---|",
        f"| {k[0]} | {k[1]} | {k[2]} | {k[3]} | {k[4]} |",
        "",
        "| Nacht | TOU | SOC→Früh | Dauer |",
        "|---|---|---|---|",
        *zeilen,
        "",
        "## Hinweise",
        "",
        nach_oben,
        "",
        *(hinweis_zeilen[:HINWEISE_MAX] or [f"Keine Hinweise in den letzten {PROTOKOLL_TAGE} Nächten."]),
        *([f"- … {len(hinweis_zeilen) - HINWEISE_MAX} weitere Nächte mit Hinweisen, siehe "
           "[`protokoll/ereignisse.csv`](protokoll/ereignisse.csv)"] if len(hinweis_zeilen) > HINWEISE_MAX else []),
        "",
        "## Monate",
        "",
        f"{nach_oben} · Bis zu {MONATS_UEBERSICHT} Monate, neueste oben.",
        "",
        "| Monat | 💤 | ∞ | Ø SOC | Ø Dauer | Fehler |",
        "|---|---|---|---|---|---|",
        *monats_zeilen,
        "",
        "## Legende",
        "",
        nach_oben,
        "",
        "- **TOU**: TOU an‑aus (Uhrzeiten); – = nicht nötig, … = läuft noch, ? = Aus nicht protokolliert",
        "- **SOC→Früh**: SOC beim Einschalten → SOC beim ersten Lauf am Morgen (… = Nacht läuft noch, ? = kein Morgenwert)",
        "- **Dauer**: wirksame Schlafzeit in Stunden (TOU an *und* Ladeslot aktiv)",
        "- **💤**: Nächte, in denen die Akkus geschlafen haben",
        "- **∞**: Akkus liefen durch (TOU blieb aus); in den Übersichten: Anzahl solcher Nächte",
        "- **⚠**: Hinweis vorhanden (Fehler, manuelle Schaltung, Ladeslot-Wechsel), siehe [Hinweise](#hinweise)",
        "- **k. D.**: keine Daten für diese Nacht",
        "- Eine Nacht zählt zu dem Tag bzw. Monat, an dem sie beginnt.",
        "",
        "Rohdaten: [`protokoll/ereignisse.csv`](protokoll/ereignisse.csv)",
        "",
    ])
    PROTOKOLL_MD.write_text(text, encoding="utf-8")
    return text

START = time.monotonic()


def restzeit() -> float:
    return MAX_LAUFZEIT - (time.monotonic() - START)


# ------------------------------- API ---------------------------------------
def _headers(endpoint: str, body: str) -> dict:
    content_md5 = base64.b64encode(hashlib.md5(body.encode()).digest()).decode()
    content_type = "application/json"
    gmt_date = formatdate(usegmt=True)
    to_sign = "\n".join(["POST", content_md5, content_type, gmt_date, endpoint])
    signature = base64.b64encode(
        hmac.new(API_SECRET.encode(), to_sign.encode(), hashlib.sha1).digest()
    ).decode()
    return {
        "Content-MD5": content_md5,
        "Content-Type": content_type,
        "Date": gmt_date,
        "Authorization": f"API {API_ID}:{signature}",
    }


def _post(endpoint: str, payload: dict) -> object:
    if not (API_ID and API_SECRET and INVERTER_SN):
        raise Fehler("Fehlt: SOLIS_KEY_ID, SOLIS_KEY_SECRET oder SOLIS_INVERTER_SN")

    body = json.dumps(payload)
    last_err = None
    for attempt in range(3):  # die Cloud-API ist gelegentlich zickig
        if restzeit() < 5:
            break
        try:
            r = requests.post(BASE_URL + endpoint, data=body,
                              headers=_headers(endpoint, body),
                              timeout=min(15, max(3, restzeit())))
            r.raise_for_status()
            js = r.json()
            if str(js.get("code")) != "0":
                raise Fehler(f"API-Fehler {js.get('code')}: {js.get('msg')}")
            return js.get("data")
        except Exception as e:  # noqa: BLE001
            last_err = e
            if attempt < 2:
                pause = WIEDERHOL_PAUSEN[attempt]
                if restzeit() < pause + 20:
                    break
                time.sleep(pause)
    raise CloudFehler(f"{endpoint} fehlgeschlagen: {last_err or 'Zeitlimit erreicht'}")


def read_cid(cid: int) -> str:
    data = _post("/v2/api/atRead", {"inverterSn": INVERTER_SN, "cid": cid})
    return data["msg"]


def write_cid(cid: int, value: str, old_value: str | None = None) -> None:
    payload = {"inverterSn": INVERTER_SN, "cid": cid, "value": value}
    if old_value is not None:
        payload["yuanzhi"] = old_value  # alter Wert, wie ihn die Solis-App mitsendet
    data = _post("/v2/api/control", payload)
    for item in data or []:
        if str(item.get("code", "0")) != "0":
            raise Fehler(f"Control fehlgeschlagen: {item.get('msg')}")


def read_soc() -> tuple[float, str]:
    """Akku-SOC in % und Zeitpunkt der letzten Meldung des Datenloggers."""
    data = _post("/v1/api/inverterDetail", {"sn": INVERTER_SN})
    soc = data.get("batteryCapacitySoc")
    if soc is None:
        raise Fehler("Feld 'batteryCapacitySoc' fehlt in inverterDetail")
    ts = data.get("dataTimestamp")
    stand = datetime.fromtimestamp(int(ts) / 1000).strftime("%d.%m. %H:%M") if ts else ""
    return float(soc), stand


# ----------------------------- Logik ---------------------------------------
def decode(mode: int) -> str:
    active = [name for bit, name in BITS.items() if mode & (1 << bit)]
    return f"{mode} (0b{mode:012b}) → " + (", ".join(active) or "keine Bits gesetzt")


def nacht_datum(now: datetime) -> date:
    """Eine Nacht gehört zum Tag, an dem sie abends beginnt.
    Vormittags (vor 12 Uhr) zählt also noch der Vortag."""
    return (now - timedelta(days=1)).date() if now.hour < 12 else now.date()


def plan(d: date) -> dict:
    """Plan für die Nacht, die am Tag d beginnt: Abendbeginn, SOC-Schwelle, Ladezeit."""
    m = MONATSPLAN[d.month]
    sommerzeit = bool(datetime(d.year, d.month, d.day, 18, tzinfo=ZEITZONE).dst())
    abend = m["abend_sz"] if sommerzeit and "abend_sz" in m else m["abend"]
    return {"abend": abend, "soc": m["soc"], "odsoc": m.get("odsoc", ODSOC_NORMAL),
            "ladezeit": f"{abend:02d}:{SLOT_MINUTE:02d}-{AUS_BEGINN:02d}:{SLOT_MINUTE:02d}"}


def plan_text(d: date) -> str:
    p = plan(d)
    return f"ab {p['abend']}:{SLOT_MINUTE:02d}, SOC <= {p['soc']} %"


# Ältere Protokollzeilen enthalten noch den Saisonnamen statt der Ladezeit
_ALTE_SAISONS = {"winter": "18:00-07:00", "sommer": "20:00-07:00"}


def ladezeit_aus_protokoll(wert: str, d: date) -> str:
    if "-" in (wert or ""):
        return wert
    return _ALTE_SAISONS.get(wert, plan(d)["ladezeit"])


def phase(now: datetime) -> str:
    h = now.hour
    if h >= plan(nacht_datum(now))["abend"] or h <= PRUEF_ENDE:
        return "pruefen"
    return "aus"


def entscheide(now: datetime, tou_an: bool | None, soc: float | None) -> tuple[bool | None, str]:
    """(Soll-Zustand oder None = nichts tun, Begründung)."""
    if phase(now) == "aus":
        heute = plan(now.date())["abend"]
        return False, f"Tagsüber (ab {AUS_BEGINN}:{SLOT_MINUTE:02d} bis {heute}:{SLOT_MINUTE:02d}) → TOU AUS, Akkus laufen normal"

    # Prüfphase – hier wird NUR eingeschaltet, nie ausgeschaltet
    schwelle = plan(nacht_datum(now))["soc"]
    if tou_an:
        return None, "TOU ist bereits AN (Akkus schlafen) → bleibt bis morgens so"
    if soc is None:
        return None, "SOC nicht lesbar → keine Änderung"
    if soc <= schwelle:
        return True, f"SOC {soc:.0f} % <= {schwelle} % → Akkus schlafen legen (TOU AN)"
    return None, f"SOC {soc:.0f} % > {schwelle} % → Akkus laufen weiter"


def tou_bit(raw: str) -> bool:
    return bool(int(raw) & (1 << BIT_TOU))


def schalte(enable: bool, dry_run: bool) -> bool:
    """Setzt NUR das TOU-Bit mit EINEM Schreibbefehl.
    Rückgabe: True = Zustand bestätigt (oder war schon so), False = unbestätigt."""
    ziel = "AN" if enable else "AUS"
    old_raw = read_cid(CID_STORAGE_MODE)      # nötig: Bitfeld lesen, nur ein Bit ändern
    old = int(old_raw)
    if tou_bit(old_raw) == enable:
        print(f"TOU ist bereits {ziel} – nichts zu tun.")
        return True
    new = old | (1 << BIT_TOU) if enable else old & ~(1 << BIT_TOU)
    print(f"Schreibe: {decode(old)}  →  {decode(new)}")
    if dry_run:
        print("Dry-Run – es wurde nichts geschrieben.")
        return True
    write_cid(CID_STORAGE_MODE, str(new), old_raw)
    print(f"Schreibbefehl TOU {ziel} von der Cloud angenommen.")
    ereignis = "TOU_AN" if enable else "TOU_AUS"

    if not RUECKLESEN:
        print("Rücklesen abgeschaltet – Kontrolle beim nächsten Lauf.")
        protokolliere(ereignis, LOG["soc"], "geschrieben (ohne Rücklesen)")
        return True

    # Befehl läuft Cloud → Datenlogger → Wechselrichter; etwas warten.
    for warte in RUECKLESE_WARTEZEIT:
        if restzeit() < warte + 10:
            break
        time.sleep(warte)
        try:
            if tou_bit(read_cid(CID_STORAGE_MODE)) == enable:
                print(f"OK – TOU {ziel}, am Wechselrichter bestätigt.")
                protokolliere(ereignis, LOG["soc"], "bestätigt")
                return True
        except Fehler as e:
            print(f"Rücklesen hakt: {e}")
    print(f"::warning::TOU {ziel} noch nicht bestätigt – der nächste Lauf prüft erneut.")
    protokolliere(ereignis, LOG["soc"], "unbestätigt")
    return False


def setze_ladeslot(d: date, dry_run: bool, alt: str | None = None) -> bool:
    """Setzt Ladestrom und Ladezeit von Slot 1 (CID 103) auf den Plan der Nacht ab Tag d.
    Format: Ladestrom,Entladestrom,Ladezeit,Entladezeit (× 3 Slots).
    Alles andere (Entladung, Slots 2 und 3) bleibt unverändert."""
    ziel = {"zeit": plan(d)["ladezeit"], "strom": LADESTROM}
    if alt is None:
        alt = read_cid(CID_CHARGE_DISCHARGE)
    teile = alt.split(",")
    if len(teile) != 12:
        raise Fehler(f"Unerwartetes Format von CID {CID_CHARGE_DISCHARGE}: {alt}")
    neu_teile = list(teile)
    neu_teile[0] = ziel["strom"]
    neu_teile[2] = ziel["zeit"]
    neu = ",".join(neu_teile)
    print(f"Ladeslot 1 → Plan ab {d:%d.%m.} ({ziel['strom']} A, {ziel['zeit']})")
    print(f"Ladeslots alt: {alt}")
    print(f"Ladeslots neu: {neu}")
    if neu == alt:
        print("Keine Änderung nötig.")
        return True
    if dry_run:
        print("Dry-Run – es wurde nichts geschrieben.")
        return True
    write_cid(CID_CHARGE_DISCHARGE, neu, alt)
    print("Schreibbefehl von der Cloud angenommen.")
    protokolliere("LADESLOT", None, f"{ziel['zeit']}, {ziel['strom']} A")
    if restzeit() < 25:
        print("Kein Zeitbudget mehr für die Kontrolle – der nächste Lauf prüft erneut.")
        return True
    time.sleep(15)
    zurueck = read_cid(CID_CHARGE_DISCHARGE)
    print(f"Zurückgelesen: {zurueck}")
    t = zurueck.split(",")
    if len(t) == 12 and t[2] == ziel["zeit"]:
        print(f"OK – Ladezeit {ziel['zeit']} bestätigt. Ladestrom wird als '{t[0]}' angezeigt "
              f"(0,1 A erscheint gerundet als 0) – bitte in der App kontrollieren.")
        return True
    print("::warning::Neue Ladezeit noch nicht bestätigt – bitte in der App prüfen.")
    return False


def strom_passt(gelesen: str, ziel: str) -> bool:
    """Vergleicht den gelesenen Ladestrom mit dem Ziel. 0,1 A liest die API als 0,
    deshalb gilt bei Zielen unter 1 A alles bis 0,1 A als passend. Ein deutlich
    höherer Wert (z. B. 50 A aus einer früheren Einstellung) wird erkannt.
    Unlesbare Werte gelten als passend, damit nicht endlos neu geschrieben wird."""
    try:
        g, z = float(gelesen), float(ziel)
    except ValueError:
        return True
    return g <= 0.1 if z < 1 else abs(g - z) < 0.05


def ladeslot_abgleich(now: datetime, dry_run: bool) -> None:
    """Morgens: Ladeslot 1 auf den Plan der kommenden Nacht setzen, falls die Zeit
    abweicht oder der Ladestrom deutlich zu hoch ist (0,1 A liest die API als 0)."""
    heute = now.date()
    ziel = plan(heute)["ladezeit"]
    if restzeit() < 35:
        print("Ladeslot-Abgleich übersprungen (Zeitbudget) – nächster Lauf.")
        return
    alt = read_cid(CID_CHARGE_DISCHARGE)
    teile = alt.split(",")
    if len(teile) == 12 and teile[2] == ziel:
        if strom_passt(teile[0], LADESTROM):
            print(f"Ladeslot 1 passt zum Plan ({teile[2]}).")
            return
        print(f"Ladeslot 1: Zeit passt, aber Ladestrom '{teile[0]}' A statt "
              f"{LADESTROM} A – wird korrigiert.")
    else:
        print(f"Neuer Abendbeginn: Ladeslot 1 ({teile[2] if len(teile) == 12 else '?'}) → {ziel}.")
    setze_ladeslot(heute, dry_run, alt)


def odsoc_aktiv() -> bool:
    return ODSOC_STEUERN and ODSOC_NORMAL is not None


def setze_entladegrenze(d: date, dry_run: bool, alt: str | None = None) -> bool:
    """Setzt den Overdischarge-SOC (ODSOC_CID) auf den Plan der Nacht ab Tag d.
    Ein Schreibbefehl, danach Kontrolle durch Zurücklesen."""
    ziel = plan(d)["odsoc"]
    if alt is None:
        alt = read_cid(ODSOC_CID)
    try:
        ist = int(float(alt))
    except ValueError:
        raise Fehler(f"Entladegrenze (CID {ODSOC_CID}) unlesbar: {alt!r}")
    if not 5 <= ziel <= 50:
        raise Fehler(f"Entladegrenze {ziel} % außerhalb 5–50 % – bitte MONATSPLAN prüfen")
    if ist == ziel:
        print(f"Entladegrenze passt zum Plan ({ist} %).")
        return True
    print(f"Entladegrenze {ist} % → {ziel} % (Plan ab {d:%d.%m.})")
    if dry_run:
        print("Dry-Run – es wurde nichts geschrieben.")
        return True
    write_cid(ODSOC_CID, str(ziel), alt)
    print("Schreibbefehl von der Cloud angenommen.")
    if restzeit() < 25:
        protokolliere("ENTLADEGRENZE", None, f"{ist} → {ziel} %, ohne Kontrolle (Zeitbudget)")
        print("Kein Zeitbudget mehr für die Kontrolle – der nächste Lauf prüft erneut.")
        return True
    time.sleep(15)
    zurueck = read_cid(ODSOC_CID)
    ok = zurueck.strip() not in ("", "-") and int(float(zurueck)) == ziel
    protokolliere("ENTLADEGRENZE", None, f"{ist} → {ziel} %, {'bestätigt' if ok else 'unbestätigt'}")
    if ok:
        print(f"OK – Entladegrenze {ziel} % bestätigt.")
        return True
    print(f"::warning::Entladegrenze noch nicht bestätigt (gelesen: {zurueck}) – der nächste Lauf prüft erneut.")
    return False


def entladegrenze_abgleich(now: datetime, dry_run: bool) -> None:
    """Morgens: Entladegrenze mit dem Plan der kommenden Nacht vergleichen (nur lesen),
    bei Abweichung einmal schreiben. Fehlt das Zeitbudget, macht es der nächste Lauf."""
    if restzeit() < 35:
        print("Entladegrenze-Abgleich übersprungen (Zeitbudget) – nächster Lauf.")
        return
    setze_entladegrenze(now.date(), dry_run)


def zeige_grenzen() -> None:
    """Liest die Kandidaten-CIDs für SOC-Grenzen (nur lesen) – zum Abgleich mit der Solis-App."""
    print("SOC-Grenzen (nur gelesen) – bitte mit den Werten in der Solis-App vergleichen:")
    for cid, text in GRENZEN_KANDIDATEN.items():
        try:
            wert = read_cid(cid)
        except Fehler as e:
            wert = f"nicht lesbar ({e})"
        print(f"  CID {cid}: {wert!s:>6}   ({text})")
    print(f"Eingestellt: ODSOC_CID = {ODSOC_CID}, Steuerung {'AKTIV' if odsoc_aktiv() else 'aus'}")


def main() -> int:
    p = argparse.ArgumentParser(description="Solis TOU / Akku-Schlaf per SolisCloud-API")
    p.add_argument("command", choices=["status", "auto", "on", "off", "ladeslot", "grenzen", "protokoll"])
    p.add_argument("--dry-run", action="store_true", help="nur anzeigen, nichts schreiben")
    a = p.parse_args()

    now = datetime.now()
    print(f"--- {now:%Y-%m-%d %H:%M} · {a.command} · Nacht vom {nacht_datum(now):%d.%m.} · "
          f"Plan {plan_text(nacht_datum(now))} ---")

    if a.command == "protokoll":
        if not PROTOKOLL_AKTIV:
            print("Protokoll ist nicht eingerichtet (PROTOKOLL_DIR / PROTOKOLL_TOKEN fehlt).")
            return 0
        print(erzeuge_markdown())
        return 0

    LOG["aktiv"] = not a.dry_run and a.command != "status"
    LOG["quelle"] = "auto" if a.command == "auto" else "manuell"
    try:
        return _ablauf(a, now)
    except CloudFehler as e:
        if a.command != "auto":
            print(f"FEHLER: {e}")
            return 1
        if phase(now) == "aus" and tou_sicher_aus():
            # Tagsüber, TOU ist laut Protokoll bereits bestätigt aus → kein Grund für Alarm
            print(f"::warning::Cloud-Problem, aber TOU ist bereits bestätigt AUS: {e}")
            protokolliere("WARNUNG", None, f"{CLOUD_PREFIX} (TOU war schon aus): {e}")
            return 0
        letzte_sicherung = phase(now) == "aus" and now.hour >= LETZTE_AUS_SICHERUNG
        if not letzte_sicherung and not aussetzer_kurz_zuvor(now):
            # Einzelner Aussetzer: der nächste Lauf holt es nach → nur Warnung, keine E-Mail
            print(f"::warning::Cloud-Aussetzer – der nächste Lauf versucht es erneut: {e}")
            protokolliere("WARNUNG", None, f"{CLOUD_PREFIX}: {e}")
            return 0
        grund = "letzte Aus-Sicherung" if letzte_sicherung else "zweimal in Folge"
        print(f"FEHLER ({grund}): {e}")
        protokolliere("FEHLER", None, f"{CLOUD_PREFIX} ({grund}): {e}")
        return 1
    except Fehler as e:
        print(f"FEHLER: {e}")
        protokolliere("FEHLER", None, str(e))
        return 1
    finally:
        if PROTOKOLL_AKTIV and (LOG["geaendert"] or (LOG["aktiv"] and not PROTOKOLL_MD.exists())):
            erzeuge_markdown()
            print("Protokoll aktualisiert.")


def _ablauf(a, now: datetime) -> int:
    if a.command == "ladeslot":
        ok = setze_ladeslot(now.date(), a.dry_run)
        if odsoc_aktiv():
            ok = setze_entladegrenze(now.date(), a.dry_run) and ok
        return 0 if ok else 1

    if a.command == "grenzen":
        zeige_grenzen()
        return 0

    if a.command in ("on", "off"):
        return 0 if schalte(a.command == "on", a.dry_run) else 1

    raw = read_cid(CID_STORAGE_MODE)
    tou_an = tou_bit(raw)
    print(f"Speichermodus: {decode(int(raw))}")

    # Morgens einmal pro Nacht den SOC festhalten (für das Protokoll)
    morgen_eintrag = (a.command == "auto" and phase(now) == "aus" and now.hour < 12
                      and not any(e["nacht"] == nacht_datum(now).isoformat() and e["ereignis"] == "MORGEN"
                                  for e in lies_ereignisse()))

    soc = None
    soc_folgefehler = False
    if a.command == "status" or morgen_eintrag or (phase(now) == "pruefen" and not tou_an):
        try:
            soc, stand = read_soc()
            print(f"SOC: {soc:.0f} %" + (f" (Stand {stand})" if stand else ""))
        except Fehler as e:
            print(f"::warning::SOC nicht lesbar: {e}")
            if phase(now) == "pruefen" and a.command == "auto":
                soc_folgefehler = aussetzer_kurz_zuvor(now)
                protokolliere("FEHLER" if soc_folgefehler else "WARNUNG", None,
                              f"{CLOUD_PREFIX}: SOC nicht lesbar" + (" (zweimal in Folge)" if soc_folgefehler else ""))
    LOG["soc"] = soc
    if morgen_eintrag:
        protokolliere("MORGEN", soc, f"TOU war {'an' if tou_an else 'aus'}")

    soll, grund = entscheide(now, tou_an, soc)
    print(f"Entscheidung: {grund}")

    if a.command == "status":
        n, h = plan(nacht_datum(now)), plan(now.date())
        print(f"Plan dieser Nacht: Prüfung ab {n['abend']}:{SLOT_MINUTE:02d}, letzte {PRUEF_ENDE}:{SLOT_MINUTE:02d} Uhr, SOC <= {n['soc']} %, "
              f"Ladeslot {n['ladezeit']} mit {LADESTROM} A")
        if h != n:
            print(f"Plan ab heute Abend: {plan_text(now.date())}, Ladeslot {h['ladezeit']}")
        if odsoc_aktiv():
            try:
                print(f"Entladegrenze (CID {ODSOC_CID}): {read_cid(ODSOC_CID)} %, Plan ab heute Abend {h['odsoc']} %")
            except Fehler as e:
                print(f"Entladegrenze nicht lesbar: {e}")
        else:
            print("Entladegrenze: Steuerung aus (erst CID mit 'grenzen' prüfen, dann ODSOC_STEUERN = True)")
        try:
            print(f"Lade-/Entladezeiten (CID {CID_CHARGE_DISCHARGE}): {read_cid(CID_CHARGE_DISCHARGE)}")
        except Fehler as e:
            print(f"Lade-/Entladezeiten nicht lesbar: {e}")
        return 0

    rc = 0
    if soll is not None:
        ok = schalte(soll, a.dry_run)
        if not ok and soll is False and now.hour >= LETZTE_AUS_SICHERUNG:
            print("FEHLER: Letzte Aus-Sicherung – TOU ist noch AN. Bitte in der App ausschalten!")
            protokolliere("FEHLER", None, "letzte Aus-Sicherung: TOU noch AN")
            rc = 1
    elif soc_folgefehler:
        rc = 1   # SOC zweimal in Folge nicht lesbar → roter Lauf + E-Mail

    if LADESLOT_ABGLEICH and phase(now) == "aus":
        try:
            ladeslot_abgleich(now, a.dry_run)
        except Fehler as e:
            print(f"::warning::Ladeslot-Abgleich fehlgeschlagen: {e}")
        if odsoc_aktiv():
            try:
                entladegrenze_abgleich(now, a.dry_run)
            except Fehler as e:
                print(f"::warning::Entladegrenze-Abgleich fehlgeschlagen: {e}")
                protokolliere("WARNUNG", None, f"Entladegrenze-Abgleich: {e}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
