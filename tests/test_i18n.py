"""Die Uebersetzungstabellen muessen deckungsgleich sein."""

import re
from pathlib import Path

import i18n

TEMPLATES = Path(__file__).resolve().parents[1] / "app" / "templates"


def test_beide_sprachen_kennen_dieselben_schluessel():
    de = set(i18n.STRINGS["de"])
    en = set(i18n.STRINGS["en"])
    assert de - en == set(), "fehlt auf Englisch: {}".format(sorted(de - en))
    assert en - de == set(), "fehlt auf Deutsch: {}".format(sorted(en - de))


def test_keine_leeren_uebersetzungen():
    for lang, tabelle in i18n.STRINGS.items():
        leer = [k for k, v in tabelle.items() if not str(v).strip()]
        assert leer == [], "{}: leer -> {}".format(lang, leer)


def test_templates_verwenden_nur_bekannte_schluessel():
    bekannt = set(i18n.STRINGS["de"])
    muster = re.compile(r"t\(\s*'([a-z_]+\.[a-z_]+)'\s*\)")
    for datei in TEMPLATES.glob("*.html"):
        for key in muster.findall(datei.read_text(encoding="utf-8")):
            assert key in bekannt, "{}: unbekannter Schluessel {}".format(datei.name, key)


def test_rueckfall_auf_deutsch_und_auf_den_schluessel():
    assert i18n.translate("xx", "app.title") == i18n.STRINGS["de"]["app.title"]
    assert i18n.translate("de", "gibt.es.nicht") == "gibt.es.nicht"
