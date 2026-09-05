import pytest
import numpy as np
from altyazi_senkron.models import SubtitleItem, SpeechSegment
from altyazi_senkron.matcher import SubtitleMatcher


def generate_dialogues(num_dialogues=60, base_interval=5.0):
    """Generate realistic dialogue timestamps with varying gaps and durations."""
    np.random.seed(42)
    subtitles = []
    current_time = 10.0

    for i in range(num_dialogues):
        duration = float(np.random.uniform(1.2, 4.5))
        gap = float(np.random.uniform(0.8, 8.0))
        start = current_time
        end = start + duration
        subtitles.append(
            SubtitleItem(
                index=i + 1,
                start=start,
                end=end,
                text=f"Dialogue line {i + 1}",
            )
        )
        current_time = end + gap

    return subtitles


def test_linear_offset_recovery():
    """Test recovering a constant shift (e.g. +3.5 seconds)."""
    subtitles = generate_dialogues(50)
    true_offset = 3.500
    true_slope = 1.000

    # Simulate detected speech by applying ground truth transformation
    speech_segments = [
        SpeechSegment(
            start=true_slope * s.start + true_offset,
            end=true_slope * s.end + true_offset,
            text=s.text,
        )
        for s in subtitles
    ]

    matcher = SubtitleMatcher()
    result = matcher.align(subtitles, speech_segments)

    assert result.overall_confidence > 0.85
    assert abs(result.detected_speed - true_slope) < 0.005
    assert abs(result.detected_offset - true_offset) < 0.150


def test_fps_drift_recovery():
    """Test recovering 23.976 -> 25 fps drift (~1.04271) + offset."""
    subtitles = generate_dialogues(60)
    true_slope = 25.0 / 23.976024  # 1.04271
    true_offset = 2.100

    speech_segments = [
        SpeechSegment(
            start=true_slope * s.start + true_offset,
            end=true_slope * s.end + true_offset,
            text=s.text,
        )
        for s in subtitles
    ]

    matcher = SubtitleMatcher()
    result = matcher.align(subtitles, speech_segments)

    assert result.overall_confidence > 0.85
    assert abs(result.detected_speed - true_slope) < 0.005
    assert abs(result.detected_offset - true_offset) < 0.150


def test_noise_and_outlier_resilience():
    """Test that random sound effects or missing lines don't throw off RANSAC."""
    subtitles = generate_dialogues(50)
    true_slope = 1.000
    true_offset = 4.200

    speech_segments = []
    # Include matching lines
    for s in subtitles:
        speech_segments.append(
            SpeechSegment(
                start=s.start + true_offset,
                end=s.end + true_offset,
                text=s.text,
            )
        )

    # Add 20 random sound noise segments (false positives that fooled ffsubsync)
    np.random.seed(99)
    for _ in range(20):
        rand_start = float(np.random.uniform(0, 300))
        speech_segments.append(
            SpeechSegment(
                start=rand_start,
                end=rand_start + float(np.random.uniform(0.5, 3.0)),
                text="Noise / Music",
            )
        )

    # Sort speech segments by time
    speech_segments.sort(key=lambda x: x.start)

    matcher = SubtitleMatcher()
    result = matcher.align(subtitles, speech_segments)

    # RANSAC should effortlessly isolate the true line despite noise
    assert result.overall_confidence > 0.75
    assert abs(result.detected_speed - true_slope) < 0.01
    assert abs(result.detected_offset - true_offset) < 0.200


def test_piecewise_cut_detection():
    """Test detecting a commercial break jump (piecewise discontinuity)."""
    subtitles = generate_dialogues(60)
    split_point = 30  # Halfway through the video

    true_slope = 1.000
    offset1 = 2.000
    offset2 = 45.000  # 43-second commercial gap inserted/removed

    speech_segments = []
    for i, s in enumerate(subtitles):
        if i < split_point:
            speech_segments.append(
                SpeechSegment(start=s.start + offset1, end=s.end + offset1)
            )
        else:
            speech_segments.append(
                SpeechSegment(start=s.start + offset2, end=s.end + offset2)
            )

    speech_segments.sort(key=lambda x: x.start)

    matcher = SubtitleMatcher()
    result = matcher.align(subtitles, speech_segments)

    assert result.is_piecewise is True
    assert len(result.segments) == 2
    assert abs(result.segments[0].offset - offset1) < 0.250
    assert abs(result.segments[1].offset - offset2) < 0.250
