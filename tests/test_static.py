"""The stylesheet has to be structurally sound.

A truncated rule block does not raise anything - the browser silently drops the
rest of the file, and the layout quietly falls apart. Cheap to catch here.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CSS = ROOT / "app" / "static" / "style.css"
TEMPLATES = ROOT / "app" / "templates"


def test_every_block_is_closed():
    text = CSS.read_text(encoding="utf-8")
    depth = 0
    for line_no, line in enumerate(text.split("\n"), 1):
        depth += line.count("{") - line.count("}")
        assert depth >= 0, "line {}: one closing brace too many".format(line_no)
    assert depth == 0, "{} block(s) left open".format(depth)


def test_media_queries_are_not_truncated():
    text = CSS.read_text(encoding="utf-8")
    for match in re.finditer(r"@media[^{]*\{", text):
        depth, closed = 0, False
        for ch in text[match.end() - 1:]:
            depth += (ch == "{") - (ch == "}")
            if depth == 0:
                closed = True
                break
        assert closed, "unterminated {}".format(match.group(0).strip())


def test_classes_the_templates_rely_on_exist():
    text = CSS.read_text(encoding="utf-8")
    for name in ("tablewrap", "hide-sm", "hide-xs", "libcard", "libhead"):
        assert "." + name in text, "{} is used in the templates but not styled".format(name)


def test_hideable_columns_are_marked_in_the_movie_list():
    """Without these classes the table cannot shrink on a phone."""
    index = (TEMPLATES / "index.html").read_text(encoding="utf-8")
    assert index.count("hide-sm") >= 6      # three columns, header and body
    assert index.count("hide-xs") >= 2
    assert "tablewrap" in index
