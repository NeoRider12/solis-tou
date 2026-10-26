# Zeitplan der Läufe (Ortszeit Deutschland)

Gestartet wird von cron-job.org: jeden Tag zur Minute 15, von **16:15 bis 10:15 Uhr**, ganzjährig gleich und direkt in deutscher Ortszeit. GitHub braucht danach meist nur wenige Sekunden bis zum Start.

Was ein Lauf tut, hängt vom **Abendbeginn** des Monats ab (siehe `MONATSPLAN` im Skript bzw. README):

| Startzeit | Was passiert |
|---|---|
| 16:15 bis vor Abendbeginn | Aus-Sicherung (Tag – TOU bleibt aus) |
| ab Abendbeginn (z. B. Dez 16:15, Juni 21:15) | Prüfung → ggf. **EIN** |
| stündlich bis 05:15 | Prüfung → ggf. EIN |
| 06:15 | letzte Prüfung → ggf. EIN |
| 07:15 | **AUS** + Ladeslot-Abgleich |
| 08:15, 09:15 | Aus-Sicherung |
| 10:15 | letzte Aus-Sicherung, **Fehler-Mail, falls TOU noch AN** |

## Wann der Ladeslot neu geschrieben wird

Immer morgens um 07:15 für die kommende Nacht, aber nur, wenn sich der Abendbeginn ändert:

| Datum | Ladeslot 1 |
|---|---|
| 01.01. | 17:00–07:00 |
| 01.02. | 18:00–07:00 |
| Beginn Sommerzeit (letzter So. im März) | 19:00–07:00 |
| 01.04. | 20:00–07:00 |
| 01.05. | 21:00–07:00 |
| 01.09. | 20:00–07:00 |
| 01.10. | 19:00–07:00 |
| Ende Sommerzeit (letzter So. im Oktober) | 17:00–07:00 |
| 01.12. | 16:00–07:00 |

Dazu prüft jeder Morgenlauf, ob der Ladestrom noch 0,1 A beträgt. Klappt das Schreiben um 07:15 nicht, holen es die Läufe um 08:15–10:15 nach.

## Legende

- **Prüfung → ggf. EIN:** Ist TOU schon an, passiert nichts. Ist TOU aus, wird der SOC gelesen und bei SOC ≤ Schwelle des Monats eingeschaltet. In der Prüfphase wird nie ausgeschaltet.
- **AUS / Aus-Sicherung:** Ist TOU an, wird es ausgeschaltet. Ist es schon aus, wird nur gelesen.

## Ablauf einer einzelnen Schaltung (ab Startzeit)

| Zeitpunkt (ca.) | Schritt |
|---|---|
| +0:20 | Skript startet und liest den Speichermodus |
| +0:25 | **ein** Schreibbefehl (nur das TOU-Bit) |
| +0:40 | 1. Kontrolle durch Zurücklesen; wenn bestätigt → fertig |
| +1:10 | 2. Kontrolle; wenn bestätigt → fertig, sonst gelbe Warnung |
| nächste volle Stunde | nächster Lauf liest neu und schreibt bei Bedarf erneut |
