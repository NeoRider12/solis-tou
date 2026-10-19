# Solis Time of Use – Akkus nachts schlafen legen

Steuert den „Time of Use“-Schalter (TOU) eines Solis RAI-3K-48ES-5G über die SolisCloud-API. Das läuft ganzjährig per GitHub Actions, ohne eigene Hardware.

> Privates Hobbyprojekt, ohne Gewähr. Es schreibt Einstellungen in deinen Wechselrichter. Nutzung auf eigenes Risiko (siehe `LICENSE`).

> **Getestet mit:** Solis RAI-3K-48ES-5G und 4× Pylontech US5000. Andere Modelle oder Firmware-Stände können die Register anders belegen – vor dem ersten scharfen Lauf unbedingt Schritt 6 der Einrichtung durchgehen.

## Prinzip

Im Wechselrichter ist ein **Ladeslot mit 0,1 A** eingestellt. Ist TOU an, lädt der Wechselrichter in dieser Zeit minimal, und die Pylontech-BMS gehen schlafen. Das Skript schaltet TOU nachts nur ein, wenn der SOC unter die Schwelle der Saison fällt. Morgens schaltet es TOU wieder aus.

| | Winter (01.10.–15.03.) | Sommer (16.03.–30.09.) |
|---|---|---|
| SOC-Prüfung, stündlich | 18:00–06:59 | 20:00–06:59 |
| TOU an bei | **SOC ≤ 30 %** | **SOC ≤ 15 %** |
| Ladeslot 1 | 18:00–07:00, 0,1 A | 20:00–07:00, 0,1 A |
| TOU aus | ab 07:00, Sicherungen bis 10/11 Uhr | ab 07:00, Sicherungen bis 10 Uhr |

- In der Prüfphase wird **nur eingeschaltet, nie ausgeschaltet**.
- **Saisonwechsel:** Morgens prüft das Skript, ob Ladeslot 1 zur kommenden Nacht passt. Am 16.03. und am 01.10. setzt es ihn automatisch auf das neue Profil. Die Entladezeiten und die Slots 2 und 3 bleiben dabei unverändert.
- Eine Nacht zählt zum Tag, an dem sie beginnt. Die Nacht vom 15. auf den 16. März ist also noch eine Winternacht.

## Aufbau: öffentlich steuern, privat protokollieren

| Repository | Sichtbarkeit | Inhalt |
|---|---|---|
| dieses Repo (z. B. `solis-tou`) | **öffentlich** | Skript + Workflow. Öffentliche Repos verbrauchen keine Actions-Minuten. |
| `solis-protokoll` | **privat** | `protokoll/ereignisse.csv` und `PROTOKOLL.md`. Der Workflow schreibt dort hinein. |

Zugangsdaten stehen nie im Code, sondern nur in den **Secrets** dieses Repos. Secrets sind auch in öffentlichen Repos nicht einsehbar und werden in Logs automatisch als `***` ausgeblendet.

## Dateien

| Datei | Zweck |
|---|---|
| `solis_tou.py` | Das Skript (status / auto / on / off / sommer / winter / protokoll) |
| `requirements.txt` | Python-Abhängigkeit (`requests`) |
| `.github/workflows/solis-tou.yml` | Zeitplan, manueller Start, Protokoll-Speicherung, Keepalive |
| `ZEITPLAN.md` | Tabelle aller Läufe und Schaltzeiten |

## Einrichtung

0. **SolisCloud-API beantragen:** In SolisCloud den API-Zugang anfordern (KeyID + KeySecret) und dabei ausdrücklich die **Steuerungsfreigabe (Device Control)** mit beantragen. Ohne sie kann das Skript nur lesen, jeder Schreibbefehl wird abgelehnt.
1. **Privates Repo** `solis-protokoll` anlegen (darf leer sein oder die bisherigen Protokolldateien enthalten).
2. **Fine-grained Token** erstellen: nur Zugriff auf `solis-protokoll`, Berechtigung *Contents: Read and write*.
3. **Dieses Repo** öffentlich anlegen und den Ordnerinhalt hochladen (inkl. `.github/workflows/`).
4. **Secrets** unter *Settings → Secrets and variables → Actions → New repository secret*:

   | Secret | Inhalt |
   |---|---|
   | `SOLIS_KEY_ID` | API KeyID aus SolisCloud |
   | `SOLIS_KEY_SECRET` | API KeySecret aus SolisCloud |
   | `SOLIS_INVERTER_SN` | Seriennummer des Wechselrichters |
   | `PROTOKOLL_TOKEN` | der Fine-grained Token aus Schritt 2 |

   Heißt das Protokoll-Repo anders, lege unter *Variables* die Variable `PROTOKOLL_REPO` an (z. B. `meinname/anderer-name`).
