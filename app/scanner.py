"""Einlesen der Bibliothek, Automatiklauf, Zeitplan und Webhook-Verarbeitung."""

import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import db
import nfo
import tmdb


class Scanner:
    def __init__(self, movies_dir, settings_getter):
        self.movies_dir = Path(movies_dir)
        self.get = settings_getter          # callable(key, default) -> str
        self.lock = threading.Lock()
        self.busy = False
        self.state = {"phase": "idle", "done": 0, "total": 0, "current": "",
                      "started": None, "trigger": None}
        self._stop = threading.Event()
        self._scheduler = None

    # ------------------------------------------------------------- Hilfsmittel
    def _langs(self):
        raw = self.get("languages", "de")
        return [l.strip() for l in raw.split(",") if l.strip()] or ["de"]

    def _flag(self, key, default="0"):
        return str(self.get(key, default)) in ("1", "true", "True", "on", "yes")

    def _api_key(self):
        return (self.get("tmdb_api_key", "") or "").strip()

    def stop(self):
        self._stop.set()

    def _claim(self):
        """Belegt-Kennzeichen setzen. False, wenn schon etwas laeuft.

        Pruefen und Setzen muessen unter demselben Schloss passieren, sonst
        starten zwei gleichzeitige Klicks zwei Durchgaenge.
        """
        with self.lock:
            if self.busy:
                return False
            self.busy = True
            return True

    def _release(self):
        with self.lock:
            self.busy = False

    # ---------------------------------------------------------------- Einlesen
    def scan_async(self):
        """Einlesen im Hintergrund anstossen. False, wenn schon etwas laeuft."""
        if not self._claim():
            return False
        self._stop.clear()

        def job():
            try:
                self.scan_library()
            except Exception as e:                         # noqa: BLE001
                db.log("error", "Einlesen fehlgeschlagen: {}".format(e), "scan")
            finally:
                self.state.update(phase="idle", current="")
                self._release()

        threading.Thread(target=job, daemon=True).start()
        return True

    def scan_library(self, workers=12):
        """NFOs einlesen und in der Datenbank abgleichen. Nur geaenderte Dateien
        werden neu geparst - Mtime und Groesse stehen ja schon in der DB."""
        started = time.time()
        self.state.update(phase="scan", done=0, total=0, current="")
        files = nfo.walk_nfo_files(self.movies_dir, self._stop)
        self.state["total"] = len(files)
        known = db.known_files()
        present = set()
        todo = []
        for path, mtime, size in files:
            present.add(path)
            old = known.get(path)
            if old and abs((old[0] or 0) - mtime) < 1 and (old[1] or 0) == size:
                self.state["done"] += 1
                continue
            todo.append((path, mtime, size))

        added = 0
        if todo:
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = {pool.submit(nfo.parse_nfo, p): (p, m, s) for p, m, s in todo}
                for fut in as_completed(futures):
                    if self._stop.is_set():
                        break
                    path, mtime, size = futures[fut]
                    try:
                        data = fut.result()
                    except Exception:                          # noqa: BLE001
                        data = None
                    if data:
                        db.upsert_movie(path, str(Path(path).parent), data, mtime, size)
                        added += 1
                    self.state["done"] += 1
                    self.state["current"] = Path(path).parent.name

        gone = db.delete_missing(present)
        db.log("info", "Bibliothek eingelesen: {} NFOs, {} neu/geaendert, {} entfernt, {:.1f}s"
               .format(len(files), added, len(gone), time.time() - started), "scan")
        return {"files": len(files), "changed": added, "removed": len(gone)}

    # ----------------------------------------------------------- Einzelner Film
    def process_movie(self, row, force=False):
        """Einen Film bei TMDB nachschlagen und die NFO schreiben.
        Gibt (status, meldung) zurueck."""
        api_key = self._api_key()
        langs = self._langs()
        path = row["path"]

        tmdb_id = row["tmdb_id"]
        try:
            if not tmdb_id and row["imdb_id"]:
                tmdb_id = tmdb.lookup_by_imdb(row["imdb_id"], api_key)
            if not tmdb_id:
                db.mark_result(path, "no_id", "Keine TMDB-/IMDb-ID in der NFO")
                return "no_id", "Keine TMDB-/IMDb-ID in der NFO"

            videos = tmdb.fetch_videos(tmdb_id, api_key, langs)
            best = tmdb.pick_best(videos, langs)
        except tmdb.TmdbError as e:
            db.mark_result(path, "error", str(e))
            db.log("error", "{}: {}".format(row["title"], e), "tmdb")
            return "error", str(e)

        if not best:
            db.mark_result(path, "no_trailer",
                           "Kein Trailer in {}".format(", ".join(langs)))
            return "no_trailer", "Kein Trailer in {}".format(", ".join(langs))

        fmt = self.get("link_format", "emby")
        if self._flag("keep_format", "1") and row["trailer"]:
            fmt = nfo.detect_format(row["trailer"]) or fmt
        value = nfo.format_link(best["key"], fmt)

        if value == (row["trailer"] or "") and not force:
            db.mark_result(path, "ok", "Bereits aktuell", trailer=value,
                           trailer_lang=best.get("lang"), written=True)
            return "ok", "Bereits aktuell"

        try:
            nfo.write_trailer(Path(path), value,
                              lockdata=self._flag("lockdata"),
                              backup=self._flag("backup", "1"))
        except (nfo.WriteError, OSError) as e:
            msg = str(e).splitlines()[0]
            db.mark_result(path, "error", msg)
            db.log("error", "{}: {}".format(row["title"], msg), "write")
            return "error", msg

        db.mark_result(path, "ok", "Trailer [{}] {}".format(best.get("lang"), best["key"]),
                       trailer=value, trailer_lang=best.get("lang"), written=True)
        db.log("ok", "{}: Trailer [{}] {} eingetragen".format(
            row["title"], best.get("lang"), best["key"]), "auto")
        return "ok", best["key"]

    def candidates_for(self, row):
        """Alle Trailer eines Films - fuer die manuelle Auswahl in der Oberflaeche."""
        api_key = self._api_key()
        tmdb_id = row["tmdb_id"]
        if not tmdb_id and row["imdb_id"]:
            tmdb_id = tmdb.lookup_by_imdb(row["imdb_id"], api_key)
        if not tmdb_id:
            return []
        return tmdb.sort_candidates(tmdb.fetch_videos(tmdb_id, api_key, self._langs()),
                                    self._langs())

    # --------------------------------------------------------- Automatiklauf
    def run(self, trigger="manual", only_paths=None, force=False):
        """Vollstaendiger Lauf: einlesen, dann offene Filme abarbeiten."""
        if not self._claim():
            return {"skipped": True, "reason": "Es laeuft bereits ein Durchgang"}
        self._stop.clear()
        run_id = db.start_run(trigger)
        self.state.update(started=time.time(), trigger=trigger)
        scanned = checked = updated = failed = 0
        try:
            if only_paths is None:
                info = self.scan_library()
                scanned = info["files"]
                recheck = int(self.get("recheck_days", "30") or 30) * 86400
                rows = db.pending_movies(recheck, self._flag("overwrite_existing"))
            else:
                rows = [db.get_movie(p) for p in only_paths]
                rows = [r for r in rows if r]

            self.state.update(phase="check", done=0, total=len(rows), current="")
            db.log("info", "Automatiklauf ({}): {} Filme zu pruefen".format(trigger, len(rows)),
                   "auto")

            for row in rows:
                if self._stop.is_set():
                    db.log("warn", "Automatiklauf abgebrochen", "auto")
                    break
                self.state["current"] = row["title"] or row["folder"]
                status, _msg = self.process_movie(row, force=force)
                checked += 1
                if status == "ok":
                    updated += 1
                elif status == "error":
                    failed += 1
                self.state["done"] = checked
                time.sleep(0.05)                # TMDB schonen
        finally:
            db.finish_run(run_id, scanned, checked, updated, failed)
            self.state.update(phase="idle", current="")
            self._release()
        result = {"scanned": scanned, "checked": checked, "updated": updated, "failed": failed}
        db.log("info", "Automatiklauf beendet: {}".format(result), "auto")
        return result

    def run_async(self, **kwargs):
        """Lauf im Hintergrund starten. Der Belegt-Schutz sitzt in run() selbst,
        deshalb ist der Blick auf busy hier nur eine schnelle Vorpruefung."""
        if self.busy:
            return False
        threading.Thread(target=self.run, kwargs=kwargs, daemon=True).start()
        return True

    # ------------------------------------------------------------- Webhook
    def handle_event(self, payload):
        """Meldung von Emby/Jellyfin/Jellyseerr verarbeiten.

        Gesucht wird zuerst der Dateipfad, sonst die TMDB-ID. Ist der Film noch
        nicht in der Datenbank, wird sein Ordner gezielt nachgelesen.
        """
        path = _dig(payload, ["Item", "Path"]) or _dig(payload, ["Path"]) \
            or _dig(payload, ["media", "path"])
        tmdb_id = (_dig(payload, ["Item", "ProviderIds", "Tmdb"])
                   or _dig(payload, ["Item", "ProviderIds", "tmdb"])
                   or _dig(payload, ["ProviderIds", "Tmdb"])
                   or _dig(payload, ["media", "tmdbId"])
                   or _dig(payload, ["tmdbId"]))
        title = (_dig(payload, ["Item", "Name"]) or _dig(payload, ["Name"])
                 or _dig(payload, ["subject"]) or "?")

        rows = []
        if path:
            folder = str(Path(path).parent)
            rows = db.find_by_folder(folder)
            if not rows:
                # Ordner gezielt einlesen (Film ist ganz neu)
                for nfo_path, mtime, size in nfo.walk_nfo_files(folder):
                    data = nfo.parse_nfo(nfo_path)
                    if data:
                        db.upsert_movie(nfo_path, folder, data, mtime, size)
                rows = db.find_by_folder(folder)
        if not rows and tmdb_id:
            rows = db.find_by_tmdb(tmdb_id)
        if not rows and tmdb_id:
            # Film liegt noch nicht in der DB: kurzer Gesamtscan
            db.log("info", "Webhook: {} unbekannt, lese Bibliothek nach".format(title), "webhook")
            self.scan_library()
            rows = db.find_by_tmdb(tmdb_id)

        if not rows:
            db.log("warn", "Webhook: kein passender Film gefunden ({})".format(title), "webhook")
            return {"matched": 0, "title": title}

        results = []
        for row in rows:
            status, msg = self.process_movie(row)
            results.append({"title": row["title"], "status": status, "message": msg})
        db.log("info", "Webhook: {} -> {}".format(title, results[0]["status"]), "webhook")
        return {"matched": len(rows), "title": title, "results": results}

    # ------------------------------------------------------------- Zeitplan
    def start_scheduler(self):
        if self._scheduler and self._scheduler.is_alive():
            return

        def loop():
            if self._flag("scan_on_start", "1"):
                time.sleep(5)
                try:
                    self.run(trigger="start")
                except Exception as e:                         # noqa: BLE001
                    db.log("error", "Startlauf fehlgeschlagen: {}".format(e), "schedule")
            while True:
                try:
                    hours = float(self.get("scan_interval_hours", "12") or 12)
                except (TypeError, ValueError):
                    hours = 12
                if hours <= 0:
                    time.sleep(300)             # Zeitplan aus
                    continue
                time.sleep(hours * 3600)
                try:
                    self.run(trigger="schedule")
                except Exception as e:                         # noqa: BLE001
                    db.log("error", "Geplanter Lauf fehlgeschlagen: {}".format(e), "schedule")

        self._scheduler = threading.Thread(target=loop, daemon=True)
        self._scheduler.start()


def _dig(data, keys):
    """Verschachtelten Wert holen, ohne bei fehlenden Schluesseln zu stolpern."""
    cur = data
    for key in keys:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
        if cur is None:
            return None
    return cur
