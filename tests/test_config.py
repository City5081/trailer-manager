"""Erzeugte Geheimnisse: einmal anlegen, danach wiederverwenden."""

import config


def test_token_aus_der_umgebung_hat_vorrang():
    assert config.WEBHOOK_TOKEN == "test-token"
    token, dauerhaft = config.ensure_webhook_token()
    assert (token, dauerhaft) == ("test-token", True)


def test_token_wird_einmal_erzeugt_und_dann_behalten(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "WEBHOOK_TOKEN", "")
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)

    erstes, dauerhaft = config.ensure_webhook_token()
    assert dauerhaft is True
    assert len(erstes) >= 32
    assert (tmp_path / "webhook_token").read_text(encoding="utf-8") == erstes

    # Beim naechsten Start derselbe Wert - sonst waere jeder eingerichtete
    # Webhook nach einem Neustart ungueltig.
    zweites, _ = config.ensure_webhook_token()
    assert zweites == erstes


def test_ohne_schreibrecht_gibt_es_einen_fluechtigen_wert(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "WEBHOOK_TOKEN", "")
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "gibt-es-nicht")

    def kein_zugriff(*args, **kwargs):
        raise OSError("nur lesend eingebunden")

    monkeypatch.setattr(config.Path, "mkdir", kein_zugriff)
    token, dauerhaft = config.ensure_webhook_token()
    assert dauerhaft is False           # der Aufrufer muss warnen koennen
    assert token


def test_sitzungsschluessel_ueberlebt_den_neustart(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "SECRET_KEY", "")
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    assert config.ensure_secret_key() == config.ensure_secret_key()
