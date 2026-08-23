"""The translation tables have to match."""

import re
from pathlib import Path

import i18n

TEMPLATES = Path(__file__).resolve().parents[1] / "app" / "templates"


def test_both_languages_know_the_same_keys():
    de = set(i18n.STRINGS["de"])
    en = set(i18n.STRINGS["en"])
    assert de - en == set(), "missing in English: {}".format(sorted(de - en))
    assert en - de == set(), "missing in German: {}".format(sorted(en - de))


def test_no_empty_translations():
    for lang, table in i18n.STRINGS.items():
        empty = [k for k, v in table.items() if not str(v).strip()]
        assert empty == [], "{}: empty -> {}".format(lang, empty)


def test_templates_only_use_known_keys():
    known = set(i18n.STRINGS["de"])
    pattern = re.compile(r"t\(\s*'([a-z_]+\.[a-z_]+)'\s*\)")
    for path in TEMPLATES.glob("*.html"):
        for key in pattern.findall(path.read_text(encoding="utf-8")):
            assert key in known, "{}: unknown key {}".format(path.name, key)


def test_fallback_to_german_and_then_to_the_key():
    assert i18n.translate("xx", "app.title") == i18n.STRINGS["de"]["app.title"]
    assert i18n.translate("de", "does.not.exist") == "does.not.exist"
