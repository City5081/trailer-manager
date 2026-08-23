"""Test setup: make app/ importable and point it at throwaway folders.

config.py reads the environment at import time, so the variables have to be in
place before any application module is loaded.
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
os.environ.setdefault("WEB_PASSWORD", "secret-with-umlaut-ä")
os.environ.setdefault("WEBHOOK_TOKEN", "test-token")
# Password and API key present: create_app treats the instance as configured and
# does not send every request to the setup wizard.
os.environ.setdefault("TMDB_API_KEY", "test-key")
os.environ.setdefault("SCAN_ON_START", "false")
os.environ.setdefault("SCAN_INTERVAL_HOURS", "0")

import pytest                                        # noqa: E402

NFO_SAMPLE = """<?xml version="1.0" encoding="utf-8"?>
<movie>
  <title>Test Movie</title>
  <year>2021</year>
  <uniqueid type="tmdb">550</uniqueid>
  <uniqueid type="imdb">tt0137523</uniqueid>
</movie>
"""


@pytest.fixture
def movie_nfo(tmp_path):
    """An NFO in the usual Emby layout: one folder per movie."""
    folder = tmp_path / "Test Movie (2021)"
    folder.mkdir()
    path = folder / "Test Movie (2021).nfo"
    path.write_text(NFO_SAMPLE, encoding="utf-8")
    return path


@pytest.fixture(scope="session", autouse=True)
def database():
    """One fresh SQLite file per test run."""
    import config
    import db

    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    db.init(config.DB_PATH)
    return db


@pytest.fixture
def client():
    """Flask test client on a configured instance."""
    import db
    import main

    main.create_app()
    db.set_setting("setup_done", "1")
    main.app.config["TESTING"] = True
    with main.app.test_client() as c:
        yield c