5. **Manuell starten** unter *Actions → Solis Time of Use → Run workflow*:
   - `status` zeigt Saison, Speichermodus, SOC, Ladeslots und die aktuelle Entscheidung.
   - `auto` führt den normalen Lauf aus. Mit Dry-Run siehst du nur, was geschaltet würde.
   - `on` / `off` schalten TOU sofort.
   - `sommer` / `winter` setzen Ladeslot 1 sofort auf das jeweilige Saisonprofil.
   - `protokoll` erzeugt `PROTOKOLL.md` im privaten Repo neu und zeigt die Tabelle im Log an.
6. **Erster Test und Ladeslot setzen:**
   - `status` starten und prüfen: Der Speichermodus (CID 636) sollte **1** (TOU aus) bzw. **3** (TOU an) zeigen. Steht dort etwas anderes, ist dein Gerät anders belegt – dann **nicht** scharf schalten, sondern erst die Bits prüfen.
   - `auto` mit Dry-Run starten und die Entscheidung im Log ansehen.
   - Einmal `winter` bzw. `sommer` (je nach aktueller Saison) **ohne** Dry-Run starten. Damit steht Ladeslot 1 sicher auf **0,1 A** und der richtigen Zeit. Wichtig, falls dort vorher ein höherer Ladestrom eingestellt war: Sonst lädt der Wechselrichter nachts mit diesem Strom aus dem Netz, sobald TOU angeht.
   - Danach in der Solis-App kontrollieren, dass Slot 1 wirklich 0,1 A zeigt (die API liest 0,1 A als `0`).

**Zeitzone:** Workflow und Skript rechnen mit deutscher Ortszeit (`TZ: Europe/Berlin` im Workflow), der `cron` ist darauf abgestimmt. Wer woanders wohnt, muss `TZ` und die `cron`-Zeilen anpassen (GitHub rechnet `cron` immer in UTC).

## Was öffentlich sichtbar ist

- **Liste der Läufe** (Uhrzeit, Dauer, grün/rot): für jeden sichtbar, nicht abschaltbar.
- **Zeitplan-Läufe laufen im stillen Modus:** Das Log zeigt nur `Lauf OK`, eine Warnung oder einen Fehler – keine SOC-Werte, keinen Speichermodus, keine Ladeslots. Bei Warnung oder Fehler legt der Workflow das vollständige Log ins private Repo: `protokoll/letzter-problemlauf.txt`.
- **Manuelle Läufe** (`status`, `on`, …) zeigen die volle Ausgabe. Danach bei Bedarf löschen: Lauf öffnen → „…“ → *Delete workflow run*.
- **Zugangsdaten** erscheinen nie, sie werden immer als `***` ausgeblendet.
- **Empfehlung:** *Settings → Actions → General → Artifact and log retention* auf **1 Tag** stellen.

## Einstellungen (oben in `solis_tou.py`)

```python
SAISONS = {
    "winter": {"beginn": (10, 1), "soc": 30, "pruef_beginn": 18,
               "ladezeit": "18:00-07:00", "strom": "0.1"},
    "sommer": {"beginn": (3, 16), "soc": 15, "pruef_beginn": 20,
               "ladezeit": "20:00-07:00", "strom": "0.1"},
}
PRUEF_ENDE = 6            # letzte Prüfung 06:00–06:59
AUS_BEGINN = 7            # ab hier TOU aus
LETZTE_AUS_SICHERUNG = 10
LADESLOT_ABGLEICH = True  # False = Ladeslot nie automatisch ändern
```

Wenn du `pruef_beginn` änderst, prüf auch den `cron` im Workflow. Die Läufe müssen die neue Uhrzeit abdecken.

## Protokoll

Öffne `PROTOKOLL.md` im **privaten** Repo `solis-protokoll` auf GitHub. Die Datei wird dort als Tabelle angezeigt, auch in der GitHub-App am Handy.

Die Tabellen sind bewusst schmal gehalten, damit sie auch am Handy im Hochformat passen. Die Spalten sind ganz unten in `PROTOKOLL.md` in einer Legende erklärt. Hinweise (Fehler, manuelle Schaltungen, Ladeslot-Wechsel) stehen als Liste unter der Tabelle, die betroffene Nacht ist mit ⚠ markiert. Es werden höchstens 15 Nächte mit Hinweisen aufgelistet (`HINWEISE_MAX`), ältere stehen in der CSV.

Darunter folgt eine **Monatsübersicht** mit einer Zeile pro Monat (neueste oben, bis zu 60 Monate). Sie zeigt Nächte mit Schlaf, durchgelaufene Nächte, Ø SOC beim Einschalten, Ø Schlafzeit und Fehler. Die Anzahl der Tage bzw. Monate stellst du oben im Skript mit `PROTOKOLL_TAGE` und `MONATS_UEBERSICHT` ein.

