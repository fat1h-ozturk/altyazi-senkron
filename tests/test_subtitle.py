import pytest
from pathlib import Path
from altyazi_senkron.models import SubtitleItem
from altyazi_senkron.subtitle import (
    parse_timestamp,
    format_srt_timestamp,
    load_subtitles,
    save_srt,
    detect_file_encoding,
)


def test_parse_timestamp():
    assert parse_timestamp("00:00:01,500") == 1.5
    assert parse_timestamp("01:02:03.400") == 3723.4
    assert parse_timestamp("02:15,250") == 135.25
    assert parse_timestamp("invalid") is None


def test_format_srt_timestamp():
    assert format_srt_timestamp(0.0) == "00:00:00,000"
    assert format_srt_timestamp(1.5) == "00:00:01,500"
    assert format_srt_timestamp(3723.4) == "01:02:03,400"
    assert format_srt_timestamp(-5.0) == "00:00:00,000"


def test_load_and_save_srt(tmp_path: Path):
    srt_content = """1
00:00:05,000 --> 00:00:08,200
Merhaba dünya!
Bu bir test satırıdır.

2
00:00:10.500 --> 00:00:14.000
İkinci altyazı bloğu.
"""
    srt_file = tmp_path / "test.srt"
    srt_file.write_text(srt_content, encoding="utf-8")

    items = load_subtitles(srt_file)
    assert len(items) == 2
    assert items[0].start == 5.0
    assert items[0].end == 8.2
    assert "Merhaba dünya!" in items[0].text
    assert items[1].start == 10.5
    assert items[1].end == 14.0

    out_file = tmp_path / "output.srt"
    save_srt(items, out_file)
    assert out_file.exists()

    reloaded = load_subtitles(out_file)
    assert len(reloaded) == 2
    assert reloaded[0].start == 5.0
    assert reloaded[1].start == 10.5


def test_turkish_cp1254_encoding(tmp_path: Path):
    # Test Turkish characters in Windows-1254 encoding
    text = "1\n00:00:01,000 --> 00:00:03,000\nŞu çılgın Türkler: ğ, ü, ş, ı, ö, ç.\n"
    srt_file = tmp_path / "turkish_cp1254.srt"
    srt_file.write_bytes(text.encode("cp1254"))

    detected = detect_file_encoding(srt_file)
    assert detected is not None

    items = load_subtitles(srt_file)
    assert len(items) == 1
    assert "çılgın" in items[0].text or "Türkler" in items[0].text
