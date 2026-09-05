from dataclasses import dataclass, field
from typing import List, Tuple, Optional


@dataclass
class SubtitleItem:
    """Represents a single subtitle entry."""
    index: int
    start: float  # In seconds
    end: float    # In seconds
    text: str

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)

    @property
    def midpoint(self) -> float:
        return (self.start + self.end) / 2.0


@dataclass
class SpeechSegment:
    """Represents a segment of detected human speech."""
    start: float  # In seconds
    end: float    # In seconds
    text: str = ""
    confidence: float = 1.0

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)

    @property
    def midpoint(self) -> float:
        return (self.start + self.end) / 2.0


@dataclass
class AlignmentSegment:
    """Represents linear synchronization parameters for a specific time range."""
    sub_start: float
    sub_end: float
    slope: float      # Speed multiplier (alpha)
    offset: float     # Shift in seconds (beta: t_video = slope * t_sub + offset)
    inliers_count: int = 0
    confidence: float = 0.0

    def apply(self, t: float) -> float:
        return self.slope * t + self.offset


@dataclass
class AlignmentResult:
    """Final synchronization result containing parameters and diagnostic metrics."""
    segments: List[AlignmentSegment] = field(default_factory=list)
    overall_confidence: float = 0.0
    detected_speed: float = 1.0
    detected_offset: float = 0.0
    is_piecewise: bool = False
    inliers_ratio: float = 0.0
    warnings: List[str] = field(default_factory=list)