So funktioniert es:
- Der Workflow holt `solis-protokoll` mit dem `PROTOKOLL_TOKEN` in den Unterordner `protokoll-repo` und übergibt ihn dem Skript als `PROTOKOLL_DIR`.
- Das Skript schreibt jede Schaltung sowie morgens einmal den SOC in `protokoll/ereignisse.csv` und erzeugt daraus `PROTOKOLL.md`.
- Der Workflow committet beide Dateien ins private Repo, aber nur, wenn sich etwas geändert hat (meist 1–2 kleine Commits pro Tag).
- Dry-Runs und `status` werden nicht protokolliert.
- **Fehlt der Token oder ist er ungültig, läuft die Steuerung trotzdem**, nur ohne Protokoll. Im Lauf erscheint dann eine gelbe Warnung.

**Wichtig für GitHub Desktop:** Im Repo `solis-protokoll` schreibt der Workflow selbst. Wenn du es lokal geklont hast, vor eigenen Änderungen immer zuerst **„Fetch origin“ / „Pull origin“**. Im öffentlichen Repo kommt nur alle ~45 Tage ein leerer Keepalive-Commit dazu, auch hier also vor einem Push kurz „Pull“.

## 60-Tage-Regel (Keepalive)

GitHub deaktiviert Zeitpläne in öffentlichen Repos, wenn dort 60 Tage lang kein Commit war. Da das Protokoll ins private Repo geht, legt der Workflow im öffentlichen Repo automatisch einen **leeren Commit** „keepalive“ an, sobald der letzte Commit 45 Tage alt ist. Der Commit enthält keinerlei Daten.

Sollte der Zeitplan trotzdem einmal deaktiviert werden, schickt GitHub vorher eine E-Mail. Dann unter *Actions → Solis Time of Use* auf **„Enable workflow“** klicken.

## Sicherheit

- Beim TOU-Schalten ändert das Skript nur Bit 1 im Speichermodus-Register (CID 636 ≙ Modbus 43110). Alle anderen Bits bleiben unverändert.
- Beim Ladeslot ändert es nur Ladestrom und Ladezeit von Slot 1 (CID 103).
- **Pro Lauf gibt es höchstens einen Schreibbefehl je Register.** Danach wird zurückgelesen. Ist der neue Wert nicht bestätigt, gibt es eine gelbe Warnung, und der nächste Lauf prüft erneut.
- Der Ladestrom 0,1 A wird von der API als `0` gelesen, intern arbeitet der Wechselrichter aber mit 0,1 A. Beim morgendlichen Abgleich gilt deshalb ein gelesener Strom bis 0,1 A als passend; ein deutlich höherer Wert (z. B. 50 A) wird erkannt und auf 0,1 A korrigiert.
- **Fehler mit E-Mail** gibt es in diesen Fällen:
  - Die API lehnt einen Befehl ab.
  - Der SOC ist nachts nicht lesbar.
  - Die letzte Aus-Sicherung am Vormittag findet TOU noch AN vor.
- **Kein Alarm bei harmlosen Cloud-Aussetzern:** Ist TOU laut Protokoll schon bestätigt AUS, erzeugt ein Cloud-Fehler tagsüber nur eine gelbe Warnung und einen Hinweis im Protokoll, aber keine E-Mail.
- Fällt das Ausschalten am Morgen komplett aus, passiert tagsüber nichts: Außerhalb des Ladeslots arbeitet der Wechselrichter trotz TOU normal im Self-Use.
- Notfall: unter *Actions → Run workflow* `off` ohne Dry-Run wählen. Oder in der Solis-App TOU ausschalten.
- **Forks und Pull Requests** fremder Leute bekommen keinen Zugriff auf deine Secrets, und der Workflow reagiert nicht auf Pull Requests.

## Actions-Minuten

In **öffentlichen** Repos sind die Minuten auf Standard-Runnern kostenlos und werden nicht vom Kontingent abgezogen. Zur Einordnung trotzdem der Verbrauch (jeder Lauf zählt als volle Minute):

| Fall | Winter (18 Läufe/Tag) | Sommer (15 Läufe/Tag) |
|---|---|---|
| Normal | ca. 570–620 min/Monat | ca. 470–530 min/Monat |
| Schlecht (Solis-Cloud den ganzen Monat gestört) | ca. 1.120 min | ca. 930 min |

Das Skript bricht nach spätestens 80 s ab, die Notbremse von GitHub greift nach 3 min.

Den genauen Zeitplan aller Läufe findest du in `ZEITPLAN.md`.
