import re
from pathlib import Path
from typing import List, Optional, Tuple, Callable
import charset_normalizer
from .models import SubtitleItem


def detect_file_encoding(file_path: Path) -> str:
    """Detect text encoding of a subtitle file with fallback support."""
    try:
        raw = file_path.read_bytes()
        # Check for UTF-8 BOM
        if raw.startswith(b'\xef\xbb\xbf'):
            return 'utf-8-sig'
        if raw.startswith(b'\xff\xfe'):
            return 'utf-16-le'
        if raw.startswith(b'\xfe\xff'):
            return 'utf-16-be'

        result = charset_normalizer.detect(raw)
        encoding = result.get("encoding")
        if encoding:
            return encoding
    except Exception:
        pass
    
    # Common fallbacks for Turkish subtitles
    for enc in ['utf-8', 'cp1254', 'iso-8859-9', 'latin-1']:
        try:
            raw.decode(enc)
            return enc
        except Exception:
            continue
            
    return 'utf-8'


def parse_timestamp(ts_str: str) -> Optional[float]:
    """
    Parse timestamp string to seconds.
    Supports formats:
    - 01:23:45,678
    - 01:23:45.678
    - 23:45,678
    - 23:45.678
    """
    ts_str = ts_str.strip().replace(',', '.')
    parts = ts_str.split(':')
    try:
        if len(parts) == 3:
            hours = float(parts[0])
            minutes = float(parts[1])
            seconds = float(parts[2])
            return hours * 3600.0 + minutes * 60.0 + seconds
        elif len(parts) == 2:
            minutes = float(parts[0])
            seconds = float(parts[1])
            return minutes * 60.0 + seconds
        elif len(parts) == 1:
            return float(parts[0])
    except ValueError:
        return None
    return None


def format_srt_timestamp(seconds: float) -> str:
    """Format seconds into standard SRT timestamp HH:MM:SS,mmm."""
    if seconds < 0:
        seconds = 0.0
    hours = int(seconds // 3600)
    remainder = seconds % 3600
    minutes = int(remainder // 60)
    secs = int(remainder % 60)
    fraction = seconds - int(seconds)
    millis = int(round(fraction * 1000))
    if millis >= 1000:
        secs += 1
        millis -= 1000
    if secs >= 60:
        minutes += 1
        secs -= 60
    if minutes >= 60:
        hours += 1
        minutes -= 60
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


_TIMESTAMP_LINE_REGEX = re.compile(
    r"(\d{1,2}:\d{2}:\d{2}(?:[,\.]\d{1,3})?|\d{1,2}:\d{2}(?:[,\.]\d{1,3})?)\s*-->\s*(\d{1,2}:\d{2}:\d{2}(?:[,\.]\d{1,3})?|\d{1,2}:\d{2}(?:[,\.]\d{1,3})?)"
)


def load_subtitles(file_path: Path) -> List[SubtitleItem]:
    """
    Robustly loads subtitles from an SRT or VTT file.
    Handles encoding issues, malformed blocks, and corrupted numbering.
    """
    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"Subtitle file not found: {file_path}")

    encoding = detect_file_encoding(file_path)
    content = file_path.read_text(encoding=encoding, errors='replace')
    
    # Normalize line endings
    content = content.replace('\r\n', '\n').replace('\r', '\n')
    lines = content.split('\n')

    items: List[SubtitleItem] = []
    current_index = 1
    i = 0
    total_lines = len(lines)

    while i < total_lines:
        line = lines[i].strip()
        
        # Skip webvtt headers or blank lines
        if not line or line.startswith('WEBVTT') or line.startswith('NOTE') or line.startswith('STYLE'):
            i += 1
            continue

        # Check if line is timestamp line
        match = _TIMESTAMP_LINE_REGEX.search(line)
        
        # If not, it might be an index number line preceding a timestamp line
        if not match and i + 1 < total_lines:
            next_line = lines[i + 1].strip()
            match = _TIMESTAMP_LINE_REGEX.search(next_line)
            if match:
                i += 1  # Advance to the timestamp line

        if match:
            start_str, end_str = match.groups()
            start_sec = parse_timestamp(start_str)
            end_sec = parse_timestamp(end_str)
            
            if start_sec is not None and end_sec is not None:
                text_lines = []
                i += 1
                while i < total_lines:
                    text_line = lines[i]
                    # Check if next block starts or blank line
                    if not text_line.strip():
                        # Empty line signals end of text block
                        break
                    if _TIMESTAMP_LINE_REGEX.search(text_line):
                        # Next timestamp encountered without blank line
                        i -= 1
                        break
                    # Also check if it's an index number line followed by timestamp
                    if text_line.strip().isdigit() and i + 1 < total_lines and _TIMESTAMP_LINE_REGEX.search(lines[i + 1]):
                        break
                    text_lines.append(text_line)
                    i += 1

                text = "\n".join(text_lines).strip()
                if text:
                    items.append(SubtitleItem(
                        index=current_index,
                        start=start_sec,
                        end=end_sec,
                        text=text
                    ))
                    current_index += 1
        i += 1

    return items


def save_srt(items: List[SubtitleItem], output_path: Path, encoding: str = 'utf-8') -> None:
    """Save subtitle items as clean UTF-8 SRT file."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Sort by start time and re-index
    sorted_items = sorted(items, key=lambda x: x.start)
    
    blocks = []
    for idx, item in enumerate(sorted_items, start=1):
        start_str = format_srt_timestamp(item.start)
        end_str = format_srt_timestamp(item.end)
        block = f"{idx}\n{start_str} --> {end_str}\n{item.text}\n"
        blocks.append(block)

    output_path.write_text("\n".join(blocks), encoding=encoding)
