from typing import List
from .models import SubtitleItem, SpeechSegment, AlignmentSegment


class SubtitleSnapper:
    """
    Fine-tunes subtitle timestamps by snapping start and end times to
    exact speech onsets and offsets detected by VAD/ASR.
    """

    def __init__(
        self,
        snap_window: float = 0.40,      # Max search distance in seconds to snap
        min_subtitle_duration: float = 0.80,  # Minimum display time for readability
        min_gap: float = 0.05,          # Minimum gap between consecutive subtitles (50ms)
    ):
        self.snap_window = snap_window
        self.min_subtitle_duration = min_subtitle_duration
        self.min_gap = min_gap

    def snap(
        self,
        subtitles: List[SubtitleItem],
        speech_segments: List[SpeechSegment],
        segments: List[AlignmentSegment],
    ) -> List[SubtitleItem]:
        """
        Applies linear alignment parameters and snaps timestamps to true speech boundaries.
        """
        if not subtitles:
            return []

        snapped_items: List[SubtitleItem] = []

        # Sort speech segments by start time
        speech_sorted = sorted(speech_segments, key=lambda s: s.start)

        for sub in subtitles:
            # 1. Apply applicable alignment segment
            seg = segments[0]
            for s in segments:
                if s.sub_start <= sub.start <= s.sub_end:
                    seg = s
                    break

            new_start = seg.apply(sub.start)
            new_end = seg.apply(sub.end)

            # 2. Find closest speech onset within snap_window
            best_start_snap = new_start
            min_start_diff = self.snap_window

            for sp in speech_sorted:
                diff = abs(sp.start - new_start)
                if diff < min_start_diff:
                    min_start_diff = diff
                    best_start_snap = sp.start
                if sp.start > new_start + self.snap_window:
                    break

            # 3. Find closest speech offset within snap_window
            best_end_snap = new_end
            min_end_diff = self.snap_window

            for sp in speech_sorted:
                diff = abs(sp.end - new_end)
                if diff < min_end_diff:
                    min_end_diff = diff
                    best_end_snap = sp.end
                if sp.start > new_end + self.snap_window:
                    break

            # Ensure start < end and respect minimum duration
            final_start = max(0.0, best_start_snap)
            final_end = max(final_start + self.min_subtitle_duration, best_end_snap)

            snapped_items.append(
                SubtitleItem(
                    index=sub.index,
                    start=final_start,
                    end=final_end,
                    text=sub.text,
                )
            )

        # 4. Final pass: prevent overlapping between adjacent subtitles
        for i in range(len(snapped_items) - 1):
            curr = snapped_items[i]
            nxt = snapped_items[i + 1]
            if curr.end + self.min_gap > nxt.start:
                # Prefer no-overlap over minimum duration guarantee.
                # Clamp curr.end so there is always at least min_gap before next.
                safe_end = nxt.start - self.min_gap
                if safe_end > curr.start:
                    curr.end = safe_end
                else:
                    # Subtitles are so close together we can't fit even the gap;
                    # keep curr as short as possible without going negative.
                    curr.end = max(curr.start, nxt.start - self.min_gap)

        return snapped_items
