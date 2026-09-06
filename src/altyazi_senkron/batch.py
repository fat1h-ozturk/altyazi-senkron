import re
from pathlib import Path
from typing import List, Tuple, Optional, Set

VIDEO_EXTENSIONS: Set[str] = {
    ".mkv", ".mp4", ".avi", ".mov", ".m4v", ".webm", ".ts", ".flv"
}

_EPISODE_REGEXES = [
    # Multi-episode: S01E01-E02, S01E01-02, S01E01E02
    re.compile(r"(?<![a-zA-Z0-9])[sS](\d{1,2})[eE](\d{1,2})(?:[-_.]?[eE]|[-_.])(\d{1,2})(?![a-zA-Z0-9])"),
    # Multi-episode: 1x01-02, 01x01-02
    re.compile(r"(?<![a-zA-Z0-9])(\d{1,2})[xX](\d{1,2})[-_.](\d{1,2})(?![a-zA-Z0-9])"),
    # Single episode: S01E02, s1e2
    re.compile(r"(?<![a-zA-Z0-9])[sS](\d{1,2})[eE](\d{1,2})(?![a-zA-Z0-9])"),
    # Single episode: 1x02, 01x02
    re.compile(r"(?<![a-zA-Z0-9])(\d{1,2})[xX](\d{1,2})(?![a-zA-Z0-9])"),
    # Episode number: Ep02, EP.02, ep2
    re.compile(r"(?<![a-zA-Z0-9])[eE][pP]\.?\s*(\d{1,3})(?![a-zA-Z0-9])"),
    # Episode number: E02, e02
    re.compile(r"(?<![a-zA-Z0-9])[eE](\d{1,3})(?![a-zA-Z0-9])"),
]


def extract_episode_id(filename: str) -> Optional[str]:
    """Extracts a normalized episode identifier like 's01e02', 's01e01-e02' or 'ep02'."""
    for regex in _EPISODE_REGEXES:
        match = regex.search(filename)
        if match:
            groups = match.groups()
            if len(groups) == 3:
                s, e1, e2 = int(groups[0]), int(groups[1]), int(groups[2])
                return f"s{s:02d}e{e1:02d}-e{e2:02d}"
            elif len(groups) == 2:
                s, e = int(groups[0]), int(groups[1])
                return f"s{s:02d}e{e:02d}"
            elif len(groups) == 1:
                return f"ep{int(groups[0]):02d}"
    return None


def get_synced_output_path(video_path: Path, subtitle_path: Path) -> Path:
    """
    Generates the output path ending with .tr[synced].srt
    """
    # Use the video file stem as the base name
    base_name = video_path.stem
    # Strip trailing ".tr" (case-insensitive) to avoid .tr.tr[synced].srt
    if base_name.lower().endswith(".tr"):
        base_name = base_name[:-3]
    # Also strip any trailing dots left after the removal above
    base_name = base_name.rstrip(".")

    return video_path.parent / f"{base_name}.tr[synced].srt"


def find_video_subtitle_pairs(
    directory: Path,
    recursive: bool = False
) -> List[Tuple[Path, Path, Path]]:
    """
    Scans directory and pairs each video file with its matching Turkish subtitle file.
    
    Priority order for matching:
    1. <video_stem>.tr.srt
    2. <video_stem>.srt
    3. Any .tr.srt matching episode identifier (e.g. S01E02)
    4. Any .srt matching episode identifier
    5. Subtitle containing video stem prefix
    
    Returns:
        List of (video_path, target_subtitle_path, output_path)
    """
    directory = Path(directory)
    if not directory.exists() or not directory.is_dir():
        return []

    # Collect video and candidate subtitle files
    if recursive:
        all_files = list(directory.rglob("*"))
    else:
        all_files = list(directory.glob("*"))

    video_files = [
        f for f in all_files
        if f.is_file() and f.suffix.lower() in VIDEO_EXTENSIONS
    ]

    # Ignore files that are already output/synced
    candidate_subtitles = [
        f for f in all_files
        if f.is_file() and f.suffix.lower() == ".srt" and "[synced]" not in f.name.lower()
    ]

    pairs: List[Tuple[Path, Path, Path]] = []
    used_subtitles: Set[Path] = set()

    # Sort videos alphabetically
    video_files.sort(key=lambda x: str(x).lower())

    for video in video_files:
        v_stem = video.stem.lower()
        v_dir = video.parent
        v_ep = extract_episode_id(video.name)

        matched_sub: Optional[Path] = None

        # Filter candidate subtitles in the same folder or overall
        subs_in_dir = [
            s for s in candidate_subtitles
            if s.parent == v_dir and s not in used_subtitles
        ]

        # 1. Exact match with .tr.srt
        for s in subs_in_dir:
            if s.name.lower() == f"{v_stem}.tr.srt":
                matched_sub = s
                break

        # 2. Exact match with .srt
        if not matched_sub:
            for s in subs_in_dir:
                if s.stem.lower() == v_stem:
                    matched_sub = s
                    break

        # 3. Episode ID match with .tr.srt
        if not matched_sub and v_ep:
            for s in subs_in_dir:
                s_name = s.name.lower()
                if ".tr." in s_name or s_name.endswith(".tr.srt"):
                    if extract_episode_id(s.name) == v_ep:
                        matched_sub = s
                        break

        # 4. Episode ID match with any .srt
        if not matched_sub and v_ep:
            for s in subs_in_dir:
                if extract_episode_id(s.name) == v_ep:
                    matched_sub = s
                    break

        # 5. Subtitle containing video stem prefix and '.tr.'
        if not matched_sub:
            for s in subs_in_dir:
                s_name = s.name.lower()
                if ".tr." in s_name and (v_stem in s_name or s.stem.lower() in v_stem):
                    matched_sub = s
                    break

        if matched_sub:
            output_path = get_synced_output_path(video, matched_sub)
            pairs.append((video, matched_sub, output_path))
            used_subtitles.add(matched_sub)

    return pairs
