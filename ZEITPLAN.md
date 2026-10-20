# Zeitplan der Läufe (Ortszeit Deutschland)

Gestartet wird von cron-job.org: jeden Tag zur Minute 5, von **18:05 bis 10:05 Uhr**, ganzjährig gleich und direkt in deutscher Ortszeit (Sommer-/Winterzeit egal). GitHub braucht danach meist nur wenige Sekunden bis zum Start.

## Winter (Nächte vom 01.10. bis 15.03.): Prüfung 18–06 Uhr, SOC ≤ 30 %, Ladeslot 18:00–07:00

| Startzeit | Was passiert |
|---|---|
| 18:05 | Prüfung → ggf. **EIN** |
| 19:05 … 05:05 | Prüfung → ggf. EIN (stündlich) |
| 06:05 | letzte Prüfung → ggf. EIN |
| 07:05 | **AUS** + Ladeslot-Abgleich |
| 08:05, 09:05 | Aus-Sicherung |
| 10:05 | letzte Aus-Sicherung, **Fehler-Mail, falls TOU noch AN** |

## Sommer (Nächte vom 16.03. bis 30.09.): Prüfung 20–06 Uhr, SOC ≤ 15 %, Ladeslot 20:00–07:00

| Startzeit | Was passiert |
|---|---|
| 18:05, 19:05 | Aus-Sicherung (Tag – TOU bleibt aus) |
| 20:05 | Prüfung → ggf. **EIN** |
| 21:05 … 05:05 | Prüfung → ggf. EIN (stündlich) |
| 06:05 | letzte Prüfung → ggf. EIN |
| 07:05 | **AUS** + Ladeslot-Abgleich |
| 08:05, 09:05 | Aus-Sicherung |
| 10:05 | letzte Aus-Sicherung, **Fehler-Mail, falls TOU noch AN** |

## Saisonwechsel

| Datum | Was passiert |
|---|---|
| 16.03., 07:05 | TOU aus (Ende der letzten Winternacht), Ladeslot 1 wird auf **20:00–07:00 / 0,1 A** gesetzt |
| 01.10., 07:05 | TOU aus, Ladeslot 1 wird auf **18:00–07:00 / 0,1 A** gesetzt |

Der Abgleich läuft bei jedem morgendlichen Lauf. Er schreibt aber nur, wenn die Ladezeit vom Saisonprofil abweicht oder der Ladestrom deutlich über 0,1 A liegt. Klappt es um 07:05 nicht, holen es die Läufe um 08:05–10:05 nach.

## Legende

- **Prüfung → ggf. EIN:** Ist TOU schon an, passiert nichts. Ist TOU aus, wird der SOC gelesen und bei SOC ≤ Schwelle eingeschaltet. In der Prüfphase wird nie ausgeschaltet.
- **AUS / Aus-Sicherung:** Ist TOU an, wird es ausgeschaltet. Ist es schon aus, wird nur gelesen.

## Ablauf einer einzelnen Schaltung (ab Startzeit)

| Zeitpunkt (ca.) | Schritt |
|---|---|
| +0:20 | Skript startet und liest den Speichermodus |
| +0:25 | **ein** Schreibbefehl (nur das TOU-Bit) |
| +0:40 | 1. Kontrolle durch Zurücklesen; wenn bestätigt → fertig |
| +1:10 | 2. Kontrolle; wenn bestätigt → fertig, sonst gelbe Warnung |
| nächste volle Stunde | nächster Lauf liest neu und schreibt bei Bedarf erneut |
