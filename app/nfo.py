"""NFO-Dateien lesen und schreiben (Emby-/Kodi-Format)."""

import os
import re
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

# Emby/Kodi kennen zwei plugin://-Schreibweisen; Emby selbst schreibt die erste.
LINK_FORMATS = {
    "emby": ("Emby-Format  plugin://.../play/?video_id=",
             "plugin://plugin.video.youtube/play/?video_id={}"),
    "kodi": ("Kodi-Altformat  plugin://...?action=play_video&videoid=",
             "plugin://plugin.video.youtube/?action=play_video&videoid={}"),
    "url": ("YouTube-URL  https://www.youtube.com/watch?v=",
            "https://www.youtube.com/watch?v={}"),
}
FORMAT_LABELS = {label: keyname for keyname, (label, _fmt) in LINK_FORMATS.items()}
DEFAULT_FORMAT = "emby"
YT_URL_FMT = "https://www.youtube.com/watch?v={}"
YT_ID_RE = re.compile(r"[A-Za-z0-9_-]{11}")


def read_ids(root):
    tmdb_id = (root.findtext("tmdbid") or "").strip()
    imdb_id = (root.findtext("imdbid") or "").strip()

    for uid in root.findall("uniqueid"):
        utype = (uid.get("type") or "").lower()
        val = (uid.text or "").strip()
        if not val:
            continue
        if utype in ("tmdb", "themoviedb") and not tmdb_id:
            tmdb_id = val
        elif utype == "imdb" and not imdb_id:
            imdb_id = val

    ident = (root.findtext("id") or "").strip()
    if ident.startswith("tt") and not imdb_id:
        imdb_id = ident
    elif ident.isdigit() and not tmdb_id:
        tmdb_id = ident

    return tmdb_id or None, imdb_id or None


def _append_indented(root, tag, value):
    children = list(root)
    indent = "\n"
    for child in children:
        if child.tail and "\n" in child.tail:
            indent = child.tail
            break
    prev_tail = children[-1].tail if children else None
    node = ET.SubElement(root, tag)
    node.text = value
    node.tail = prev_tail if prev_tail else "\n"
    if children:
        children[-1].tail = indent


def set_trailer(root, value):
    node = root.find("trailer")
    if value:
        if node is not None:
            if (node.text or "").strip() == value:
                return False
            node.text = value
            return True
        _append_indented(root, "trailer", value)
        return True
    changed = False
    for node in root.findall("trailer"):
        children = list(root)
        pos = children.index(node)
        root.remove(node)
        if pos > 0:                       # Einrueckung des Vorgaengers uebernehmen
            children[pos - 1].tail = node.tail
        changed = True
    return changed


def ensure_lockdata(root):
    if root.find("lockdata") is None:
        _append_indented(root, "lockdata", "true")
        return True
    return False


class WriteError(RuntimeError):
    """Schreibfehler mit Klartext-Ursache."""


def check_write_access(nfo_path):
    """Prueft Schreibrechte auf NFO und Ordner. Gibt Liste von Klartextzeilen."""
    lines = []
    nfo = Path(nfo_path)
    folder = nfo.parent
    lines.append("Datei:  {}".format(nfo))
    lines.append("Ordner: {}".format(folder))

    try:
        st = nfo.stat()
        lines.append("Rechte der NFO: {:o}, Besitzer-UID {}, Gruppen-GID {}".format(
            st.st_mode & 0o777, st.st_uid, st.st_gid))
    except OSError as e:
        lines.append("NFO nicht lesbar: {}".format(e))
        return lines

    lines.append("NFO beschreibbar:   {}".format("ja" if os.access(nfo, os.W_OK) else "NEIN"))
    lines.append("Ordner beschreibbar: {}".format("ja" if os.access(folder, os.W_OK) else "NEIN"))

    probe = folder / ".tmdb-trailer-schreibtest"
    try:
        probe.write_text("test", encoding="utf-8")
        probe.unlink()
        lines.append("Praktischer Schreibtest im Ordner: erfolgreich")
    except OSError as e:
        lines.append("Praktischer Schreibtest im Ordner: FEHLGESCHLAGEN ({})".format(e))

    return lines


def _perm_hint(path):
    return ("Moegliche Ursachen:\n"
            "  - Die SMB-Freigabe ist nur lesend eingebunden (als Gast verbunden oder in\n"
            "    Unraid unter Shares -> SMB Security auf 'Read-only').\n"
            "  - Die Datei gehoert einem anderen Benutzer (z.B. von Emby oder einem\n"
            "    Docker-Container geschrieben). In Unraid hilft Tools -> New Permissions.\n"
            "  - Der Ordner selbst ist nicht beschreibbar - dann scheitert schon die\n"
            "    Sicherungskopie. Zum Test die Option 'Sicherung (.bak)' abschalten.\n\n"
            "Betroffen: {}".format(path))


def write_trailer(nfo_path, value, lockdata=False, backup=True):
    """Trailer-Link in eine NFO schreiben. Gibt True zurueck, wenn geaendert."""
    nfo_path = Path(nfo_path)
    tree = ET.parse(nfo_path)
    root = tree.getroot()
    changed = set_trailer(root, value)
    if lockdata and value:
        changed = ensure_lockdata(root) or changed
    if not changed:
        return False

    if backup:
        bak = nfo_path.with_suffix(nfo_path.suffix + ".bak")
        if not bak.exists():
            try:
                bak.write_bytes(nfo_path.read_bytes())
            except PermissionError as e:
                raise WriteError(
                    "Die Sicherungskopie laesst sich nicht anlegen - der ORDNER ist "
                    "nicht beschreibbar.\n\n" + _perm_hint(bak)) from e
            except OSError as e:
                raise WriteError("Sicherungskopie fehlgeschlagen: {}".format(e)) from e

    _write_atomic(tree, nfo_path)
    return True


