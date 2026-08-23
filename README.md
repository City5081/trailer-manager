# Trailer DE

Trägt deutsche Trailer von [themoviedb.org](https://www.themoviedb.org) in die
`.nfo`-Dateien einer Emby-Filmbibliothek ein – per Zeitplan, per Knopfdruck oder
sofort, wenn Emby bzw. Jellyseerr einen neuen Film meldet.

Hintergrund: Emby holt sich seine Trailer selbst von TMDB und landet dabei fast
immer beim englischen. Steht dagegen ein `<trailer>`-Eintrag in der NFO, nimmt
Emby diesen.

## Funktionen

- **Dauerhafte Datenbank** (SQLite): Ein Automatiklauf fragt nur Filme ab, die
  neu sind, deren NFO sich geändert hat oder die beim letzten Mal keinen Trailer
  hatten. Bei 1600 Filmen dauert der zweite Lauf Sekunden statt Stunden.
- **Zeitplan** in einstellbarem Intervall, dazu ein Lauf beim Start.
- **Webhook** für Emby, Jellyfin und Jellyseerr: neuer Film → Trailer sofort gesetzt.
- **Weboberfläche** mit Filmliste, Suche, Filtern, Einzelsuche und manueller
  Bearbeitung des Links; jeder Trailer lässt sich vorab auf YouTube ansehen.
- **Anmeldung** mit Benutzername und Passwort, Webhook separat per Token gesichert.
- **Zweisprachig** Deutsch/Englisch, in der Kopfzeile umschaltbar.
- **Robuste TMDB-Abfrage**: Der `language`-Filter der Videos-Schnittstelle liefert
  je nach Sprach-/Regionskombination nichts, obwohl das Video existiert. Deshalb
  wird bei Bedarf mehrfach abgefragt und anhand des Sprachfelds am Video selbst
  sortiert. Sobald etwas in der gewünschten Sprache dabei ist, hört die Abfrage auf.
- **Beide Linkformate**: `plugin://plugin.video.youtube/play/?video_id=…` (das,
  was Emby schreibt), das ältere Kodi-Format und normale YouTube-URLs.
- **Sicheres Schreiben**: Die NFO wird erst in eine Nachbardatei geschrieben und
  dann umbenannt. Bricht der Vorgang ab, bleibt die alte Datei unversehrt.

## Schnellstart

```bash
git clone https://github.com/City5081/trailer-de.git
cd trailer-de
cp .env.example .env          # ausfüllen: TMDB_API_KEY, WEB_PASSWORD, WEBHOOK_TOKEN, MOVIES_PATH
docker compose up -d --build
```

Danach `http://SERVER:8099` aufrufen und anmelden.

Statt selbst zu bauen lässt sich auch das fertige Image verwenden – in der
`docker-compose.yml` `build: .` auskommentieren und die `image:`-Zeile aktivieren:

```
ghcr.io/city5081/trailer-de:latest
```

Der Image-Name ist durchgehend klein geschrieben: Docker lässt in Image-Namen
keine Großbuchstaben zu, auch wenn der GitHub-Benutzername welche hat. Die
Action schreibt aus demselben Grund nach `city5081`.

Zufallswerte für `SECRET_KEY` und `WEBHOOK_TOKEN`:

```bash
openssl rand -hex 32
```

### Unraid

Für den Compose Manager liegt eine eigene Fassung bereit:
[`docker-compose.unraid.yml`](docker-compose.unraid.yml) – ohne `build:` und ohne
`env_file:`, denn der Compose Manager legt auf dem Server weder ein
Quellverzeichnis noch eine `.env` an. Inhalt in *Edit Stack* einfügen, Werte
eintragen, fertig.

Alternativ über *Docker → Add Container*. Wichtig ist in beiden Fällen:

| Pfad/Variable | Wert |
|---|---|
| `/movies` | Freigabe mit den Filmen, **Read/Write** |
| `/config` | z. B. `/mnt/user/appdata/trailer-de` |
| Port | `8099` → `8080` |
| `PUID` / `PGID` | `99` / `100` |

Der Container startet als root, stellt den Benutzer `app` auf `PUID`/`PGID` um
und gibt die Rechte dann ab. Neu geschriebene NFOs gehören damit demselben
Benutzer wie der Rest der Freigabe.

Wenn die NFOs Emby oder einem anderen Container gehören, hilft
*Tools → New Permissions*, sonst scheitert das Schreiben mit „Permission denied".
Was genau klemmt, zeigt in der Detailansicht eines Films der Knopf
*Schreibrechte prüfen*.

## Konfiguration

Alles lässt sich per Umgebungsvariable vorgeben und später in der Oberfläche
ändern – die Einstellungen aus der Oberfläche haben Vorrang. Vollständige
Vorlage: [`.env.example`](.env.example).

| Variable | Bedeutung |
|---|---|
| `WEB_USERNAME`, `WEB_PASSWORD` | Zugang zur Oberfläche |
| `WEB_PASSWORD_HASH` | statt Klartext; erzeugen mit `tools/hash_password.py` |
| `SECRET_KEY` | Sitzungsschlüssel (sonst automatisch unter `/config`) |
| `COOKIE_SECURE` | `true` hinter einem Reverse Proxy mit TLS |
| `SESSION_DAYS` | wie lange eine Anmeldung gilt (Voreinstellung 30) |
| `TMDB_API_KEY` | **v3-API-Key**, nicht das Read-Access-Token |
| `LANGUAGES` | `de` = ausschließlich deutsche Trailer, `de,en` mit Rückfall |
| `LINK_FORMAT` | `emby`, `kodi` oder `url` |
| `KEEP_FORMAT` | vorhandene Schreibweise beibehalten |
| `BACKUP` | vor der ersten Änderung eine `.nfo.bak` anlegen |
| `SCAN_INTERVAL_HOURS` | Intervall, `0` schaltet den Zeitplan ab |
| `SCAN_ON_START` | Lauf beim Start des Containers |
| `RECHECK_DAYS` | erfolglose Filme nach so vielen Tagen erneut prüfen |
| `UI_LANGUAGE` | `de` oder `en` |
| `WEBHOOK_TOKEN` | Token für die Webhook-Adresse; **ohne Token bleibt der Webhook zu** |
| `AUTH_DISABLED` | `true` nur, wenn eine Gegenstelle die Anmeldung übernimmt |
| `PUID` / `PGID` | Benutzer- und Gruppenkennung für geschriebene Dateien |

Host-seitig steuern `HOST_PORT`, `MOVIES_PATH` und `CONFIG_PATH` in der `.env`,
was die `docker-compose.yml` einhängt.

## Webhook einrichten

Die fertige Adresse steht in der Oberfläche unter *Einstellungen → Webhook*:

```
http://SERVER:8099/webhook?token=DEIN_TOKEN
```

**Emby:** Einstellungen → Notifications → Webhooks. Ereignis *New Media Added*
genügt, Format JSON.

**Jellyseerr:** Settings → Notifications → Webhook, bei *Media Available*.

Das Tool sucht den Film zuerst über den Dateipfad aus der Meldung, sonst über die
TMDB-ID; ist er noch unbekannt, wird sein Ordner gezielt nachgelesen.

## Wie entschieden wird, was geprüft wird

Beim Automatiklauf werden angefasst:

- neue Filme und solche, deren NFO sich seit dem letzten Mal geändert hat
- Filme ohne Trailer-Eintrag
- Filme, bei denen früher nichts gefunden wurde und deren letzte Prüfung länger
  als `RECHECK_DAYS` zurückliegt (auf TMDB kommen ja laufend Trailer dazu)

Fertige Filme bleiben unberührt – außer *„auch fertige Filme erneut prüfen"* ist
gesetzt oder du drückst *Alle neu prüfen*.

## Sicherheit

Die Oberfläche gehört nicht ungeschützt ins Internet. Wenn du von außen zugreifen
willst, dann über einen Reverse Proxy mit TLS (z. B. Nginx Proxy Manager oder
SWAG), setze `COOKIE_SECURE=true` und ein Passwort per `WEB_PASSWORD_HASH` statt
im Klartext.

Eingebaut sind: CSRF-Token für alle Formulare, eine wachsende Wartezeit nach
wiederholt falschen Anmeldungen, `X-Frame-Options`/`nosniff`, und ein Webhook,
der ohne gesetztes `WEBHOOK_TOKEN` gar nicht erst antwortet.

## Entwicklung

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/pytest -q
.venv/bin/ruff check .
```

Lokal ohne Container starten:

```bash
DATA_DIR=./config MOVIES_DIR=/pfad/zu/Filmen WEB_PASSWORD=test .venv/bin/python app/main.py
```

## Aufbau

```
app/
  main.py      Flask-Anwendung: Anmeldung, Seiten, Webhook
  scanner.py   Einlesen, Automatiklauf, Zeitplan, Webhook-Verarbeitung
  db.py        SQLite: Filme, Protokoll, Einstellungen, Durchläufe
  tmdb.py      TMDB-Client mit robuster Sprachbehandlung
  nfo.py       NFO lesen und schreiben, Linkformate
  i18n.py      Übersetzungen DE/EN
docker/
  entrypoint.sh  setzt PUID/PGID und gibt die Rechte ab
tests/         pytest-Suite (ohne Netzzugriff)
tools/
  hash_password.py  erzeugt WEB_PASSWORD_HASH
```

## Lizenz

MIT – siehe [LICENSE](LICENSE).
