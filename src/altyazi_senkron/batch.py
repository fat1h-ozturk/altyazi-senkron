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


def extract_subtitle_lang_tag(subtitle_path: Path) -> Optional[str]:
    """
    Extracts language code tag from subtitle filename if present.
    Examples:
        'Series.S01E01.en.srt'  -> 'en'
        'Series.S01E01.eng.srt' -> 'eng'
        'Series.S01E01.tr.srt'  -> 'tr'
        'Movie.srt'             -> None
    """
    stem = subtitle_path.stem.lower()
    parts = stem.split(".")
    if len(parts) >= 2:
        candidate = parts[-1]
        if re.match(r"^[a-z]{2,3}$", candidate):
            return candidate
    return None


def get_synced_output_path(
    video_path: Path,
    subtitle_path: Path,
    sub_lang: Optional[str] = None,
) -> Path:
    """
    Generates the output path ending with .<lang>[synced].srt (e.g. .en[synced].srt, .tr[synced].srt)
    """
    base_name = video_path.stem

    # Determine which language tag to use
    if sub_lang and sub_lang.lower() != "all":
        tag = sub_lang.lower()
    else:
        detected_tag = extract_subtitle_lang_tag(subtitle_path)
        tag = detected_tag if detected_tag else "tr"

    # Strip existing language suffixes from base_name to avoid Dizi.S01E01.en.en[synced].srt
    for possible_tag in [tag, "tr", "tur", "en", "eng", "de", "ger", "fr", "fra", "es", "spa", "it", "ita"]:
        if base_name.lower().endswith(f".{possible_tag}"):
            base_name = base_name[: -(len(possible_tag) + 1)]

    base_name = base_name.rstrip(".")
    return video_path.parent / f"{base_name}.{tag}[synced].srt"


def find_video_subtitle_pairs(
    directory: Path,
    sub_lang: str = "tr",
    recursive: bool = False,
) -> List[Tuple[Path, Path, Path]]:
    """
    Scans directory and pairs each video file with its matching subtitle file for the requested language.
    
    Args:
        directory: Directory to search
        sub_lang: Target subtitle language code (e.g. 'tr', 'en', 'de', or 'all'). Default 'tr'.
        recursive: Whether to search subdirectories recursively.

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

    lang_lower = sub_lang.lower() if sub_lang else "tr"
    if lang_lower == "en":
        target_aliases = ["en", "eng"]
    elif lang_lower == "tr":
        target_aliases = ["tr", "tur"]
    elif lang_lower == "all":
        target_aliases = []
    else:
        target_aliases = [lang_lower]

    for video in video_files:
        v_stem = video.stem.lower()
        v_dir = video.parent
        v_ep = extract_episode_id(video.name)

        matched_sub: Optional[Path] = None

        subs_in_dir = [
            s for s in candidate_subtitles
            if s.parent == v_dir and s not in used_subtitles
        ]

        # 1. Exact match with .{alias}.srt (e.g. Video.en.srt)
        if target_aliases:
            for s in subs_in_dir:
                for alias in target_aliases:
                    if s.name.lower() == f"{v_stem}.{alias}.srt":
                        matched_sub = s
                        break
                if matched_sub:
                    break

        # 2. Exact match with .srt (e.g. Video.srt)
        if not matched_sub:
            for s in subs_in_dir:
                if s.stem.lower() == v_stem:
                    matched_sub = s
                    break

        # 3. Episode ID match with matching language tag (e.g. Series.S01E01.en.srt)
        if not matched_sub and v_ep:
            for s in subs_in_dir:
                s_ep = extract_episode_id(s.name)
                if s_ep == v_ep:
                    s_tag = extract_subtitle_lang_tag(s)
                    if not target_aliases or (s_tag and s_tag in target_aliases):
                        matched_sub = s
                        break

        # 4. Episode ID match with any .srt (only if no conflicting different language tag)
        if not matched_sub and v_ep:
            for s in subs_in_dir:
                if extract_episode_id(s.name) == v_ep:
                    s_tag = extract_subtitle_lang_tag(s)
                    if target_aliases and s_tag and s_tag not in target_aliases:
                        continue
                    matched_sub = s
                    break

        # 5. Subtitle containing video stem prefix and language alias
        if not matched_sub and target_aliases:
            for s in subs_in_dir:
                s_name = s.name.lower()
                for alias in target_aliases:
                    if f".{alias}." in s_name and (v_stem in s_name or s.stem.lower() in v_stem):
                        matched_sub = s
                        break
                if matched_sub:
                    break

        # 6. Fallback: subtitle containing video stem
        if not matched_sub:
            for s in subs_in_dir:
                s_name = s.name.lower()
                if v_stem in s_name or s.stem.lower() in v_stem:
                    s_tag = extract_subtitle_lang_tag(s)
                    if target_aliases and s_tag and s_tag not in target_aliases:
                        continue
                    matched_sub = s
                    break

        if matched_sub:
            output_path = get_synced_output_path(video, matched_sub, sub_lang=sub_lang)
            pairs.append((video, matched_sub, output_path))
            used_subtitles.add(matched_sub)

    return pairs
