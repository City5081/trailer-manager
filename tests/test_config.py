"""Generated secrets: create once, reuse afterwards."""

import config


def test_the_session_key_survives_a_restart(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "SECRET_KEY", "")
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    assert config.ensure_secret_key() == config.ensure_secret_key()


def test_environment_credentials_are_detected():
    assert config.credentials_from_env() is True
