# Zeitplan der Läufe (Ortszeit Deutschland)

Die Zeiten sind geplante Startzeiten. GitHub startet oft 5–15 Minuten später.

## Winter (Nächte vom 01.10. bis 15.03.): Prüfung 18–06 Uhr, SOC ≤ 30 %, Ladeslot 18:00–07:00

| Startzeit | Oktober bis 24.10. und ab 28.03. (Sommerzeit) | 25.10. bis 27.03. (Winterzeit) |
|---|---|---|
| 17:05 | – (kein Lauf) | Aus-Sicherung |
| 18:05 | Prüfung → ggf. **EIN** | Prüfung → ggf. **EIN** |
| 19:05 … 05:05 | Prüfung → ggf. EIN (stündlich) | Prüfung → ggf. EIN (stündlich) |
| 06:05 | letzte Prüfung → ggf. EIN | letzte Prüfung → ggf. EIN |
| 07:05 | **AUS** + Ladeslot-Abgleich | **AUS** + Ladeslot-Abgleich |
| 08:05 | Aus-Sicherung | Aus-Sicherung |
| 09:05 | Aus-Sicherung | Aus-Sicherung |
| 10:05 | Aus-Sicherung, **Fehler-Mail, falls TOU noch AN** | letzte Aus-Sicherung, **Fehler-Mail, falls TOU noch AN** |
| 11:05 | letzte Aus-Sicherung, Fehler-Mail | – (kein Lauf) |

## Sommer (Nächte vom 16.03. bis 30.09.): Prüfung 20–06 Uhr, SOC ≤ 15 %, Ladeslot 20:00–07:00

| Startzeit | April–September |
|---|---|
| 20:05 | Prüfung → ggf. **EIN** |
| 21:05 … 05:05 | Prüfung → ggf. EIN (stündlich) |
| 06:05 | letzte Prüfung → ggf. EIN |
| 07:05 | **AUS** + Ladeslot-Abgleich |
| 08:05 | Aus-Sicherung |
| 09:05 | Aus-Sicherung |
| 10:05 | letzte Aus-Sicherung, **Fehler-Mail, falls TOU noch AN** |

Vom 16. bis 31. März laufen noch die Winter-Startzeiten, also schon ab 17:05 bzw. 18:05. Bis 20 Uhr wird dabei nur „aus“ geprüft, die SOC-Prüfung beginnt erst um 20:05.

## Saisonwechsel

| Datum | Was passiert |
|---|---|
| 16.03., 07:05 | TOU aus (Ende der letzten Winternacht), Ladeslot 1 wird auf **20:00–07:00 / 0,1 A** gesetzt |
| 01.10., 07:05 | TOU aus, Ladeslot 1 wird auf **18:00–07:00 / 0,1 A** gesetzt |

Der Abgleich läuft bei jedem morgendlichen Lauf. Er schreibt aber nur, wenn die Ladezeit vom Saisonprofil abweicht. Klappt es um 07:05 nicht, holen es die Läufe um 08:05–10:05 nach.

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
