"""Generated secrets: create once, reuse afterwards."""

import config


def test_a_token_from_the_environment_wins():
    assert config.WEBHOOK_TOKEN == "test-token"
    token, persisted = config.ensure_webhook_token()
    assert (token, persisted) == ("test-token", True)


def test_the_token_is_generated_once_and_then_kept(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "WEBHOOK_TOKEN", "")
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)

    first, persisted = config.ensure_webhook_token()
    assert persisted is True
    assert len(first) >= 32
    assert (tmp_path / "webhook_token").read_text(encoding="utf-8") == first

    # The same value on the next start - otherwise every configured webhook
    # would stop working after a restart.
    second, _ = config.ensure_webhook_token()
    assert second == first


def test_without_write_access_the_value_is_temporary(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "WEBHOOK_TOKEN", "")
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "missing")

    def no_access(*args, **kwargs):
        raise OSError("mounted read only")

    monkeypatch.setattr(config.Path, "mkdir", no_access)
    token, persisted = config.ensure_webhook_token()
    assert persisted is False           # so the caller can warn
    assert token


def test_the_session_key_survives_a_restart(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "SECRET_KEY", "")
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    assert config.ensure_secret_key() == config.ensure_secret_key()


def test_environment_credentials_are_detected():
    assert config.credentials_from_env() is True
