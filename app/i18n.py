"""Bilingual interface (German / English).

Switch in the header; the choice lives in the session, the default comes from
the settings or from UI_LANGUAGE.
"""

LANGUAGES = {"de": "Deutsch", "en": "English"}

STRINGS = {
    "de": {
        "app.title": "Trailer Manager",

        "nav.movies": "Filme",
        "nav.settings": "Einstellungen",
        "nav.log": "Protokoll",
        "nav.logout": "Abmelden",

        "login.title": "Anmelden",
        "login.user": "Benutzer",
        "login.password": "Passwort",
        "login.submit": "Anmelden",
        "login.failed": "Benutzername oder Passwort falsch.",
        "login.hint": "Zugangsdaten stammen aus der Einrichtung oder aus den "
                      "Umgebungsvariablen des Containers.",

        "stats.total": "Einträge",
        "stats.with_trailer": "mit Trailer",
        "stats.primary_lang": "in Zielsprache",
        "stats.no_trailer": "ohne Trailer",
        "stats.no_id": "ohne TMDB-ID",
        "stats.errors": "Fehler",

        "action.scan": "Bibliothek einlesen",
        "action.run": "Automatiklauf starten",
        "action.run_force": "Alle neu prüfen",
        "action.stop": "Abbrechen",
        "action.search": "Trailer suchen",
        "action.auto": "Auto",
        "action.auto_hint": "Sucht den besten Trailer und schreibt ihn sofort in "
                            "die NFO.",
        "action.manual": "Suchen",
        "action.manual_hint": "Zeigt alle gefundenen Trailer zur Auswahl.",
        "action.save": "Speichern",
        "action.open_youtube": "Auf YouTube ansehen",
        "action.apply": "Übernehmen",
        "action.remove": "Entfernen",
        "action.test": "Verbindung testen",
        "action.filter": "Filtern",
        "action.reset": "Zurücksetzen",
        "action.change_password": "Passwort ändern",
        "action.edit": "Bearbeiten",

        "table.title": "Titel",
        "table.year": "Jahr",
        "table.tmdb": "TMDB",
        "table.trailer": "Trailer",
        "table.library": "Bibliothek",
        "table.lang": "Sprache",
        "table.lang_unknown": "noch nicht geprüft",
        "table.state": "Status",
        "table.checked": "Geprüft",
        "table.changed": "Trailer gesetzt",
        "table.actions": "Aktionen",
        "table.empty": "Keine Filme gefunden. Zuerst die Bibliothek einlesen.",

        "filter.search": "Suche",
        "filter.only_missing": "nur ohne Trailer",
        "filter.state": "Status",
        "filter.all": "alle",

        "state.ok": "fertig",
        "state.pending": "offen",
        "state.no_trailer": "kein Trailer",
        "state.no_id": "keine ID",
        "state.error": "Fehler",

        "detail.link": "Trailer-Link",
        "detail.link_hint": "plugin://-Link, YouTube-URL oder nur die Video-ID",
        "detail.candidates": "Gefundene Trailer",
        "detail.none": "Keine Trailer gefunden.",
        "detail.official": "offiziell",

        "setup.title": "Einrichtung",
        "setup.intro": "Einmalige Grundeinstellungen. Alles lässt sich später "
                       "unter Einstellungen ändern.",
        "setup.account": "Zugang",
        "setup.account_env": "Benutzername und Passwort kommen aus den "
                             "Umgebungsvariablen des Containers - dieser Schritt "
                             "entfällt.",
        "setup.password_repeat": "Passwort wiederholen",
        "setup.tmdb_hint": "Der v3-API-Key von themoviedb.org, nicht das "
                           "Read-Access-Token. Kostenlos im TMDB-Konto unter "
                           "Einstellungen -> API.",
        "setup.library_hint": "Weitere Ordner - etwa Anime oder Serien - kommen "
                              "später unter Einstellungen dazu.",
        "setup.behaviour": "Verhalten",
        "setup.skip_check": "ohne Prüfung des API-Keys speichern",
        "setup.finish": "Einrichtung abschließen",
        "setup.finished": "Einrichtung abgeschlossen.",
        "setup.err_user": "Bitte einen Benutzernamen eintragen.",
        "setup.err_short": "Das Passwort ist zu kurz (mindestens 8 Zeichen).",
        "setup.err_repeat": "Die beiden Passwörter stimmen nicht überein.",
        "setup.err_key": "Bitte den TMDB-API-Key eintragen.",

        "action.back": "Zurück zur Liste",
        "settings.keep_format_hint": "Steht in einer NFO schon ein Trailer, wird "
                                     "dessen Schreibweise beibehalten - ein "
                                     "plugin://-Link bleibt einer, eine YouTube-URL "
                                     "bleibt eine. Ohne diese Option würde jeder Lauf "
                                     "jede Datei anfassen, nur um die Schreibweise "
                                     "umzustellen.",
        "settings.backup_hint": "Vor der ersten Änderung an einer NFO wird eine Kopie "
                                "als <name>.nfo.bak abgelegt - nur einmal, spätere "
                                "Änderungen überschreiben sie nicht. Braucht "
                                "Schreibrechte im Filmordner.",
        "settings.lockdata_hint": "Trägt zusätzlich <lockdata>true</lockdata> in die "
                                  "NFO ein. Emby behandelt den Eintrag damit als "
                                  "gesperrt und holt seine Metadaten nicht mehr selbst "
                                  "aus dem Internet. Vorsicht: Das gilt für den ganzen "
                                  "Film, nicht nur für den Trailer - Titel, "
                                  "Beschreibung und Bilder werden dann auch nicht mehr "
                                  "aktualisiert.",
        "emby.poll": "Emby nach neuen Filmen fragen (Minuten, 0 = aus)",
        "emby.last_poll": "Zuletzt abgefragt",
        "emby.never": "noch nicht abgefragt",
        "emby.title": "Emby",
        "emby.hint": "Adresse und API-Key gelten für beides: neue Filme abfragen "
                     "und Emby über geschriebene Trailer informieren. Jellyfin "
                     "spricht dieselbe Schnittstelle.",
        "emby.url": "Adresse von Emby oder Jellyfin",
        "emby.api_key": "API-Key",
        "emby.api_key_hint": "In Emby unter Einstellungen -> Erweitert -> "
                             "API-Schlüssel anlegen. Der Schlüssel gilt "
                             "serverweit, also nicht weitergeben.",
        "emby.test": "Emby testen",
        "emby.test_ok": "Verbindung steht",
        "emby.entries_found": "Einträge gefunden",
        "emby.err_missing": "Bitte zuerst Adresse und API-Key eintragen.",
        "notify.title": "Benachrichtigungen",
        "notify.service": "Dienst",
        "notify.off": "aus",
        "notify.url": "Adresse",
        "notify.url_hint": "Bei ntfy gehört das Thema in die Adresse, bei Discord "
                           "ist es die vollständige Webhook-Adresse:",
        "notify.token": "Token",
        "notify.token_hint": "Gotify: das Token einer Anwendung aus dem Reiter "
                             "'Apps' (beginnt mit A) - nicht das eines Clients. "
                             "ntfy: nur bei geschützten Themen. Discord: leer lassen.",
        "notify.on_new": "wenn ein neu hinzugefügter Film einen Trailer bekommt",
        "notify.on_run": "Zusammenfassung nach jedem Automatiklauf",
        "notify.on_error": "bei Fehlern",
        "notify.targets": "Ziele",
        "notify.add": "Ziel hinzufügen",
        "notify.added": "Ziel hinzugefügt.",
        "notify.deleted": "Ziel entfernt.",
        "notify.delete_confirm": "Dieses Ziel entfernen?",
        "notify.none": "Noch kein Ziel eingetragen.",
        "notify.err_url": "Bitte eine Adresse eintragen.",
        "notify.test": "Testen",
        "notify.test_ok": "Benachrichtigung verschickt.",
        "notify.test_title": "Trailer Manager",
        "notify.test_body": "Test - wenn du das liest, funktioniert es.",
        "notify.err_service": "Bitte zuerst einen Dienst auswählen.",
        "settings.title": "Einstellungen",
        "settings.tmdb": "TMDB",
        "settings.api_key": "API-Key (v3)",
        "settings.languages": "Sprachen (Reihenfolge)",
        "settings.languages_hint": "z.B. 'de' für ausschließlich deutsche Trailer, "
                                   "'de,en' mit englischem Rückfall",
        "settings.writing": "Schreiben",
        "settings.link_format": "Linkformat",
        "settings.keep_format": "vorhandenes Format je Film beibehalten",
        "settings.backup": "Sicherungskopie (.bak) anlegen",
        "settings.lockdata": "<lockdata>true</lockdata> ergänzen",
        "settings.overwrite": "auch fertige Filme erneut prüfen",
        "settings.schedule": "Zeitplan",
        "settings.interval": "Intervall (Stunden, 0 = aus)",
        "settings.scan_on_start": "beim Start einmal durchlaufen",
        "settings.recheck": "Filme ohne Treffer erneut prüfen nach (Tagen)",
        "settings.ui": "Oberfläche",
        "settings.ui_language": "Sprache",
        "settings.password": "Passwort",
        "settings.pw_current": "Aktuelles Passwort",
        "settings.pw_new": "Neues Passwort",
        "settings.pw_saved": "Passwort geändert.",
        "settings.pw_wrong": "Das aktuelle Passwort stimmt nicht.",
        "settings.pw_from_env": "Das Passwort kommt aus den Umgebungsvariablen und "
                                "lässt sich hier nicht ändern.",
        "settings.saved": "Einstellungen gespeichert.",


        "settings.yes": "ein",
        "settings.no": "aus",
        "library.title": "Bibliotheken",
        "library.hint": "Jeder Ordner wird getrennt behandelt und kann eigene "
                        "Einstellungen bekommen. Was leer bleibt, übernimmt den "
                        "globalen Wert weiter oben.",
        "library.name": "Name",
        "library.path": "Ordner im Container",
        "library.kind": "Inhalt",
        "library.kind_movie": "Filme",
        "library.kind_tv": "Serien",
        "library.entries": "Einträge",
        "library.enabled": "aktiv",
        "library.disabled": "abgeschaltet",
        "library.add": "Bibliothek hinzufügen",
        "library.added": "Bibliothek angelegt.",
        "library.deleted": "Bibliothek entfernt. Die NFO-Dateien selbst wurden nicht "
                           "angerührt.",
        "library.delete_confirm": "Diese Bibliothek und ihre Einträge aus der "
                                  "Datenbank entfernen? Die Dateien bleiben unberührt.",

        "library.scan": "Nur diese prüfen",
        "library.overrides": "Abweichende Einstellungen",
        "library.inherit": "global übernehmen",
        "library.err_fields": "Name und Ordner dürfen nicht leer sein.",
        "library.err_path": "Diesen Ordner gibt es im Container nicht. Ist er als "
                            "Volume eingehängt?",
        "library.all": "alle Bibliotheken",
        "library.none": "Noch keine Bibliothek angelegt.",
        "library.tv_note": "Bei Serien wird je Serie die tvshow.nfo geschrieben, "
                           "nicht die einzelnen Folgen.",

        "log.title": "Protokoll",
        "log.time": "Zeit",
        "log.level": "Art",
        "log.source": "Quelle",
        "log.message": "Meldung",
        "log.empty": "Noch keine Einträge.",
        "log.runs": "Letzte Durchläufe",
        "run.trigger": "Auslöser",
        "run.scanned": "eingelesen",
        "run.checked": "geprüft",
        "run.updated": "aktualisiert",
        "run.failed": "Fehler",
        "run.duration": "Dauer",

        "status.busy": "Durchlauf läuft",
        "status.idle": "bereit",
        "msg.started": "Durchlauf gestartet.",
        "msg.already": "Es läuft bereits ein Durchgang.",
        "msg.saved": "Gespeichert.",
        "msg.removed": "Trailer entfernt.",
        "msg.invalid_link": "Aus dieser Eingabe lässt sich keine YouTube-ID lesen.",
        "msg.test_ok": "Verbindung und API-Key in Ordnung.",
    },
    "en": {
        "app.title": "Trailer Manager",

        "nav.movies": "Movies",
        "nav.settings": "Settings",
        "nav.log": "Log",
        "nav.logout": "Sign out",

        "login.title": "Sign in",
        "login.user": "Username",
        "login.password": "Password",
        "login.submit": "Sign in",
        "login.failed": "Wrong username or password.",
        "login.hint": "Credentials come from the setup wizard or from the "
                      "container's environment variables.",

        "stats.total": "entries",
        "stats.with_trailer": "with trailer",
        "stats.primary_lang": "in target language",
        "stats.no_trailer": "no trailer",
        "stats.no_id": "no TMDB id",
        "stats.errors": "errors",

        "action.scan": "Scan library",
        "action.run": "Run now",
        "action.run_force": "Recheck all",
        "action.stop": "Stop",
        "action.search": "Search trailers",
        "action.auto": "Auto",
        "action.auto_hint": "Picks the best trailer and writes it into the NFO "
                            "right away.",
        "action.manual": "Search",
        "action.manual_hint": "Shows every trailer that was found, to pick from.",
        "action.save": "Save",
        "action.open_youtube": "Watch on YouTube",
        "action.apply": "Apply",
        "action.remove": "Remove",
        "action.test": "Test connection",
        "action.filter": "Filter",
        "action.reset": "Reset",
        "action.change_password": "Change password",
        "action.edit": "Edit",

        "table.title": "Title",
        "table.year": "Year",
        "table.tmdb": "TMDB",
        "table.trailer": "Trailer",
        "table.library": "Library",
        "table.lang": "Lang",
        "table.lang_unknown": "not checked yet",
        "table.state": "State",
        "table.checked": "Checked",
        "table.changed": "Trailer set",
        "table.actions": "Actions",
        "table.empty": "No movies yet. Scan the library first.",

        "filter.search": "Search",
        "filter.only_missing": "without trailer only",
        "filter.state": "State",
        "filter.all": "all",

        "state.ok": "done",
        "state.pending": "pending",
        "state.no_trailer": "no trailer",
        "state.no_id": "no id",
        "state.error": "error",

        "detail.link": "Trailer link",
        "detail.link_hint": "plugin:// link, YouTube URL or just the video id",
        "detail.candidates": "Available trailers",
        "detail.none": "No trailers found.",
        "detail.official": "official",

        "setup.title": "Setup",
        "setup.intro": "One time basics. Everything can be changed later under "
                       "Settings.",
        "setup.account": "Account",
        "setup.account_env": "Username and password come from the container's "
                             "environment variables - this step is skipped.",
        "setup.password_repeat": "Repeat password",
        "setup.tmdb_hint": "The v3 API key from themoviedb.org, not the read access "
                           "token. Free of charge in your TMDB account under "
                           "Settings -> API.",
        "setup.library_hint": "More folders - anime or TV shows for instance - can "
                              "be added later under Settings.",
        "setup.behaviour": "Behaviour",
        "setup.skip_check": "save without checking the API key",
        "setup.finish": "Finish setup",
        "setup.finished": "Setup complete.",
        "setup.err_user": "Please enter a username.",
        "setup.err_short": "The password is too short (at least 8 characters).",
        "setup.err_repeat": "The two passwords do not match.",
        "setup.err_key": "Please enter the TMDB API key.",

        "action.back": "Back to the list",
        "settings.keep_format_hint": "When an NFO already holds a trailer, its "
                                     "notation is kept - a plugin:// link stays one, "
                                     "a YouTube URL stays one. Without this every run "
                                     "would touch every file just to change the "
                                     "notation.",
        "settings.backup_hint": "Before the first change to an NFO a copy is saved as "
                                "<name>.nfo.bak - once only, later changes do not "
                                "overwrite it. Needs write access in the movie folder.",
        "settings.lockdata_hint": "Also writes <lockdata>true</lockdata> into the NFO. "
                                  "Emby then treats the entry as locked and stops "
                                  "fetching metadata for it. Careful: that covers the "
                                  "whole item, not just the trailer - title, plot and "
                                  "artwork stop being updated as well.",
        "emby.poll": "Ask Emby for new items every (minutes, 0 = off)",
        "emby.last_poll": "Last asked",
        "emby.never": "not asked yet",
        "emby.title": "Emby",
        "emby.hint": "The address and API key cover both jobs: asking for new "
                     "items and telling Emby about written trailers. Jellyfin "
                     "speaks the same interface.",
        "emby.url": "Address of Emby or Jellyfin",
        "emby.api_key": "API key",
        "emby.api_key_hint": "Create one in Emby under Settings -> Advanced -> "
                             "API keys. It is valid server wide, so keep it to "
                             "yourself.",
        "emby.test": "Test Emby",
        "emby.test_ok": "Connection works",
        "emby.entries_found": "entries found",
        "emby.err_missing": "Please enter an address and an API key first.",
        "notify.title": "Notifications",
        "notify.service": "Service",
        "notify.off": "off",
        "notify.url": "Address",
        "notify.url_hint": "For ntfy the topic belongs in the address, for Discord it "
                           "is the full webhook address:",
        "notify.token": "Token",
        "notify.token_hint": "Gotify: an application token from the 'Apps' tab "
                             "(starts with A) - not a client token. ntfy: only for "
                             "protected topics. Discord: leave empty.",
        "notify.on_new": "when a newly added item gets its trailer",
        "notify.on_run": "summary after every automatic run",
        "notify.on_error": "on errors",
        "notify.targets": "Targets",
        "notify.add": "Add target",
        "notify.added": "Target added.",
        "notify.deleted": "Target removed.",
        "notify.delete_confirm": "Remove this target?",
        "notify.none": "No target configured yet.",
        "notify.err_url": "Please enter an address.",
        "notify.test": "Test",
        "notify.test_ok": "Notification sent.",
        "notify.test_title": "Trailer Manager",
        "notify.test_body": "Test - if you can read this, it works.",
        "notify.err_service": "Please pick a service first.",
        "settings.title": "Settings",
        "settings.tmdb": "TMDB",
        "settings.api_key": "API key (v3)",
        "settings.languages": "Languages (in order)",
        "settings.languages_hint": "e.g. 'de' for German only, 'de,en' to fall back "
                                   "to English",
        "settings.writing": "Writing",
        "settings.link_format": "Link format",
        "settings.keep_format": "keep the format already used per movie",
        "settings.backup": "create backup copy (.bak)",
        "settings.lockdata": "add <lockdata>true</lockdata>",
        "settings.overwrite": "recheck movies that are already done",
        "settings.schedule": "Schedule",
        "settings.interval": "Interval (hours, 0 = off)",
        "settings.scan_on_start": "run once on startup",
        "settings.recheck": "recheck movies without a hit after (days)",
        "settings.ui": "Interface",
        "settings.ui_language": "Language",
        "settings.password": "Password",
        "settings.pw_current": "Current password",
        "settings.pw_new": "New password",
        "settings.pw_saved": "Password changed.",
        "settings.pw_wrong": "The current password is not correct.",
        "settings.pw_from_env": "The password comes from the environment and cannot "
                                "be changed here.",
        "settings.saved": "Settings saved.",


        "settings.yes": "on",
        "settings.no": "off",
        "library.title": "Libraries",
        "library.hint": "Every folder is handled separately and can carry its own "
                        "settings. Anything left empty keeps the global value from "
                        "above.",
        "library.name": "Name",
        "library.path": "Folder inside the container",
        "library.kind": "Content",
        "library.kind_movie": "Movies",
        "library.kind_tv": "TV shows",
        "library.entries": "entries",
        "library.enabled": "enabled",
        "library.disabled": "disabled",
        "library.add": "Add library",
        "library.added": "Library created.",
        "library.deleted": "Library removed. The NFO files themselves were not touched.",
        "library.delete_confirm": "Remove this library and its entries from the "
                                  "database? The files stay untouched.",

        "library.scan": "Check this one only",
        "library.overrides": "Settings that differ",
        "library.inherit": "use the global value",
        "library.err_fields": "Name and folder must not be empty.",
        "library.err_path": "That folder does not exist inside the container. Is it "
                            "mounted as a volume?",
        "library.all": "all libraries",
        "library.none": "No library configured yet.",
        "library.tv_note": "For TV shows the tvshow.nfo of each series is written, "
                           "not the individual episodes.",

        "log.title": "Log",
        "log.time": "Time",
        "log.level": "Level",
        "log.source": "Source",
        "log.message": "Message",
        "log.empty": "Nothing logged yet.",
        "log.runs": "Recent runs",
        "run.trigger": "Trigger",
        "run.scanned": "scanned",
        "run.checked": "checked",
        "run.updated": "updated",
        "run.failed": "failed",
        "run.duration": "duration",

        "status.busy": "run in progress",
        "status.idle": "idle",
        "msg.started": "Run started.",
        "msg.already": "A run is already in progress.",
        "msg.saved": "Saved.",
        "msg.removed": "Trailer removed.",
        "msg.invalid_link": "No YouTube video id could be read from that input.",
        "msg.test_ok": "Connection and API key are fine.",
    },
}


def translate(lang, key):
    table = STRINGS.get(lang) or STRINGS["de"]
    return table.get(key) or STRINGS["de"].get(key) or key
