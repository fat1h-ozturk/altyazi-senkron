import json
import subprocess
import shutil
import tempfile
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple


def check_ffmpeg() -> bool:
    """Verify that ffmpeg and ffprobe are available in system PATH."""
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def get_media_info(media_path: Path) -> Dict[str, Any]:
    """Inspect media file streams, duration, and metadata using ffprobe."""
    if not check_ffmpeg():
        raise RuntimeError("ffmpeg and ffprobe must be installed on your system.")

    media_path = Path(media_path)
    if not media_path.exists():
        raise FileNotFoundError(f"Media file not found: {media_path}")

    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_format",
        "-show_streams",
        "-of", "json",
        str(media_path)
    ]

    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed to inspect {media_path}: {result.stderr}")

    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return {}


def get_embedded_subtitles(media_path: Path) -> List[Dict[str, Any]]:
    """List all embedded subtitle tracks found in the media file."""
    info = get_media_info(media_path)
    subtitles = []
    
    for stream in info.get("streams", []):
        if stream.get("codec_type") == "subtitle":
            tags = stream.get("tags", {})
            subtitles.append({
                "index": stream.get("index"),
                "codec": stream.get("codec_name"),
                "language": tags.get("language", "und"),
                "title": tags.get("title", ""),
                "default": stream.get("disposition", {}).get("default", 0) == 1,
            })
    return subtitles


def extract_embedded_subtitle(media_path: Path, stream_index: int, output_srt: Path) -> Path:
    """Extract an embedded subtitle track to an external SRT file."""
    output_srt = Path(output_srt)
    output_srt.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        "ffmpeg",
        "-y",
        "-v", "error",
        "-i", str(media_path),
        "-map", f"0:{stream_index}",
        "-c:s", "srt",
        str(output_srt)
    ]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Failed to extract embedded subtitle: {result.stderr}")
    return output_srt


def extract_audio_wav(
    media_path: Path,
    output_wav: Optional[Path] = None,
    sample_rate: int = 16000,
    start_time: Optional[float] = None,
    duration: Optional[float] = None
) -> Path:
    """
    Extracts 16kHz mono 16-bit PCM audio from video file to a WAV file.
    Ideal for Whisper ASR and Silero VAD processing.
    """
    if not check_ffmpeg():
        raise RuntimeError("ffmpeg is required to extract audio from video.")

    media_path = Path(media_path)
    if not media_path.exists():
        raise FileNotFoundError(f"Media file not found: {media_path}")

    if output_wav is None:
        temp_dir = tempfile.gettempdir()
        output_wav = Path(temp_dir) / f"altyazi_senkron_{media_path.stem}.wav"

    output_wav.parent.mkdir(parents=True, exist_ok=True)

    cmd = ["ffmpeg", "-y", "-v", "error"]
    
    if start_time is not None:
        cmd.extend(["-ss", str(start_time)])
    if duration is not None:
        cmd.extend(["-t", str(duration)])

    cmd.extend([
        "-i", str(media_path),
        "-vn",                    # Strip video
        "-acodec", "pcm_s16le",   # Standard uncompressed 16-bit PCM
        "-ac", "1",               # Mono channel
        "-ar", str(sample_rate),  # Target sample rate
        str(output_wav)
    ])

    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg audio extraction failed: {result.stderr}")

    return output_wav
