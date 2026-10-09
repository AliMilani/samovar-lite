import os

import pytest

from samovar_lite import util


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [(0, "00:00:00"), (59.9, "00:00:59"), (3661, "01:01:01"), (None, "00:00:00"), (-5, "00:00:00")],
)
def test_fmt_time(seconds, expected):
    assert util.fmt_time(seconds) == expected


@pytest.mark.parametrize(
    ("text", "duration", "expected"),
    [
        ("90", None, 90.0),
        ("1:30", None, 90.0),
        ("01:02:03", None, 3723.0),
        ("0:00:01.5", None, 1.5),
        ("50%", 200.0, 100.0),
        ("150%", 200.0, 200.0),
        ("50%", None, None),
        ("", None, None),
        ("abc", None, None),
        ("1:2:3:4", None, None),
    ],
)
def test_parse_time(text, duration, expected):
    assert util.parse_time(text, duration) == expected


def test_natural_sort_orders_numbers_by_value():
    names = ["ep10.mkv", "ep2.mkv", "Ep1.mkv"]
    assert sorted(names, key=util.natural_key) == ["Ep1.mkv", "ep2.mkv", "ep10.mkv"]


def test_kind_detection():
    assert util.is_media("Movie.MKV")
    assert util.is_media("song.flac")
    assert not util.is_media("notes.txt")
    assert util.is_sub("movie.srt")
    assert not util.is_sub("readme.txt")
    assert util.is_url("https://example.org/a.mp4")
    assert not util.is_url("/home/user/a.mp4")
    assert not util.is_url("C:relative")


def test_similar_files_groups_episodes(tmp_path):
    for name in ("Show.S01E01.mkv", "Show.S01E02.mkv", "Show.S01E10.mkv", "Other.Film.2020.mkv", "Show.S01E01.srt"):
        (tmp_path / name).write_bytes(b"")
    group = util.similar_files(str(tmp_path / "Show.S01E02.mkv"))
    assert [os.path.basename(p) for p in group] == ["Show.S01E01.mkv", "Show.S01E02.mkv", "Show.S01E10.mkv"]


def test_similar_files_leaves_unrelated_videos_alone(tmp_path):
    for name in ("Holiday.mp4", "Wedding.mp4"):
        (tmp_path / name).write_bytes(b"")
    assert util.similar_files(str(tmp_path / "Holiday.mp4")) == [str(tmp_path / "Holiday.mp4")]


def test_similar_files_queues_a_whole_album(tmp_path):
    for name in ("02 - Second.mp3", "01 - First.mp3", "cover.jpg"):
        (tmp_path / name).write_bytes(b"")
    group = util.similar_files(str(tmp_path / "02 - Second.mp3"))
    assert [os.path.basename(p) for p in group] == ["01 - First.mp3", "02 - Second.mp3"]


def test_expand_paths_walks_folders_in_natural_order(tmp_path):
    (tmp_path / "b").mkdir()
    for name in ("a10.mp4", "a2.mp4", "notes.txt", "b/c.mkv"):
        (tmp_path / name).write_bytes(b"")
    found = util.expand_paths([str(tmp_path), "https://example.org/x.mp4"])
    assert [os.path.relpath(p, tmp_path) for p in found[:-1]] == ["a2.mp4", "a10.mp4", "b/c.mkv"]
    assert found[-1] == "https://example.org/x.mp4"


def test_read_m3u_resolves_relative_entries(tmp_path):
    playlist = tmp_path / "list.m3u8"
    playlist.write_text(
        "#EXTM3U\n#EXTINF:1,One\none.mp4\n\n/abs/two.mp4\nhttps://example.org/three.mp4\n", encoding="utf-8"
    )
    assert util.read_playlist_file(str(playlist)) == [
        str(tmp_path / "one.mp4"),
        "/abs/two.mp4",
        "https://example.org/three.mp4",
    ]


def test_read_pls(tmp_path):
    playlist = tmp_path / "list.pls"
    playlist.write_text("[playlist]\nFile1=/music/a.mp3\nTitle1=A\nFile2=b.mp3\nNumberOfEntries=2\n", encoding="utf-8")
    assert util.read_playlist_file(str(playlist)) == ["/music/a.mp3", str(tmp_path / "b.mp3")]


def test_human_size():
    assert util.human_size(512) == "512 B"
    assert util.human_size(1536) == "1.5 KB"
    assert util.human_size(None) == ""
