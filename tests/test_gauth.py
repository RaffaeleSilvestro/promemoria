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