def _write_atomic(tree, nfo_path):
    """Erst in eine Nachbardatei schreiben, dann umbenennen.

    Bricht das Schreiben ab - volle Platte, gekappte SMB-Verbindung -, bleibt so
    die alte NFO unversehrt, statt halb geschrieben zurueckzubleiben. Klappt das
    Anlegen der Zwischendatei nicht (Ordner nur lesbar, Datei aber beschreibbar),
    wird direkt geschrieben.
    """
    folder = nfo_path.parent
    try:
        mode = nfo_path.stat().st_mode & 0o777
    except OSError:
        mode = 0o644

    tmp_path = None
    try:
        fd, tmp_name = tempfile.mkstemp(prefix=nfo_path.name + ".", suffix=".tmp",
                                        dir=str(folder))
        os.close(fd)
        tmp_path = Path(tmp_name)
    except OSError:
        tmp_path = None

    if tmp_path is None:
        try:
            tree.write(nfo_path, encoding="utf-8", xml_declaration=True)
            return
        except PermissionError as e:
            raise WriteError("Die NFO-Datei ist schreibgeschuetzt.\n\n"
                             + _perm_hint(nfo_path)) from e
        except OSError as e:
            raise WriteError("Schreiben fehlgeschlagen: {}".format(e)) from e

    try:
        tree.write(tmp_path, encoding="utf-8", xml_declaration=True)
        os.chmod(tmp_path, mode)
        _copy_owner(nfo_path, tmp_path)
        os.replace(tmp_path, nfo_path)
    except PermissionError as e:
        _unlink_quiet(tmp_path)
        raise WriteError("Die NFO-Datei ist schreibgeschuetzt.\n\n"
                         + _perm_hint(nfo_path)) from e
    except OSError as e:
        _unlink_quiet(tmp_path)
        raise WriteError("Schreiben fehlgeschlagen: {}".format(e)) from e


def _copy_owner(src, dst):
    """Besitzer uebernehmen, damit Emby die NFO weiter anfassen kann.

    Nur moeglich, wenn der Prozess die Rechte dazu hat - sonst still uebergehen.
    """
    try:
        st = os.stat(src)
        os.chown(dst, st.st_uid, st.st_gid)
    except (OSError, AttributeError):
        pass


def _unlink_quiet(path):
    try:
        os.unlink(path)
    except OSError:
        pass


def video_id_from(text):
    """YouTube-ID aus plugin://-String, URL oder blanker ID herausloesen."""
    text = (text or "").strip()
    if not text:
        return None
    for pattern in (r"video_id=([A-Za-z0-9_-]{11})",      # Emby / neues YouTube-Addon
                    r"videoid=([A-Za-z0-9_-]{11})",       # Kodi-Altformat
                    r"[?&]v=([A-Za-z0-9_-]{11})",
                    r"youtu\.be/([A-Za-z0-9_-]{11})",
                    r"/embed/([A-Za-z0-9_-]{11})"):
        m = re.search(pattern, text)
        if m:
            return m.group(1)
    if YT_ID_RE.fullmatch(text):
        return text
    return None


def format_link(video_id, fmt=DEFAULT_FORMAT):
    """Video-ID in die gewuenschte Schreibweise bringen."""
    if fmt is True:                       # Altaufruf (Schalter 'youtube_url')
        fmt = "url"
    elif fmt is False:
        fmt = "kodi"
    _label, pattern = LINK_FORMATS.get(fmt, LINK_FORMATS[DEFAULT_FORMAT])
    return pattern.format(video_id)


def detect_format(link):
    """Erkennt, in welcher Schreibweise ein vorhandener Link vorliegt."""
    text = (link or "").strip().lower()
    if "video_id=" in text:
        return "emby"
    if "videoid=" in text:
        return "kodi"
    if "youtube.com" in text or "youtu.be" in text:
        return "url"
    return None


def parse_nfo(path):
    """NFO einlesen -> dict oder None."""
    try:
        root = ET.parse(path).getroot()
    except (ET.ParseError, OSError):
        return None
    if root.tag != "movie":
        return None
    tmdb_id, imdb_id = read_ids(root)
    return {
        "title": (root.findtext("title") or Path(path).parent.name).strip(),
        "year": (root.findtext("year") or "").strip(),
        "tmdb": tmdb_id,
        "imdb": imdb_id,
        "trailer": (root.findtext("trailer") or "").strip(),
    }


def walk_nfo_files(root_path, stop=None):
    """NFO-Dateien einsammeln. os.scandir ist ueber SMB deutlich schneller als
    Path.rglob, weil Typ und Groesse schon in der Verzeichnisliste stecken."""
    found = []
    stack = [str(root_path)]
    while stack:
        if stop is not None and stop.is_set():
            break
        current = stack.pop()
        try:
            with os.scandir(current) as it:
                for entry in it:
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            if not entry.name.startswith("."):
                                stack.append(entry.path)
                        elif entry.name.lower().endswith(".nfo"):
                            try:
                                st = entry.stat()
                                found.append((entry.path, st.st_mtime, st.st_size))
                            except OSError:
                                found.append((entry.path, 0, 0))
                    except OSError:
                        continue
        except OSError:
            continue
    return found
