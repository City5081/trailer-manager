"""Testaufbau: app/ importierbar machen und auf Wegwerf-Ordner umlenken.

config.py liest die Umgebung beim Import, deshalb muessen die Variablen stehen,
bevor irgendein Modul der Anwendung geladen wird.
"""

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

_TMP = Path(tempfile.mkdtemp(prefix="trailer-de-tests-"))
os.environ.setdefault("DATA_DIR", str(_TMP / "config"))
os.environ.setdefault("MOVIES_DIR", str(_TMP / "movies"))
os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("WEB_USERNAME", "tester")
os.environ.setdefault("WEB_PASSWORD", "geheim-mit-umlaut-ä")
os.environ.setdefault("WEBHOOK_TOKEN", "test-token")
os.environ.setdefault("SCAN_ON_START", "false")
os.environ.setdefault("SCAN_INTERVAL_HOURS", "0")

import pytest                                        # noqa: E402

NFO_SAMPLE = """<?xml version="1.0" encoding="utf-8"?>
<movie>
  <title>Testfilm</title>
  <year>2021</year>
  <uniqueid type="tmdb">550</uniqueid>
  <uniqueid type="imdb">tt0137523</uniqueid>
</movie>
"""


@pytest.fixture
def movie_nfo(tmp_path):
    """Eine NFO-Datei im typischen Emby-Layout: ein Ordner je Film."""
    folder = tmp_path / "Testfilm (2021)"
    folder.mkdir()
    path = folder / "Testfilm (2021).nfo"
    path.write_text(NFO_SAMPLE, encoding="utf-8")
    return path


@pytest.fixture
def client():
    """Flask-Testclient mit frisch angelegter Datenbank."""
    import config
    import main

    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    main.create_app()
    main.app.config["TESTING"] = True
    with main.app.test_client() as c:
        yield c


@pytest.fixture(scope="session", autouse=True)
def datenbank():
    """Einmal pro Testlauf eine frische SQLite-Datei anlegen."""
    import config
    import db

    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    db.init(config.DB_PATH)
    return db
