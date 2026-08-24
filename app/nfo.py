"""Reading and writing NFO files (Emby/Kodi format).

Two shapes matter: a movie NFO with a <movie> root, one file per movie folder,
and a series NFO named tvshow.nfo with a <tvshow> root, one file per series
folder. Episode NFOs (<episodedetails>) carry no trailer and are skipped.
"""

import os
import re
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

# Emby and Kodi understand two plugin:// spellings; Emby itself writes the first.
LINK_FORMATS = {
    "emby": ("Emby style  plugin://.../play/?video_id=",
             "plugin://plugin.video.youtube/play/?video_id={}"),
    "kodi": ("Kodi legacy  plugin://...?action=play_video&videoid=",
             "plugin://plugin.video.youtube/?action=play_video&videoid={}"),
    "url": ("YouTube URL  https://www.youtube.com/watch?v=",
            "https://www.youtube.com/watch?v={}"),
}
FORMAT_LABELS = {label: keyname for keyname, (label, _fmt) in LINK_FORMATS.items()}
DEFAULT_FORMAT = "emby"
YT_URL_FMT = "https://www.youtube.com/watch?v={}"
YT_ID_RE = re.compile(r"[A-Za-z0-9_-]{11}")


# Root elements we know how to handle, mapped to the kind of library they
# belong to. Everything else - episodes, seasons, artists - is ignored.
ROOT_KINDS = {"movie": "movie", "tvshow": "tv"}
TV_NFO_NAME = "tvshow.nfo"


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
        if pos > 0:                       # keep the previous element's indentation
            children[pos - 1].tail = node.tail
        changed = True
    return changed


def ensure_lockdata(root):
    if root.find("lockdata") is None:
        _append_indented(root, "lockdata", "true")
        return True
    return False


class WriteError(RuntimeError):
    """Write failure with a plain language cause."""


def check_write_access(nfo_path):
    """Check write access to the NFO and its folder. Returns plain text lines."""
    lines = []
    nfo = Path(nfo_path)
    folder = nfo.parent
    lines.append("File:   {}".format(nfo))
    lines.append("Folder: {}".format(folder))

    try:
        st = nfo.stat()
        lines.append("NFO permissions: {:o}, owner UID {}, group GID {}".format(
            st.st_mode & 0o777, st.st_uid, st.st_gid))
    except OSError as e:
        lines.append("NFO not readable: {}".format(e))
        return lines

    lines.append("NFO writable:    {}".format("yes" if os.access(nfo, os.W_OK) else "NO"))
    lines.append("Folder writable: {}".format("yes" if os.access(folder, os.W_OK) else "NO"))

    probe = folder / ".trailer-manager-write-test"
    try:
        probe.write_text("test", encoding="utf-8")
        probe.unlink()
        lines.append("Actual write test in the folder: succeeded")
    except OSError as e:
        lines.append("Actual write test in the folder: FAILED ({})".format(e))

    return lines


def failure_report(nfo_path, error):
    """Everything needed to understand a failed write, as one log entry.

    Permissions are the usual cause and they are awkward to check from the
    outside, so the facts are gathered right when the write fails instead of
    leaving a button in the interface that nobody presses until it is too late.
    """
    lines = [str(error).strip(), ""]
    lines.extend(check_write_access(nfo_path))
    return "\n".join(lines)


def _perm_hint(path):
    return ("Possible causes:\n"
            "  - The SMB share is mounted read only (connected as guest, or set to\n"
            "    'Read-only' under Shares -> SMB Security on Unraid).\n"
            "  - The file belongs to a different user (written by Emby or another\n"
            "    container). On Unraid, Tools -> New Permissions helps.\n"
            "  - The folder itself is not writable - then even the backup copy\n"
            "    fails. Turn off the 'backup (.bak)' option to test.\n\n"
            "Affected: {}".format(path))


def write_trailer(nfo_path, value, lockdata=False, backup=True):
    """Write a trailer link into an NFO. Returns True when something changed."""
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
                    "The backup copy cannot be created - the FOLDER is not "
                    "writable.\n\n" + _perm_hint(bak)) from e
            except OSError as e:
                raise WriteError("Backup copy failed: {}".format(e)) from e

    _write_atomic(tree, nfo_path)
    return True


