"""Bilingual interface (German / English).

Switch in the header; the choice lives in the session, the default comes from
the settings or from UI_LANGUAGE.
"""

LANGUAGES = {"de": "Deutsch", "en": "English"}

STRINGS = {
    "de": {
        "app.title": "Trailer Manager",
        "app.subtitle": "Trailer fuer Emby, direkt in die NFO-Dateien",

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

        "stats.total": "Filme",
        "stats.with_trailer": "mit Trailer",
        "stats.primary_lang": "in Zielsprache",
        "stats.no_trailer": "ohne Trailer",
        "stats.no_id": "ohne TMDB-ID",
        "stats.errors": "Fehler",

        "action.scan": "Bibliothek einlesen",
        "action.run": "Automatiklauf starten",
        "action.run_force": "Alle neu pruefen",
        "action.stop": "Abbrechen",
        "action.search": "Trailer suchen",
        "action.save": "Speichern",
        "action.open_youtube": "Auf YouTube ansehen",
        "action.diag": "Schreibrechte pruefen",
        "action.apply": "Uebernehmen",
        "action.remove": "Entfernen",
        "action.test": "Verbindung testen",
        "action.filter": "Filtern",
        "action.reset": "Zuruecksetzen",
        "action.change_password": "Passwort aendern",

        "table.title": "Titel",
        "table.year": "Jahr",
        "table.tmdb": "TMDB",
        "table.trailer": "Trailer",
        "table.lang": "Sprache",
        "table.lang_unknown": "noch nicht geprueft",
        "table.state": "Status",
        "table.checked": "Geprueft",
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
        "setup.intro": "Einmalige Grundeinstellungen. Alles laesst sich spaeter "
                       "unter Einstellungen aendern.",
        "setup.account": "Zugang",
        "setup.account_env": "Benutzername und Passwort kommen aus den "
                             "Umgebungsvariablen des Containers - dieser Schritt "
                             "entfaellt.",
        "setup.password_repeat": "Passwort wiederholen",
        "setup.tmdb_hint": "Der v3-API-Key von themoviedb.org, nicht das "
                           "Read-Access-Token. Kostenlos im TMDB-Konto unter "
                           "Einstellungen -> API.",
        "setup.library_hint": "Weitere Ordner - etwa Anime oder Serien - kommen "
                              "spaeter unter Einstellungen dazu.",
        "setup.behaviour": "Verhalten",
        "setup.skip_check": "ohne Pruefung des API-Keys speichern",
        "setup.finish": "Einrichtung abschliessen",
        "setup.finished": "Einrichtung abgeschlossen. Die Webhook-Adresse steht "
                          "weiter unten.",
        "setup.err_user": "Bitte einen Benutzernamen eintragen.",
        "setup.err_short": "Das Passwort ist zu kurz (mindestens 8 Zeichen).",
        "setup.err_repeat": "Die beiden Passwoerter stimmen nicht ueberein.",
        "setup.err_key": "Bitte den TMDB-API-Key eintragen.",

        "settings.title": "Einstellungen",
        "settings.tmdb": "TMDB",
        "settings.api_key": "API-Key (v3)",
        "settings.languages": "Sprachen (Reihenfolge)",
        "settings.languages_hint": "z.B. 'de' fuer ausschliesslich deutsche Trailer, "
                                   "'de,en' mit englischem Rueckfall",
        "settings.writing": "Schreiben",
        "settings.link_format": "Linkformat",
        "settings.keep_format": "vorhandenes Format je Film beibehalten",
        "settings.backup": "Sicherungskopie (.bak) anlegen",
        "settings.lockdata": "<lockdata>true</lockdata> ergaenzen",
        "settings.overwrite": "auch fertige Filme erneut pruefen",
        "settings.schedule": "Zeitplan",
        "settings.interval": "Intervall (Stunden, 0 = aus)",
        "settings.scan_on_start": "beim Start einmal durchlaufen",
        "settings.recheck": "Filme ohne Treffer erneut pruefen nach (Tagen)",
        "settings.ui": "Oberflaeche",
        "settings.ui_language": "Sprache",
        "settings.password": "Passwort",
        "settings.pw_current": "Aktuelles Passwort",
        "settings.pw_new": "Neues Passwort",
        "settings.pw_saved": "Passwort geaendert.",
        "settings.pw_wrong": "Das aktuelle Passwort stimmt nicht.",
        "settings.pw_from_env": "Das Passwort kommt aus den Umgebungsvariablen und "
                                "laesst sich hier nicht aendern.",
        "settings.saved": "Einstellungen gespeichert.",

        "settings.webhook": "Webhook",
        "webhook.hint": "Diese Adresse traegst du in Emby, Jellyfin oder Jellyseerr "
                        "ein. Jeder neu hinzugefuegte Film bekommt seinen Trailer "
                        "dann sofort, ohne auf den naechsten Automatiklauf zu warten.",
        "webhook.emby": "In Emby einrichten",
        "webhook.emby_where": "Einstellungen -> Benachrichtigungen -> Webhooks -> "
                              "Hinzufuegen",
        "webhook.emby_event": "Ereignis: nur 'Neue Medien hinzugefuegt' "
                              "(Library - New media added)",
        "webhook.emby_type": "Inhaltstyp: application/json",
        "webhook.emby_limit": "Bibliotheksereignisse beschraenken auf: Filme",
        "webhook.emby_note": "multipart/form-data wird ebenfalls verstanden, JSON ist "
                             "aber eindeutiger. Die Bezeichnungen unterscheiden sich "
                             "je nach Emby-Version leicht.",
        "webhook.jellyfin": "In Jellyfin einrichten",
        "webhook.jellyfin_where": "Dashboard -> Plugins -> Webhook -> Add Generic "
                                  "Destination, Notification Type 'Item Added', "
                                  "Item Type 'Movies'",
        "webhook.jellyseerr": "In Jellyseerr einrichten",
        "webhook.jellyseerr_where": "Settings -> Notifications -> Webhook, Ausloeser "
                                    "'Media Available'",
        "webhook.token_note": "Das Token steckt in der Adresse. Wer sie kennt, kann "
                              "Durchlaeufe ausloesen - also nicht oeffentlich teilen.",

        "settings.yes": "ein",
        "settings.no": "aus",
        "library.title": "Bibliotheken",
        "library.hint": "Jeder Ordner wird getrennt behandelt und kann eigene "
                        "Einstellungen bekommen. Was leer bleibt, uebernimmt den "
                        "globalen Wert weiter oben.",
        "library.name": "Name",
        "library.path": "Ordner im Container",
        "library.kind": "Inhalt",
        "library.kind_movie": "Filme",
        "library.kind_tv": "Serien",
        "library.entries": "Eintraege",
        "library.enabled": "aktiv",
        "library.add": "Bibliothek hinzufuegen",
        "library.added": "Bibliothek angelegt.",
        "library.deleted": "Bibliothek entfernt. Die NFO-Dateien selbst wurden nicht "
                           "angeruehrt.",
        "library.delete_confirm": "Diese Bibliothek und ihre Eintraege aus der "
                                  "Datenbank entfernen? Die Dateien bleiben unberuehrt.",
        "library.edit": "Bearbeiten",
        "library.scan": "Nur diese pruefen",
        "library.overrides": "Abweichende Einstellungen",
        "library.inherit": "global uebernehmen",
        "library.err_fields": "Name und Ordner duerfen nicht leer sein.",
        "library.err_path": "Diesen Ordner gibt es im Container nicht. Ist er als "
                            "Volume eingehaengt?",
        "library.all": "alle Bibliotheken",
        "library.none": "Noch keine Bibliothek angelegt.",
        "library.tv_note": "Bei Serien wird je Serie die tvshow.nfo geschrieben, "
                           "nicht die einzelnen Folgen.",
        "webhook.last": "Zuletzt empfangen",
        "webhook.never": "noch nichts empfangen",
        "webhook.test_hint": "Emby hat bei den Webhooks einen Knopf zum Testen. "
                             "Danach steht der Empfang hier und im Protokoll - "
                             "ein Testereignis loest bewusst keinen Durchlauf aus.",

        "log.title": "Protokoll",
        "log.time": "Zeit",
        "log.level": "Art",
        "log.source": "Quelle",
        "log.message": "Meldung",
        "log.empty": "Noch keine Eintraege.",
        "log.runs": "Letzte Durchlaeufe",
        "run.trigger": "Ausloeser",
        "run.scanned": "eingelesen",
        "run.checked": "geprueft",
        "run.updated": "aktualisiert",
        "run.failed": "Fehler",
        "run.duration": "Dauer",

        "status.busy": "Durchlauf laeuft",
        "status.idle": "bereit",
        "msg.started": "Durchlauf gestartet.",
        "msg.already": "Es laeuft bereits ein Durchgang.",
        "msg.saved": "Gespeichert.",
        "msg.removed": "Trailer entfernt.",
        "msg.invalid_link": "Aus dieser Eingabe laesst sich keine YouTube-ID lesen.",
        "msg.test_ok": "Verbindung und API-Key in Ordnung.",
    },
    "en": {
        "app.title": "Trailer Manager",
        "app.subtitle": "Trailers for Emby, straight into your NFO files",

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

        "stats.total": "movies",
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
        "action.save": "Save",
        "action.open_youtube": "Watch on YouTube",
        "action.diag": "Check write access",
        "action.apply": "Apply",
        "action.remove": "Remove",
        "action.test": "Test connection",
        "action.filter": "Filter",
        "action.reset": "Reset",
        "action.change_password": "Change password",

        "table.title": "Title",
        "table.year": "Year",
        "table.tmdb": "TMDB",
        "table.trailer": "Trailer",
        "table.lang": "Lang",
        "table.lang_unknown": "not checked yet",
        "table.state": "State",
        "table.checked": "Checked",
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
        "setup.finished": "Setup complete. The webhook address is further down.",
        "setup.err_user": "Please enter a username.",
        "setup.err_short": "The password is too short (at least 8 characters).",
        "setup.err_repeat": "The two passwords do not match.",
        "setup.err_key": "Please enter the TMDB API key.",

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

        "settings.webhook": "Webhook",
        "webhook.hint": "Enter this address in Emby, Jellyfin or Jellyseerr. Every "
                        "newly added movie then gets its trailer right away, without "
                        "waiting for the next scheduled run.",
        "webhook.emby": "Set up in Emby",
        "webhook.emby_where": "Settings -> Notifications -> Webhooks -> Add",
        "webhook.emby_event": "Event: only 'New media added' (Library)",
        "webhook.emby_type": "Request content type: application/json",
        "webhook.emby_limit": "Limit library events to: Movies",
        "webhook.emby_note": "multipart/form-data is understood as well, but JSON is "
                             "less ambiguous. Labels differ slightly between Emby "
                             "versions.",
        "webhook.jellyfin": "Set up in Jellyfin",
        "webhook.jellyfin_where": "Dashboard -> Plugins -> Webhook -> Add Generic "
                                  "Destination, notification type 'Item Added', "
                                  "item type 'Movies'",
        "webhook.jellyseerr": "Set up in Jellyseerr",
        "webhook.jellyseerr_where": "Settings -> Notifications -> Webhook, trigger "
                                    "'Media Available'",
        "webhook.token_note": "The token is part of the address. Anyone who knows it "
                              "can trigger runs, so do not share it publicly.",

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
        "library.add": "Add library",
        "library.added": "Library created.",
        "library.deleted": "Library removed. The NFO files themselves were not touched.",
        "library.delete_confirm": "Remove this library and its entries from the "
                                  "database? The files stay untouched.",
        "library.edit": "Edit",
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
        "webhook.last": "Last received",
        "webhook.never": "nothing received yet",
        "webhook.test_hint": "Emby has a test button on its webhook settings. After "
                             "pressing it the arrival shows up here and in the log - "
                             "a test event deliberately does not start a run.",

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
