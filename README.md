# Solis Time of Use – Akkus nachts schlafen legen

Steuert den „Time of Use“-Schalter (TOU) eines Solis RAI-3K-48ES-5G über die SolisCloud-API. Das läuft ganzjährig per GitHub Actions, ohne eigene Hardware. Gestartet wird stündlich und pünktlich von [cron-job.org](https://cron-job.org).

> Privates Hobbyprojekt, ohne Gewähr. Es schreibt Einstellungen in deinen Wechselrichter. Nutzung auf eigenes Risiko (siehe `LICENSE`).

> **Getestet mit:** Solis RAI-3K-48ES-5G und 4× Pylontech US5000. Andere Modelle oder Firmware-Stände können die Register anders belegen – vor dem ersten scharfen Lauf unbedingt Schritt 6 der Einrichtung durchgehen.

## Prinzip

Im Wechselrichter ist ein **Ladeslot mit 0,1 A** eingestellt. Ist TOU an, lädt der Wechselrichter in dieser Zeit minimal, und die Pylontech-BMS gehen schlafen. Das Skript prüft ab dem **Abendbeginn** stündlich den SOC und schaltet TOU ein, sobald er unter die Schwelle des Monats fällt. Morgens um 07:00 schaltet es TOU wieder aus.

**Monatsplan** (`MONATSPLAN` im Skript): Der Abendbeginn ist Sonnenuntergang −1 Std., jeweils der späteste Wert des Monats, auf die volle Stunde aufgerundet. So beginnt der Akkuschlaf nie, solange die Sonne noch laden könnte – **die Sonne hat Vorrang**. Berechnet für Norddeutschland (ca. 52° N), für andere Orte anpassen.

| Monat | Abendbeginn = Start Ladeslot 1 | TOU an bei |
|---|---|---|
| Januar | 17:00 | SOC ≤ 30 % |
| Februar | 18:00 | SOC ≤ 30 % |
| März | 18:00, ab Sommerzeit 19:00 | SOC ≤ 25 % |
| April | 20:00 | SOC ≤ 20 % |
| Mai–August | 21:00 | SOC ≤ 15 % |
| September | 20:00 | SOC ≤ 20 % |
| Oktober | 19:00, ab Winterzeit 17:00 | SOC ≤ 25 % |
| November | 17:00 | SOC ≤ 30 % |
| Dezember | 16:00 | SOC ≤ 30 % |

Ladeslot 1 läuft immer vom Abendbeginn bis **07:00** mit **0,1 A**. TOU aus ab 07:00, Aus-Sicherungen bis 10 Uhr.

- In der Prüfphase wird **nur eingeschaltet, nie ausgeschaltet**.
- **Ladeslot nachführen:** Morgens prüft das Skript, ob Ladeslot 1 zur kommenden Nacht passt, und setzt ihn bei Bedarf neu – nur bei einem neuen Abendbeginn und bei der Zeitumstellung, also ca. 8× im Jahr. Die SOC-Schwelle wird nie geschrieben, sie gilt nur im Skript. Entladezeiten und die Slots 2 und 3 bleiben unverändert.
- **Zeitumstellung:** erkennt das Skript selbst. Der Wechselrichter muss sich ebenfalls umstellen (Solis-App: *Daylight Saving* automatisch), weil die Slot-Zeiten in seiner Uhrzeit gelten.
- Eine Nacht zählt zum Tag, an dem sie beginnt. Die Nacht vom 31.01. auf den 01.02. gilt also noch als Januarnacht.

## Aufbau: öffentlich steuern, privat protokollieren

| Repository | Sichtbarkeit | Inhalt |
|---|---|---|
| dieses Repo (z. B. `solis-tou`) | **öffentlich** | Skript + Workflow. Öffentliche Repos verbrauchen keine Actions-Minuten. |
| `solis-protokoll` | **privat** | `protokoll/ereignisse.csv` und `PROTOKOLL.md`. Der Workflow schreibt dort hinein. |

Zugangsdaten stehen nie im Code, sondern nur in den **Secrets** dieses Repos. Secrets sind auch in öffentlichen Repos nicht einsehbar und werden in Logs automatisch als `***` ausgeblendet.

## Dateien

| Datei | Zweck |
|---|---|
| `solis_tou.py` | Das Skript (status / auto / on / off / ladeslot / protokoll) |
| `requirements.txt` | Python-Abhängigkeit (`requests`) |
| `.github/workflows/solis-tou.yml` | externer Start (cron-job.org), manueller Start, Protokoll-Speicherung |
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
   - `status` zeigt Plan, Speichermodus, SOC, Ladeslots und die aktuelle Entscheidung.
   - `auto` führt den normalen Lauf aus. Mit Dry-Run siehst du nur, was geschaltet würde.
   - `on` / `off` schalten TOU sofort.
   - `ladeslot` setzt Ladeslot 1 sofort auf den Plan von heute Abend.
   - `protokoll` erzeugt `PROTOKOLL.md` im privaten Repo neu und zeigt die Tabelle im Log an.
6. **Erster Test und Ladeslot setzen:**
   - `status` starten und prüfen: Der Speichermodus (CID 636) sollte **1** (TOU aus) bzw. **3** (TOU an) zeigen. Steht dort etwas anderes, ist dein Gerät anders belegt – dann **nicht** scharf schalten, sondern erst die Bits prüfen.
   - `auto` mit Dry-Run starten und die Entscheidung im Log ansehen.
   - Einmal `ladeslot` **ohne** Dry-Run starten. Damit steht Ladeslot 1 sicher auf **0,1 A** und der richtigen Zeit. Wichtig, falls dort vorher ein höherer Ladestrom eingestellt war: Sonst lädt der Wechselrichter nachts mit diesem Strom aus dem Netz, sobald TOU angeht.
   - Danach in der Solis-App kontrollieren, dass Slot 1 wirklich 0,1 A zeigt (die API liest 0,1 A als `0`).

7. **cron-job.org einrichten** (nächster Abschnitt). Ohne diesen Schritt läuft nichts automatisch.

**Zeitzone:** Das Skript rechnet mit deutscher Ortszeit (`TZ: Europe/Berlin` im Workflow), der cron-job.org-Job ebenfalls. Wer woanders wohnt, passt beides an.

## Stündlich starten mit cron-job.org

GitHubs eigener Zeitplan (`schedule`) startet nur „nach bestem Bemühen“: oft 30–60 Minuten zu spät, manchmal gar nicht. Deshalb gibt es hier keinen GitHub-Zeitplan. Stattdessen startet der kostenlose Dienst [cron-job.org](https://cron-job.org) den Workflow auf die Minute genau über die GitHub-API.

**1. Token für den Start erstellen** (GitHub → Settings → Developer settings → Fine-grained tokens):
- *Repository access:* nur dieses Repo
- *Permissions:* **Actions: Read and write** (sonst nichts)
- Ablaufdatum notieren und rechtzeitig erneuern.

**2. Job bei cron-job.org anlegen:**

| Feld | Wert |
|---|---|
| URL | `https://api.github.com/repos/<dein-name>/<dieses-repo>/actions/workflows/solis-tou.yml/dispatches` |
| Zeitplan | Benutzerdefiniert: Minute **5**, Stunden **16–23 und 0–10**, jeden Tag |
| Zeitzone | **Europe/Berlin** (dann gibt es kein Sommer-/Winterzeit-Problem) |
| Methode (Erweitert) | **POST** |
| Header | `Authorization: Bearer <Token>` · `Accept: application/vnd.github+json` · `X-GitHub-Api-Version: 2022-11-28` · `Content-Type: application/json` |
| Body | `{"ref":"main","inputs":{"command":"extern"}}` |
| Benachrichtigung | bei Fehlschlag per E-Mail |

Erfolgreich ist der Aufruf, wenn GitHub mit **204** antwortet. In der Liste der Läufe heißt er dann *„Extern (cron-job.org)“*, manuelle Läufe heißen *„Manuell: …“*. Die Stunden 16–10 decken den frühesten Abendbeginn (Dezember, 16:00) ab. Läufe vor dem Abendbeginn des Monats sind nur Aus-Sicherungen. Wird ein Abendbeginn im `MONATSPLAN` früher als 16 Uhr gelegt, den Job erweitern.

**Ohne Reserve:** Fällt cron-job.org aus, läuft nichts. Deshalb die Fehler-Benachrichtigung dort einschalten. Notfalls von Hand starten (*Run workflow* → `auto` ohne Dry-Run). Bleibt TOU morgens versehentlich an, passiert tagsüber nichts (siehe *Sicherheit*).

**Was kann jemand mit diesem Token?** Nur Läufe dieses Repos starten, abbrechen, löschen und deren Logs lesen – keinen Code ändern, keine Secrets lesen. Starten kann er auch `on`/`off`/`ladeslot`, also nur die fest im Skript hinterlegten, sicheren Aktionen (schlimmstenfalls schlafen die Akkus eine Nacht nicht). Bei Verdacht: Token in GitHub löschen, neu erstellen, bei cron-job.org tauschen.

**Actions-Minuten:** Öffentlich kostenlos. Im privaten Repo ca. 19 Läufe/Tag ≈ 590 min/Monat (frei sind 2.000).

## Was öffentlich sichtbar ist

- **Liste der Läufe** (Uhrzeit, Dauer, grün/rot): für jeden sichtbar, nicht abschaltbar.
- **Externe Läufe (cron-job.org) laufen im stillen Modus:** Das Log zeigt nur `Lauf OK`, eine Warnung oder einen Fehler – keine SOC-Werte, keinen Speichermodus, keine Ladeslots. Bei Warnung oder Fehler legt der Workflow das vollständige Log ins private Repo: `protokoll/letzter-problemlauf.txt`.
- **Manuelle Läufe** (`status`, `on`, …) zeigen die volle Ausgabe. Danach bei Bedarf löschen: Lauf öffnen → „…“ → *Delete workflow run*.
- **Zugangsdaten** erscheinen nie, sie werden immer als `***` ausgeblendet.
- **Empfehlung:** *Settings → Actions → General → Artifact and log retention* auf **1 Tag** stellen.

## Einstellungen (oben in `solis_tou.py`)

```python
MONATSPLAN = {
    1:  {"abend": 17, "soc": 30},
    # …
    3:  {"abend": 18, "abend_sz": 19, "soc": 25},   # abend_sz = solange Sommerzeit gilt
    # …
    12: {"abend": 16, "soc": 30},
}
LADESTROM = "0.1"         # Ladestrom von Slot 1 in A
PRUEF_ENDE = 6            # letzte Prüfung 06:00–06:59
AUS_BEGINN = 7            # ab hier TOU aus
LETZTE_AUS_SICHERUNG = 10
LADESLOT_ABGLEICH = True  # False = Ladeslot nie automatisch ändern
```

`soc` kannst du jederzeit ändern, das kostet keine Schreibvorgänge. Legst du einen `abend` früher als 16 Uhr, erweitere den cron-job.org-Job, damit die Läufe die neue Uhrzeit abdecken.

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

**Wichtig für GitHub Desktop:** Im Repo `solis-protokoll` schreibt der Workflow selbst. Wenn du es lokal geklont hast, vor eigenen Änderungen immer zuerst **„Fetch origin“ / „Pull origin“**.

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

In **öffentlichen** Repos sind die Minuten auf Standard-Runnern kostenlos. Im privaten Repo: ca. 19 Läufe pro Tag, jeder zählt als volle Minute → ca. 590 min/Monat, bei gestörter Solis-Cloud bis ca. 1.100 min (frei sind 2.000).

Das Skript bricht nach spätestens 80 s ab, die Notbremse von GitHub greift nach 3 min.

Den genauen Zeitplan aller Läufe findest du in `ZEITPLAN.md`.
