from pathlib import Path
from typing import List, Optional, Callable
from .models import SpeechSegment


class SpeechDetector:
    """
    Detects human speech segments from audio using Faster-Whisper and Silero VAD.
    Produces accurate speech intervals, eliminating background music and sound effects.
    """

    def __init__(
        self,
        model_size: str = "base",
        device: str = "cpu",
        compute_type: str = "int8",
        cpu_threads: int = 4,
    ):
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self.cpu_threads = cpu_threads
        self._model = None

    def _get_model(self):
        if self._model is None:
            from faster_whisper import WhisperModel
            self._model = WhisperModel(
                self.model_size,
                device=self.device,
                compute_type=self.compute_type,
                cpu_threads=self.cpu_threads
            )
        return self._model

    def detect_segments(
        self,
        audio_path: Path,
        language: Optional[str] = None,
        progress_callback: Optional[Callable[[float, float], None]] = None,
        no_speech_prob_threshold: float = 0.6,
        vad_min_silence_ms: int = 300,
    ) -> List[SpeechSegment]:
        """
        Transcribe and extract speech timestamps from audio.
        Uses integrated Silero VAD filter to discard non-speech noise.

        Args:
            no_speech_prob_threshold: Segments with no_speech_prob above this
                value are discarded (treats them as music/noise). Default 0.6.
            vad_min_silence_ms: Minimum silence duration (ms) between speech
                segments. Lower values keep more short pauses as separate
                segments. Default 300ms.
        """
        model = self._get_model()

        segments, info = model.transcribe(
            str(audio_path),
            language=language,
            vad_filter=True,
            vad_parameters=dict(
                min_silence_duration_ms=vad_min_silence_ms,
                speech_pad_ms=150,
            ),
            word_timestamps=False,
        )

        total_duration = info.duration if info and info.duration else 0.0
        results: List[SpeechSegment] = []

        for seg in segments:
            # Drop segments that Whisper itself considers non-speech
            # (background music, ambient sounds, etc.)
            nsp = seg.no_speech_prob if hasattr(seg, 'no_speech_prob') else 0.0
            if nsp >= no_speech_prob_threshold:
                if progress_callback and total_duration > 0:
                    progress_callback(seg.end, total_duration)
                continue

            results.append(
                SpeechSegment(
                    start=seg.start,
                    end=seg.end,
                    text=seg.text.strip(),
                    confidence=1.0 - nsp,
                )
            )
            if progress_callback and total_duration > 0:
                progress_callback(seg.end, total_duration)

        return results