def _write_atomic(tree, nfo_path):
    """Write to a sibling file first, then rename.

    If writing is cut short - disk full, SMB connection dropped - the old NFO
    stays intact instead of being left half written. When the temporary file
    cannot be created (folder read only but file writable) we write directly.
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
            raise WriteError("The NFO file is write protected.\n\n"
                             + _perm_hint(nfo_path)) from e
        except OSError as e:
            raise WriteError("Writing failed: {}".format(e)) from e

    try:
        tree.write(tmp_path, encoding="utf-8", xml_declaration=True)
        os.chmod(tmp_path, mode)
        _copy_owner(nfo_path, tmp_path)
        os.replace(tmp_path, nfo_path)
    except PermissionError as e:
        _unlink_quiet(tmp_path)
        raise WriteError("The NFO file is write protected.\n\n"
                         + _perm_hint(nfo_path)) from e
    except OSError as e:
        _unlink_quiet(tmp_path)
        raise WriteError("Writing failed: {}".format(e)) from e


def _copy_owner(src, dst):
    """Carry the owner over so Emby can still touch the NFO.

    Only possible when the process has the rights for it - otherwise ignore.
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
    """Pull the YouTube id out of a plugin:// string, a URL or a bare id."""
    text = (text or "").strip()
    if not text:
        return None
    for pattern in (r"video_id=([A-Za-z0-9_-]{11})",      # Emby / current YouTube add-on
                    r"videoid=([A-Za-z0-9_-]{11})",       # Kodi legacy
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
    """Render a video id in the requested spelling."""
    if fmt is True:                       # legacy call (the old 'youtube_url' flag)
        fmt = "url"
    elif fmt is False:
        fmt = "kodi"
    _label, pattern = LINK_FORMATS.get(fmt, LINK_FORMATS[DEFAULT_FORMAT])
    return pattern.format(video_id)


def detect_format(link):
    """Recognise which spelling an existing link uses."""
    text = (link or "").strip().lower()
    if "video_id=" in text:
        return "emby"
    if "videoid=" in text:
        return "kodi"
    if "youtube.com" in text or "youtu.be" in text:
        return "url"
    return None


def parse_nfo(path, kind=None):
    """Read an NFO -> dict or None.

    With `kind` given ("movie" or "tv") a file of the other shape is rejected,
    so a stray movie.nfo inside a series folder cannot end up in the wrong
    library.
    """
    try:
        root = ET.parse(path).getroot()
    except (ET.ParseError, OSError):
        return None
    found_kind = ROOT_KINDS.get(root.tag)
    if found_kind is None or (kind is not None and found_kind != kind):
        return None
    tmdb_id, imdb_id = read_ids(root)
    year = (root.findtext("year") or "").strip()
    if not year:
        # Series usually carry a full premiered date instead of a plain year.
        premiered = (root.findtext("premiered") or "").strip()
        year = premiered[:4] if premiered[:4].isdigit() else ""
    return {
        "title": (root.findtext("title") or Path(path).parent.name).strip(),
        "year": year,
        "tmdb": tmdb_id,
        "imdb": imdb_id,
        "trailer": (root.findtext("trailer") or "").strip(),
        "kind": found_kind,
    }


def _is_hidden(name):
    """True for genuinely hidden folders like .git or .AppleDouble.

    A single leading dot marks a hidden folder; several do not. Titles such as
    "... denn zum Kuessen sind sie da" begin with three, and skipping their
    folder meant the movie never showed up at all.
    """
    return name.startswith(".") and not name.startswith("..")


def walk_nfo_files(root_path, stop=None, only_names=None):
    """Collect NFO files. os.scandir is much faster than Path.rglob over SMB,
    because type and size already come with the directory listing.

    `only_names` narrows the search to specific file names. For series that is
    tvshow.nfo: a show with ten seasons holds hundreds of episode NFOs, and
    opening every one of them just to discard it would dominate the scan.
    """
    wanted = {n.lower() for n in only_names} if only_names else None
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
                            if not _is_hidden(entry.name):
                                stack.append(entry.path)
                        elif (entry.name.lower() in wanted if wanted
                              else entry.name.lower().endswith(".nfo")):
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
