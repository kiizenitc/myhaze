import os

from myhaze.config import load_settings


def test_env_file_fills_gaps_but_never_overrides_the_environment(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "# local secrets\n"
        "AQICN_TOKEN=from_file\n"
        "SUPABASE_DB_URL=\n"
        "MYHAZE_TEST_QUOTED='quoted value'\n"
    )
    monkeypatch.setenv("AQICN_TOKEN", "from_env")
    monkeypatch.delenv("SUPABASE_DB_URL", raising=False)
    monkeypatch.setenv("MYHAZE_TEST_QUOTED", "placeholder")
    monkeypatch.delenv("MYHAZE_TEST_QUOTED")  # registers cleanup for the value the loader sets

    settings = load_settings(env_file)

    assert settings.aqicn_token == "from_env"
    assert settings.db_url is None
    assert os.environ["MYHAZE_TEST_QUOTED"] == "quoted value"
