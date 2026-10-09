import json

from samovar_lite import settings as settings_module
from samovar_lite.settings import Settings


def test_defaults_when_file_is_missing(tmp_path):
    settings = Settings(str(tmp_path / "settings.json"))
    assert settings["volume"] == 100
    assert settings["repeat"] == "off"
    assert settings["sub_codepage"] == "cp1256"


def test_round_trip_keeps_unicode_paths(tmp_path):
    path = tmp_path / "nested" / "settings.json"
    settings = Settings(str(path))
    settings["volume"] = 40
    settings.add_recent("/videos/فیلم.mkv")
    settings.save()
    again = Settings(str(path))
    assert again["volume"] == 40
    assert again["recent"] == ["/videos/فیلم.mkv"]
    assert "فیلم" in path.read_text(encoding="utf-8")


def test_broken_file_falls_back_to_defaults(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text("{not json", encoding="utf-8")
    assert Settings(str(path))["volume"] == 100


def test_recent_list_is_deduplicated_and_capped(tmp_path):
    settings = Settings(str(tmp_path / "settings.json"))
    for i in range(30):
        settings.add_recent("/v/%d.mkv" % i)
    settings.add_recent("/v/5.mkv")
    assert len(settings["recent"]) == 20
    assert settings["recent"][0] == "/v/5.mkv"
    assert settings["recent"].count("/v/5.mkv") == 1


def test_resume_positions(tmp_path):
    settings = Settings(str(tmp_path / "settings.json"))
    settings.set_position("/v/a.mkv", 61.26)
    assert settings.get_position("/v/a.mkv") == 61.3
    settings.set_position("/v/a.mkv", None)
    assert settings.get_position("/v/a.mkv") is None


def test_forced_codepage_prefix_is_dropped(tmp_path):
    # "+cp1256" would force the code page even for UTF-8 files; older settings files contain it.
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"sub_codepage": "+cp1256"}), encoding="utf-8")
    assert Settings(str(path))["sub_codepage"] == "cp1256"


def test_settings_from_before_the_rename_are_picked_up(tmp_path, monkeypatch):
    legacy = tmp_path / "fast-pot-player" / "settings.json"
    legacy.parent.mkdir()
    legacy.write_text(json.dumps({"volume": 35}), encoding="utf-8")
    current = tmp_path / "samovar-lite" / "settings.json"
    monkeypatch.setattr(settings_module, "CONFIG_FILE", str(current))
    monkeypatch.setattr(settings_module, "LEGACY_FILE", str(legacy))
    settings = Settings(str(current))
    assert settings["volume"] == 35
    settings.save()
    assert json.loads(current.read_text(encoding="utf-8"))["volume"] == 35
