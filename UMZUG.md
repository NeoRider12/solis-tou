# Umzug: altes Konto → Hauptkonto (öffentlich + privates Protokoll)

Reihenfolge einhalten – so läuft die Steuerung nie doppelt und es geht kein Protokoll verloren.
Zeitbedarf: ca. 20–30 Minuten. Am besten **tagsüber** (zwischen 11 und 17 Uhr läuft kein Zeitplan).

## 1. Protokoll sichern (altes Konto)

1. In GitHub Desktop das alte Repo `Solis-4-github` öffnen → **Fetch origin / Pull origin**.
2. Aus dem lokalen Ordner diese beiden Dinge beiseitelegen:
   - Ordner `protokoll/` (darin `ereignisse.csv`)
   - Datei `PROTOKOLL.md`

## 2. Privates Protokoll-Repo anlegen (Hauptkonto)

1. Mit dem **Hauptkonto** auf github.com: **New repository**
   - Name: `solis-protokoll`
   - Sichtbarkeit: **Private**
   - Haken bei „Add a README file“ setzen (dann ist das Repo nicht leer)
2. Den Inhalt des ZIPs `solis-protokoll-start.zip` und die beiden gesicherten Dinge aus Schritt 1 hochladen, sodass im Repo liegt:
   ```
   README.md
   PROTOKOLL.md
   protokoll/ereignisse.csv
   ```
   (Per Web: *Add file → Upload files* – Ordner lassen sich per Drag & Drop hineinziehen. Oder per GitHub Desktop klonen, Dateien reinkopieren, Commit, Push.)

## 3. Token für das Protokoll erstellen

github.com → Profilbild → **Settings → Developer settings → Personal access tokens → Fine-grained tokens → Generate new token**

| Feld | Einstellung |
|---|---|
| Token name | `solis-protokoll` |
| Resource owner | dein Hauptkonto |
| Expiration | **No expiration** (oder z. B. 1 Jahr – dann im Kalender notieren) |
| Repository access | **Only select repositories** → `solis-protokoll` |
| Permissions → Repository permissions | **Contents: Read and write** (Metadata: Read wird automatisch gesetzt) |

→ **Generate token**, Token kopieren (wird nur einmal angezeigt) – gleich in Schritt 5 als Secret eintragen, nirgendwo sonst speichern.

Der Token kann ausschließlich dieses eine private Repo lesen/schreiben – sonst nichts.

## 4. Öffentliches Repo anlegen (Hauptkonto)

1. **New repository**, Name z. B. `solis-tou`, Sichtbarkeit **Public**, ohne README.
2. Inhalt von `solis-tou-public.zip` hochladen – **komplett neu, ohne die alte Git-Historie** (die alte Historie enthält Protokolldaten).
   Wichtig: der versteckte Ordner `.github/workflows/` und die Datei `.gitignore` müssen mit hoch.
   - GitHub Desktop: *File → New repository* im entpackten Ordner, dann **Publish repository**, Haken bei „Keep this code private“ **entfernen**.
3. Kontrolle auf github.com: Es dürfen **kein** `protokoll/`-Ordner und **keine** `PROTOKOLL.md` im öffentlichen Repo liegen.

## 5. Secrets eintragen (öffentliches Repo)

*Settings → Secrets and variables → Actions → New repository secret*

| Name | Wert |
|---|---|
| `SOLIS_KEY_ID` | KeyID aus SolisCloud |
| `SOLIS_KEY_SECRET` | KeySecret aus SolisCloud (**am besten vorher neu erzeugen**, siehe Schritt 9) |
| `SOLIS_INVERTER_SN` | Seriennummer |
| `PROTOKOLL_TOKEN` | Token aus Schritt 3 |

Dann: *Settings → Actions → General*
- **Artifact and log retention** → `1` Tag → Save
- „Fork pull request workflows from outside collaborators“: Standard (*Require approval*) lassen

## 6. Alten Workflow stoppen (altes Konto)

Altes Repo → **Actions → Solis Time of Use → „…“ → Disable workflow**.
Ab jetzt läuft nur noch das neue Repo.

## 7. Neues Repo testen

*Actions → Solis Time of Use → Run workflow*:

1. `status` (Dry-Run an) → zeigt SOC, Modus, Ladeslot. Prüfen: keine Zugangsdaten im Log sichtbar (nur `***`).
2. `protokoll` → im Log erscheint die Tabelle, und im privaten Repo gibt es einen neuen Commit „Protokoll …“ (nur falls sich etwas geändert hat).
   Erscheint die gelbe Warnung *„Protokoll-Repo … nicht erreichbar“*: Token-Rechte oder Repo-Name prüfen.
3. Am nächsten Morgen: Nacht im `PROTOKOLL.md` des privaten Repos kontrollieren.

## 8. Altes Repo löschen (altes Konto)

Erst wenn eine Nacht im neuen Repo sauber gelaufen ist:
Altes Repo → **Settings → ganz unten „Danger Zone“ → Delete this repository**.
Damit sind auch die alten Secrets und die alte Historie weg.

GitHub Desktop: altes Repo in der Liste rechtsklicken → *Remove* (lokalen Ordner danach selbst löschen), unter *File → Options → Accounts* auf das Hauptkonto umstellen und die beiden neuen Repos klonen.

## 9. KeySecret erneuern (empfohlen)

Das bisherige KeySecret stand im Klartext in einem Chat. Wenn SolisCloud es zulässt: dort ein neues KeySecret erzeugen und nur in das Secret `SOLIS_KEY_SECRET` des neuen Repos eintragen. Danach einmal `status` testen.
