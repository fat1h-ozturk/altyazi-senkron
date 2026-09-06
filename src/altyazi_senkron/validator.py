from typing import List, Dict, Any
from .models import SubtitleItem, SpeechSegment, AlignmentResult


class AlignmentValidator:
    """
    Validates the quality of synchronization and generates detailed diagnostics.
    """

    @staticmethod
    def evaluate(
        aligned_subtitles: List[SubtitleItem],
        speech_segments: List[SpeechSegment],
        result: AlignmentResult,
    ) -> Dict[str, Any]:
        """
        Computes precision, coverage, and overlap statistics.
        """
        if not aligned_subtitles or not speech_segments:
            return {
                "matched_ratio": 0.0,
                "overlap_percentage": 0.0,
                "status": "FAILED",
                "message": "Empty subtitles or speech segments."
            }

        matched_subtitles_count = 0
        total_subtitles = len(aligned_subtitles)

        for sub in aligned_subtitles:
            # Check if there is any speech segment overlapping this subtitle
            has_overlap = any(
                max(0.0, min(sub.end, sp.end) - max(sub.start, sp.start)) > 0.20
                for sp in speech_segments
                if sp.start <= sub.end and sp.end >= sub.start
            )
            if has_overlap:
                matched_subtitles_count += 1

        matched_ratio = matched_subtitles_count / max(1, total_subtitles)
        confidence_pct = result.overall_confidence * 100.0

        if matched_ratio >= 0.85 and confidence_pct >= 75.0:
            status = "EXCELLENT"
        elif matched_ratio >= 0.70 and confidence_pct >= 60.0:
            status = "GOOD"
        elif matched_ratio >= 0.50 and confidence_pct >= 40.0:
            status = "ACCEPTABLE"
        else:
            status = "UNCERTAIN"

        return {
            "matched_ratio": matched_ratio,
            "matched_count": matched_subtitles_count,
            "total_subtitles": total_subtitles,
            "confidence_percentage": confidence_pct,
            "detected_speed": result.detected_speed,
            "detected_offset": result.detected_offset,
            "is_piecewise": result.is_piecewise,
            "status": status,
        }
