import json

import pytest

from promemoria.core import gauth


def test_validate_and_import_client_file(tmp_path):
    good = tmp_path / "client.json"
    good.write_text(json.dumps({"installed": {"client_id": "abc", "client_secret": "x"}}))
    data_dir = tmp_path / "data"
    target = gauth.import_client_file(good, data_dir)
    assert target == data_dir / gauth.CLIENT_FILE_NAME and target.exists()


@pytest.mark.parametrize("content, match", [
    ("non json", "leggere"),
    (json.dumps({"web": {"client_id": "abc"}}), "App desktop"),
    (json.dumps({"installed": {}}), "client_id"),
])
def test_validate_rejects_bad_files(tmp_path, content, match):
    bad = tmp_path / "c.json"
    bad.write_text(content)
    with pytest.raises(gauth.GAuthError, match=match):
        gauth.validate_client_file(bad)


def test_session_rejects_garbage():
    with pytest.raises(gauth.GAuthError):
        gauth.session("non json")


CREDS = json.dumps({"client_id": "c", "client_secret": "s", "refresh_token": "r"})


@pytest.mark.parametrize("retryable, expected", [
    (False, gauth.GAuthError), (True, ConnectionError)])
def test_refresh_error_is_translated(monkeypatch, retryable, expected):
    from google.auth.exceptions import RefreshError
    from google.oauth2.credentials import Credentials

    def fail(self, request):
        raise RefreshError("invalid_grant: Token has been expired or revoked.",
                           retryable=retryable)

    monkeypatch.setattr(Credentials, "refresh", fail)
    with pytest.raises(expected) as err:
        gauth.session(CREDS).request("GET", "https://example.invalid", timeout=1)
    if not retryable:
        assert "Ricollega" in str(err.value)


def test_network_error_during_refresh_is_translated(monkeypatch):
    from google.auth.exceptions import TransportError
    from google.oauth2.credentials import Credentials

    def fail(self, request):
        raise TransportError("dns")

    monkeypatch.setattr(Credentials, "refresh", fail)
    with pytest.raises(ConnectionError):
        gauth.session(CREDS).request("GET", "https://example.invalid", timeout=1)
