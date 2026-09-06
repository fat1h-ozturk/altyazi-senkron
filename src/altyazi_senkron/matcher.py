import math
from typing import List, Tuple, Optional, Dict
import numpy as np
from scipy.optimize import minimize
from .models import SubtitleItem, SpeechSegment, AlignmentSegment, AlignmentResult


class SubtitleMatcher:
    """
    Robust alignment engine for synchronizing subtitles with detected speech.
    Uses RANSAC, rhythm fingerprinting, and piecewise discontinuity detection.
    """

    # Common film/video framerate ratios
    CANONICAL_SPEEDS = [
        1.0,                    # Identical fps
        25.0 / 23.976024,       # ~1.04271 (23.976 -> 25 PAL)
        23.976024 / 25.0,       # ~0.95904 (25 -> 23.976 NTSC)
        24.0 / 23.976024,       # ~1.00100
        23.976024 / 24.0,       # ~0.99900
        25.0 / 24.0,            # ~1.04167
        24.0 / 25.0,            # ~0.96000
        30.0 / 25.0,            # ~1.20000 (PAL -> 30fps)
        25.0 / 30.0,            # ~0.83333
        29.97002997 / 25.0,     # ~1.19880 (PAL -> NTSC)
        25.0 / 29.97002997,     # ~0.83472
        29.97002997 / 24.0,     # ~1.24875 (24fps -> NTSC)
        24.0 / 29.97002997,     # ~0.80080
    ]

    def __init__(
        self,
        min_speed: float = 0.79,   # widened to cover 24/29.97 (~0.80080)
        max_speed: float = 1.26,   # widened to cover 29.97/24 (~1.24875)
        inlier_tolerance: float = 0.40,  # Max distance in seconds to consider an inlier
    ):
        self.min_speed = min_speed
        self.max_speed = max_speed
        self.inlier_tolerance = inlier_tolerance

    def align(
        self,
        subtitles: List[SubtitleItem],
        speech_segments: List[SpeechSegment],
    ) -> AlignmentResult:
        """
        Calculates optimal synchronization parameters between subtitles and speech segments.
        Handles speed drift, constant delay, and piecewise commercial cuts.
        """
        if not subtitles or not speech_segments:
            return AlignmentResult(
                warnings=["Insufficient subtitles or speech segments to perform alignment."]
            )

        sub_starts = np.array([s.start for s in subtitles], dtype=np.float64)
        sub_ends = np.array([s.end for s in subtitles], dtype=np.float64)
        sub_mids = (sub_starts + sub_ends) / 2.0
        sub_durs = sub_ends - sub_starts

        audio_starts = np.array([a.start for a in speech_segments], dtype=np.float64)
        audio_ends = np.array([a.end for a in speech_segments], dtype=np.float64)
        audio_mids = (audio_starts + audio_ends) / 2.0
        audio_durs = audio_ends - audio_starts

        # Step 1: Find best global hypotheses using rhythm fingerprints & canonical speeds
        best_slope, best_offset, best_score = self._find_global_alignment(
            sub_mids, sub_durs, audio_mids, audio_durs
        )

        # Step 2: Refine global parameters with bounded optimization on inliers
        refined_slope, refined_offset, inliers_mask = self._refine_linear(
            sub_mids, audio_mids, best_slope, best_offset
        )

        inliers_count = int(np.sum(inliers_mask))
        total_subs = len(subtitles)
        inliers_ratio = inliers_count / max(1, total_subs)

        # Step 3: Check for piecewise discontinuities (cut scenes / commercial breaks)
        segments = self._detect_piecewise_cuts(
            subtitles,
            sub_mids,
            audio_mids,
            refined_slope,
            refined_offset,
            inliers_mask,
        )

        is_piecewise = len(segments) > 1

        # Step 4: Calculate overall confidence score
        confidence = self._compute_alignment_confidence(
            subtitles,
            speech_segments,
            segments,
        )

        warnings = []
        if confidence < 0.65:
            warnings.append(
                f"Low confidence ({confidence * 100:.1f}%). Subtitle text may not match video dialogue."
            )
        if abs(refined_slope - 1.0) > 0.05:
            warnings.append(
                f"Significant speed drift detected ({refined_slope:.4f}x). Framerate conversion applied."
            )

        return AlignmentResult(
            segments=segments,
            overall_confidence=confidence,
            detected_speed=refined_slope,
            detected_offset=refined_offset,
            is_piecewise=is_piecewise,
            inliers_ratio=inliers_ratio,
            warnings=warnings,
        )

    def _find_global_alignment(
        self,
        sub_mids: np.ndarray,
        sub_durs: np.ndarray,
        audio_mids: np.ndarray,
        audio_durs: np.ndarray,
    ) -> Tuple[float, float, float]:
        """
        Find candidate global (slope, offset) using 1D difference histogram & canonical speeds.
        """
        best_slope = 1.0
        best_offset = 0.0
        best_score = -1.0

        # Test candidate speeds: Canonical speeds first, then fine range if needed
        candidate_speeds = list(self.CANONICAL_SPEEDS)

        # Also sample speeds from rhythm pairs (RANSAC fingerprints)
        fingerprint_speeds = self._extract_fingerprint_speeds(
            sub_mids, sub_durs, audio_mids, audio_durs
        )
        candidate_speeds.extend(fingerprint_speeds)

        for speed in candidate_speeds:
            if not (self.min_speed <= speed <= self.max_speed):
                continue

            scaled_sub_mids = speed * sub_mids
            offset, score = self._find_best_offset_for_speed(
                scaled_sub_mids, audio_mids
            )

            if score > best_score:
                best_score = score
                best_slope = speed
                best_offset = offset

        return best_slope, best_offset, best_score

    def _find_best_offset_for_speed(
        self,
        scaled_sub_mids: np.ndarray,
        audio_mids: np.ndarray,
        bin_width: float = 0.25,
    ) -> Tuple[float, float]:
        """
        Computes 1D difference histogram between audio_mids and scaled_sub_mids.
        Matching speech pairs form a sharp spike at the true offset!
        """
        # For efficiency, compute pairwise differences for sub-sampled items if list is large
        if len(scaled_sub_mids) > 600:
            step = len(scaled_sub_mids) // 400
            s_sample = scaled_sub_mids[::step]
        else:
            s_sample = scaled_sub_mids

        if len(audio_mids) > 800:
            step_a = len(audio_mids) // 500
            a_sample = audio_mids[::step_a]
        else:
            a_sample = audio_mids

        # Pairwise differences: offset = audio - sub
        diffs = a_sample[:, None] - s_sample[None, :]
        diffs_flat = diffs.ravel()

        # Remove impossible offsets (e.g. video offset > 2 hours or < -2 hours)
        valid_mask = np.abs(diffs_flat) < 7200.0
        diffs_valid = diffs_flat[valid_mask]

        if len(diffs_valid) == 0:
            return 0.0, 0.0

        min_val = np.min(diffs_valid)
        max_val = np.max(diffs_valid)
        num_bins = int(np.ceil((max_val - min_val) / bin_width))
        num_bins = max(1, min(num_bins, 100000))

        counts, bin_edges = np.histogram(diffs_valid, bins=num_bins, range=(min_val, max_val))
        
        # Find top 5 peaks
        top_peak_indices = np.argsort(counts)[-5:][::-1]
        best_offset = 0.0
        best_score = -1.0

        for peak_idx in top_peak_indices:
            candidate_offset = 0.5 * (bin_edges[peak_idx] + bin_edges[peak_idx + 1])
            # Evaluate exact inlier count around candidate offset
            score = self._score_inliers(scaled_sub_mids + candidate_offset, audio_mids)
            if score > best_score:
                best_score = score
                best_offset = candidate_offset

        return best_offset, best_score

    def _extract_fingerprint_speeds(
        self,
        sub_mids: np.ndarray,
        sub_durs: np.ndarray,
        audio_mids: np.ndarray,
        audio_durs: np.ndarray,
        max_samples: int = 40,
    ) -> List[float]:
        """
        Matches distinctive inter-dialogue gaps to discover non-standard speeds.
        """
        speeds: List[float] = []
        if len(sub_mids) < 2 or len(audio_mids) < 2:
            return speeds

        # Calculate consecutive gaps
        sub_gaps = sub_mids[1:] - sub_mids[:-1]
        audio_gaps = audio_mids[1:] - audio_mids[:-1]

        # Filter gaps between 1.0s and 20.0s
        s_mask = (sub_gaps >= 1.0) & (sub_gaps <= 20.0)
        a_mask = (audio_gaps >= 1.0) & (audio_gaps <= 20.0)

        s_valid = sub_gaps[s_mask]
        a_valid = audio_gaps[a_mask]

        if len(s_valid) == 0 or len(a_valid) == 0:
            return speeds

        # Sample distinctive gaps
        for s_gap in s_valid[:max_samples]:
            # find audio gaps with ratio in [min_speed, max_speed]
            ratios = a_valid / s_gap
            valid_ratios = ratios[(ratios >= self.min_speed) & (ratios <= self.max_speed)]
            for r in valid_ratios:
                speeds.append(float(r))

        return speeds[:20]

    def _score_inliers(
        self,
        mapped_sub_mids: np.ndarray,
        audio_mids: np.ndarray,
    ) -> float:
        """
        Fast count of mapped subtitle midpoints that are within inlier_tolerance of audio midpoints.
        """
        if len(mapped_sub_mids) == 0 or len(audio_mids) == 0:
            return 0.0

        idx = np.searchsorted(audio_mids, mapped_sub_mids)
        idx_clamped = np.clip(idx, 0, len(audio_mids) - 1)
        idx_prev = np.clip(idx - 1, 0, len(audio_mids) - 1)

        dist1 = np.abs(audio_mids[idx_clamped] - mapped_sub_mids)
        dist2 = np.abs(audio_mids[idx_prev] - mapped_sub_mids)
        min_dist = np.minimum(dist1, dist2)

        inliers = min_dist <= self.inlier_tolerance
        return float(np.sum(inliers))

    def _refine_linear(
        self,
        sub_mids: np.ndarray,
        audio_mids: np.ndarray,
        init_slope: float,
        init_offset: float,
    ) -> Tuple[float, float, np.ndarray]:
        """
        Refine slope and offset using least-squares on verified inliers.
        """
        mapped = init_slope * sub_mids + init_offset
        idx = np.searchsorted(audio_mids, mapped)
        idx_clamped = np.clip(idx, 0, len(audio_mids) - 1)
        idx_prev = np.clip(idx - 1, 0, len(audio_mids) - 1)

        dist1 = np.abs(audio_mids[idx_clamped] - mapped)
        dist2 = np.abs(audio_mids[idx_prev] - mapped)
        use_clamped = dist1 < dist2
        best_audio_idx = np.where(use_clamped, idx_clamped, idx_prev)
        min_dist = np.where(use_clamped, dist1, dist2)

        inliers_mask = min_dist <= self.inlier_tolerance

        if np.sum(inliers_mask) < 4:
            return init_slope, init_offset, inliers_mask

        sub_inliers = sub_mids[inliers_mask]
        audio_inliers = audio_mids[best_audio_idx[inliers_mask]]

        # Fit least-squares line: audio = slope * sub + offset
        A = np.vstack([sub_inliers, np.ones(len(sub_inliers))]).T
        res, _, _, _ = np.linalg.lstsq(A, audio_inliers, rcond=None)
        refined_slope = float(res[0])
        refined_offset = float(res[1])

        # Ensure refined slope didn't deviate into unrealistic value
        if not (self.min_speed <= refined_slope <= self.max_speed):
            refined_slope = init_slope
            refined_offset = init_offset

        # Recalculate inliers with refined parameters
        new_mapped = refined_slope * sub_mids + refined_offset
        idx = np.searchsorted(audio_mids, new_mapped)
        idx_clamped = np.clip(idx, 0, len(audio_mids) - 1)
        idx_prev = np.clip(idx - 1, 0, len(audio_mids) - 1)
        dist1 = np.abs(audio_mids[idx_clamped] - new_mapped)
        dist2 = np.abs(audio_mids[idx_prev] - new_mapped)
        new_min_dist = np.minimum(dist1, dist2)
        new_inliers_mask = new_min_dist <= self.inlier_tolerance

        return refined_slope, refined_offset, new_inliers_mask

    def _compute_inliers_mask(
        self,
        sub_mids: np.ndarray,
        audio_mids: np.ndarray,
        slope: float,
        offset: float,
    ) -> np.ndarray:
        """Computes boolean inlier mask for a given slope and offset."""
        if len(sub_mids) == 0 or len(audio_mids) == 0:
            return np.array([], dtype=bool)
        mapped = slope * sub_mids + offset
        idx = np.searchsorted(audio_mids, mapped)
        c0 = np.clip(idx, 0, len(audio_mids) - 1)
        c1 = np.clip(idx - 1, 0, len(audio_mids) - 1)
        d0 = np.abs(audio_mids[c0] - mapped)
        d1 = np.abs(audio_mids[c1] - mapped)
        min_dist = np.minimum(d0, d1)
        return min_dist <= self.inlier_tolerance

    def _split_cuts_recursive(
        self,
        subtitles: List[SubtitleItem],
        sub_mids: np.ndarray,
        audio_mids: np.ndarray,
        base_slope: float,
        current_offset: float,
        current_inliers_mask: Optional[np.ndarray] = None,
        depth: int = 0,
        max_depth: int = 3,
    ) -> List[AlignmentSegment]:
        """
        Recursively splits subtitles into segments if discontinuities (commercial cuts) exist.
        Supports multiple cuts across the video up to max_depth levels.
        """
        total_subs = len(subtitles)
        if total_subs == 0:
            return []

        if current_inliers_mask is None:
            current_inliers_mask = self._compute_inliers_mask(
                sub_mids, audio_mids, base_slope, current_offset
            )

        inliers_count = int(np.sum(current_inliers_mask))
        confidence = inliers_count / max(1, total_subs)

        # Base case 1: Not enough subtitles for splitting or max depth reached
        if total_subs < 20 or depth >= max_depth:
            return [
                AlignmentSegment(
                    sub_start=subtitles[0].start,
                    sub_end=subtitles[-1].end,
                    slope=base_slope,
                    offset=current_offset,
                    inliers_count=inliers_count,
                    confidence=confidence,
                )
            ]

        # Base case 2: 85%+ inliers match current line, no piecewise cut needed
        outlier_indices = np.where(~current_inliers_mask)[0]
        if len(outlier_indices) < total_subs * 0.15:
            return [
                AlignmentSegment(
                    sub_start=subtitles[0].start,
                    sub_end=subtitles[-1].end,
                    slope=base_slope,
                    offset=current_offset,
                    inliers_count=inliers_count,
                    confidence=confidence,
                )
            ]

        # Check if outliers share a secondary offset
        outlier_sub_mids = sub_mids[outlier_indices]
        scaled_outliers = base_slope * outlier_sub_mids
        sec_offset, sec_score = self._find_best_offset_for_speed(
            scaled_outliers, audio_mids
        )

        if sec_score > len(outlier_indices) * 0.35 and abs(sec_offset - current_offset) > 1.0:
            # Find distances to audio for both candidate offsets
            def get_mapped_min_dist(offset: float) -> np.ndarray:
                mapped = base_slope * sub_mids + offset
                idx = np.searchsorted(audio_mids, mapped)
                c0 = np.clip(idx, 0, len(audio_mids) - 1)
                c1 = np.clip(idx - 1, 0, len(audio_mids) - 1)
                d0 = np.abs(audio_mids[c0] - mapped)
                d1 = np.abs(audio_mids[c1] - mapped)
                return np.minimum(d0, d1)

            dist_base = get_mapped_min_dist(current_offset)
            dist_sec = get_mapped_min_dist(sec_offset)

            sec_is_better = (dist_sec < dist_base).astype(int)
            cum_sec = np.cumsum(sec_is_better)
            total_sec_better = cum_sec[-1]

            best_k = -1
            min_errors = total_subs
            first_is_base = True

            min_margin = max(5, int(total_subs * 0.10))
            for k in range(min_margin, total_subs - min_margin):
                err_a = cum_sec[k - 1] + ((total_subs - k) - (total_sec_better - cum_sec[k - 1]))
                err_b = (k - cum_sec[k - 1]) + (total_sec_better - cum_sec[k - 1])

                if err_a < min_errors:
                    min_errors = err_a
                    best_k = k
                    first_is_base = True
                if err_b < min_errors:
                    min_errors = err_b
                    best_k = k
                    first_is_base = False

            if best_k > 0 and (total_subs - min_errors) >= int(total_subs * 0.60):
                offset_first = current_offset if first_is_base else sec_offset
                offset_second = sec_offset if first_is_base else current_offset

                # Recursively process left and right slices to discover further cuts
                left_segs = self._split_cuts_recursive(
                    subtitles[:best_k],
                    sub_mids[:best_k],
                    audio_mids,
                    base_slope,
                    offset_first,
                    depth=depth + 1,
                    max_depth=max_depth,
                )
                right_segs = self._split_cuts_recursive(
                    subtitles[best_k:],
                    sub_mids[best_k:],
                    audio_mids,
                    base_slope,
                    offset_second,
                    depth=depth + 1,
                    max_depth=max_depth,
                )
                return left_segs + right_segs

        return [
            AlignmentSegment(
                sub_start=subtitles[0].start,
                sub_end=subtitles[-1].end,
                slope=base_slope,
                offset=current_offset,
                inliers_count=inliers_count,
                confidence=confidence,
            )
        ]

    def _detect_piecewise_cuts(
        self,
        subtitles: List[SubtitleItem],
        sub_mids: np.ndarray,
        audio_mids: np.ndarray,
        base_slope: float,
        base_offset: float,
        inliers_mask: np.ndarray,
    ) -> List[AlignmentSegment]:
        """
        Detects discontinuities (e.g. TV commercial breaks or deleted scenes).
        Recursively splits non-matching chunks into piecewise segments.
        """
        return self._split_cuts_recursive(
            subtitles=subtitles,
            sub_mids=sub_mids,
            audio_mids=audio_mids,
            base_slope=base_slope,
            current_offset=base_offset,
            current_inliers_mask=inliers_mask,
            depth=0,
            max_depth=3,
        )

    def _compute_alignment_confidence(
        self,
        subtitles: List[SubtitleItem],
        speech_segments: List[SpeechSegment],
        segments: List[AlignmentSegment],
    ) -> float:
        """
        Calculates temporal overlap percentage between aligned subtitles and speech segments.
        """
        if not subtitles or not speech_segments or not segments:
            return 0.0

        total_sub_duration = 0.0
        total_overlap_duration = 0.0

        for sub in subtitles:
            total_sub_duration += sub.duration
            # Find applicable segment
            seg = segments[0]
            for s in segments:
                if s.sub_start <= sub.start <= s.sub_end:
                    seg = s
                    break

            mapped_start = seg.apply(sub.start)
            mapped_end = seg.apply(sub.end)

            # Find overlapping speech segments
            for speech in speech_segments:
                if speech.end < mapped_start:
                    continue
                if speech.start > mapped_end:
                    break
                overlap = max(0.0, min(mapped_end, speech.end) - max(mapped_start, speech.start))
                total_overlap_duration += overlap

        if total_sub_duration == 0:
            return 0.0

        # Ratio of overlapping speech duration to total subtitle duration
        ratio = total_overlap_duration / total_sub_duration
        return min(1.0, max(0.0, ratio))
