import pytest
from pathlib import Path
from altyazi_senkron.batch import find_video_subtitle_pairs, extract_episode_id, get_synced_output_path


def test_extract_episode_id():
    assert extract_episode_id("Breaking.Bad.S01E05.720p.mkv") == "s01e05"
    assert extract_episode_id("dizi_1x03.mp4") == "s01e03"
    assert extract_episode_id("Show.S02E01-E02.1080p.mkv") == "s02e01-e02"
    assert extract_episode_id("Show.S02E01-02.1080p.mkv") == "s02e01-e02"
    assert extract_episode_id("Show.02x01-02.1080p.mkv") == "s02e01-e02"
    assert extract_episode_id("Movie.2024.1080p.mkv") is None


def test_get_synced_output_path():
    video = Path("/videos/Inception.2010.mkv")
    sub = Path("/videos/Inception.2010.tr.srt")
    out = get_synced_output_path(video, sub)
    assert out.name == "Inception.2010.tr[synced].srt"

    # If video already had .tr in stem
    video2 = Path("/videos/Inception.2010.tr.mkv")
    out2 = get_synced_output_path(video2, sub)
    assert out2.name == "Inception.2010.tr[synced].srt"


def test_find_video_subtitle_pairs(tmp_path: Path):
    # Create test files
    (tmp_path / "Series.S01E01.1080p.mkv").touch()
    (tmp_path / "Series.S01E01.tr.srt").touch()

    (tmp_path / "Series.S01E02.1080p.mkv").touch()
    (tmp_path / "Series.S01E02.1080p.tr.srt").touch()

    (tmp_path / "Movie.2023.mp4").touch()
    (tmp_path / "Movie.2023.srt").touch()

    # Create an already synced file that should be ignored
    (tmp_path / "Series.S01E01.1080p.tr[synced].srt").touch()

    # Non-video file
    (tmp_path / "notes.txt").touch()

    pairs = find_video_subtitle_pairs(tmp_path)
    assert len(pairs) == 3

    # Check pair 1
    v1, s1, o1 = pairs[0]
    assert v1.name == "Movie.2023.mp4"
    assert s1.name == "Movie.2023.srt"
    assert o1.name == "Movie.2023.tr[synced].srt"

    # Check S01E01
    ep1_pair = [p for p in pairs if "S01E01" in p[0].name][0]
    assert ep1_pair[1].name == "Series.S01E01.tr.srt"
    assert ep1_pair[2].name == "Series.S01E01.1080p.tr[synced].srt"

    # Check S01E02
    ep2_pair = [p for p in pairs if "S01E02" in p[0].name][0]
    assert ep2_pair[1].name == "Series.S01E02.1080p.tr.srt"
    assert ep2_pair[2].name == "Series.S01E02.1080p.tr[synced].srt"
