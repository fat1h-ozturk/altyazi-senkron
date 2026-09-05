import pytest
from altyazi_senkron.models import SubtitleItem, SpeechSegment, AlignmentSegment
from altyazi_senkron.snapper import SubtitleSnapper


def test_snapper_fine_tuning():
    subtitles = [
        SubtitleItem(index=1, start=10.15, end=13.05, text="Hello"),
    ]
    # Speech actually starts at 10.0 and ends at 13.2
    speech = [
        SpeechSegment(start=10.00, end=13.20, text="Hello"),
    ]
    segment = AlignmentSegment(
        sub_start=0.0, sub_end=100.0, slope=1.0, offset=0.0
    )

    snapper = SubtitleSnapper(snap_window=0.30)
    snapped = snapper.snap(subtitles, speech, [segment])

    assert len(snapped) == 1
    assert abs(snapped[0].start - 10.00) < 0.01
    assert abs(snapped[0].end - 13.20) < 0.01


def test_snapper_min_duration():
    # Very short speech (e.g. 0.2s grunt)
    subtitles = [
        SubtitleItem(index=1, start=5.0, end=5.2, text="Oh!"),
    ]
    speech = [
        SpeechSegment(start=5.0, end=5.2, text="Oh!"),
    ]
    segment = AlignmentSegment(
        sub_start=0.0, sub_end=100.0, slope=1.0, offset=0.0
    )

    snapper = SubtitleSnapper(min_subtitle_duration=0.8)
    snapped = snapper.snap(subtitles, speech, [segment])

    assert len(snapped) == 1
    assert round(snapped[0].duration, 3) >= 0.8
