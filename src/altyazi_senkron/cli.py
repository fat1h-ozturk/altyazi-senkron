import os
import sys
import warnings
import logging
from pathlib import Path
from typing import Optional, List, Tuple, Dict, Any
import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn
from rich.markup import escape

# Suppress HuggingFace Hub unauthenticated warning and general logging noise
os.environ["HF_HUB_DISABLE_IMPLICIT_TOKEN"] = "1"
os.environ["HF_HUB_ENABLE_HF_TRANSFER"] = "0"
warnings.filterwarnings("ignore", message=".*unauthenticated requests to the HF Hub.*")
warnings.filterwarnings("ignore", category=UserWarning, module="huggingface_hub.*")
logging.getLogger("huggingface_hub").setLevel(logging.ERROR)

from .subtitle import load_subtitles, save_srt
from .audio import (
    check_ffmpeg,
    extract_audio_wav,
    get_embedded_subtitles,
    extract_embedded_subtitle,
)
from .detector import SpeechDetector
from .matcher import SubtitleMatcher
from .snapper import SubtitleSnapper
from .validator import AlignmentValidator
from .models import SpeechSegment, AlignmentResult
from .batch import find_video_subtitle_pairs

app = typer.Typer(
    name="altyazi-senkron",
    help="AI destekli, yüksek hassasiyetli film ve dizi altyazı senkronizasyon aracı.",
    add_completion=False,
)
console = Console()


def _is_subtitle_file(path: Path) -> bool:
    return path.suffix.lower() in [".srt", ".vtt", ".ass", ".ssa", ".sub"]


def process_single_sync(
    reference: Path,
    target_sub: Path,
    output: Path,
    detector: Optional[SpeechDetector] = None,
    model: str = "base",
    device: str = "auto",
    no_snap: bool = False,
    use_embedded: bool = False,
    threads: int = 4,
    show_details: bool = True,
    progress_prefix: str = "",
    language: Optional[str] = None,
    vad_min_silence: int = 300,
) -> Tuple[bool, Optional[AlignmentResult], Optional[Dict[str, Any]], str]:
    """
    Executes synchronization for a single video/subtitle pair.
    Returns: (success, AlignmentResult, eval_metrics, error_message)
    """
    temp_files = []
    try:
        # 1. Altyazıyı Yükle
        try:
            target_items = load_subtitles(target_sub)
        except Exception as e:
            return False, None, None, f"Hedef altyazı okunamadı: {e}"

        if not target_items:
            return False, None, None, "Hedef altyazı dosyası boş veya geçersiz."

        if show_details:
            console.print(f"[green]✔[/green] Hedef altyazı okundu: [bold]{len(target_items)}[/bold] satır.")

        speech_segments = []

        # Senaryo A: Referans olarak altyazı verilmişse (Sub-to-Sub)
        if _is_subtitle_file(reference):
            if show_details:
                console.print("[yellow]ℹ[/yellow] Referans altyazı kullanılıyor (Sub-to-Sub).")
            ref_items = load_subtitles(reference)
            speech_segments = [
                SpeechSegment(start=item.start, end=item.end, text=item.text)
                for item in ref_items
            ]
        else:
            # Senaryo B: Video veya ses dosyası
            if not check_ffmpeg():
                return False, None, None, "Sistemde 'ffmpeg' bulunamadı."

            # Gömülü altyazı kontrolü
            if use_embedded:
                embedded_subs = get_embedded_subtitles(reference)
                if embedded_subs:
                    ref_track = embedded_subs[0]['index']
                    if show_details:
                        console.print(f"[green]✔[/green] Gömülü altyazı #{ref_track} referans olarak çekiliyor...")
                    extracted_sub = reference.parent / f"{reference.stem}_temp_ref.srt"
                    temp_files.append(extracted_sub)
                    extract_embedded_subtitle(reference, ref_track, extracted_sub)
                    ref_items = load_subtitles(extracted_sub)
                    speech_segments = [
                        SpeechSegment(start=item.start, end=item.end, text=item.text)
                        for item in ref_items
                    ]

            # Gömülü altyazı yoksa veya kullanılmıyorsa ASR ile devam et
            if not speech_segments:
                # 2. Sesi Çıkar — wav_path'i önceden temp_files'a ekle ki FFmpeg
                # hata verse dahi finally bloğu geçici dosyayı temizleyebilsin.
                import tempfile as _tmpmod
                _tmp_wav = Path(_tmpmod.gettempdir()) / f"altyazi_senkron_{reference.stem}.wav"
                temp_files.append(_tmp_wav)
                status_msg = f"{progress_prefix}16kHz ses ayıklanıyor..." if progress_prefix else "16kHz ses ayıklanıyor (FFmpeg)..."
                with console.status(f"[bold green]{status_msg}[/bold green]"):
                    wav_path = extract_audio_wav(reference, output_wav=_tmp_wav)

                # 3. Konuşma Tespiti (Whisper + Silero VAD)
                if detector is None:
                    compute_device = "cuda" if device == "cuda" else "cpu"
                    detector = SpeechDetector(
                        model_size=model,
                        device=compute_device,
                        cpu_threads=threads,
                    )

                task_desc = f"[cyan]{progress_prefix}Ses & Konuşma Analizi ({model})...[/cyan]"
                with Progress(
                    SpinnerColumn(),
                    TextColumn("[progress.description]{task.description}"),
                    BarColumn(),
                    TimeElapsedColumn(),
                    console=console,
                ) as progress:
                    task = progress.add_task(task_desc, total=100.0)

                    def update_progress(current_sec: float, total_sec: float):
                        if total_sec > 0:
                            pct = min(100.0, (current_sec / total_sec) * 100.0)
                            progress.update(task, completed=pct)

                    speech_segments = detector.detect_segments(
                        wav_path,
                        language=language,
                        vad_min_silence_ms=vad_min_silence,
                        progress_callback=update_progress,
                    )
                    progress.update(task, completed=100.0)

                if show_details:
                    console.print(f"[green]✔[/green] [bold]{len(speech_segments)}[/bold] konuşma aralığı tespit edildi.")

        if not speech_segments:
            return False, None, None, "Seste konuşma tespit edilemedi veya referans altyazı boş."

        # 4. Eşleştirme Motoru (RANSAC & Rhythm Fingerprinting)
        with console.status("[bold green]RANSAC ve konuşma ritim eşleştirmesi yapılıyor...[/bold green]"):
            matcher = SubtitleMatcher()
            result = matcher.align(target_items, speech_segments)

        # 5. Snapping (Milisaniyelik Konuşma Kenetleme)
        if not no_snap:
            with console.status("[bold green]Milisaniyelik konuşma sınırlarına kenetleniyor...[/bold green]"):
                snapper = SubtitleSnapper()
                final_subtitles = snapper.snap(target_items, speech_segments, result.segments)
        else:
            final_subtitles = []
            for sub in target_items:
                seg = result.segments[0]
                for s in result.segments:
                    if s.sub_start <= sub.start <= s.sub_end:
                        seg = s
                        break
                final_subtitles.append(
                    target_items.__class__(
                        index=sub.index,
                        start=seg.apply(sub.start),
                        end=seg.apply(sub.end),
                        text=sub.text,
                    )
                )

        # 6. Doğrulama
        eval_metrics = AlignmentValidator.evaluate(final_subtitles, speech_segments, result)

        # 7. Kaydet
        save_srt(final_subtitles, output)
        return True, result, eval_metrics, ""

    except Exception as e:
        return False, None, None, str(e)
    finally:
        for f in temp_files:
            try:
                if f.exists():
                    f.unlink()
            except Exception:
                pass


@app.command(name="sync")
def sync_command(
    reference: Path = typer.Argument(
        ...,
        help="Video dosyası, ses dosyası veya referans altyazı (.mkv, .mp4, .wav, .srt, vb.)",
        exists=True,
    ),
    target_sub: Path = typer.Argument(
        ...,
        help="Senkronlanacak hedef altyazı dosyası (.srt, .vtt)",
        exists=True,
    ),
    output: Optional[Path] = typer.Option(
        None,
        "-o", "--output",
        help="Çıktı altyazı dosya yolu. Varsayılan: <hedef>_synced.srt",
    ),
    model: str = typer.Option(
        "base",
        "-m", "--model",
        help="Whisper model boyutu: tiny, base, small, medium (Varsayılan: base)",
    ),
    device: str = typer.Option(
        "auto",
        "-d", "--device",
        help="Hesaplama birimi: cpu, cuda veya auto",
    ),
    no_snap: bool = typer.Option(
        False,
        "--no-snap",
        help="Milisaniyelik konuşma başlangıç/bitiş kenetlemesini (snapping) devre dışı bırak.",
    ),
    use_embedded: bool = typer.Option(
        False,
        "--use-embedded",
        help="Videoda gömülü altyazı varsa ses yerine doğrudan gömülü altyazıyı referans al.",
    ),
    threads: int = typer.Option(
        max(1, min(8, os.cpu_count() or 4)),
        "-t", "--threads",
        help="CPU iş parçacığı (threads) sayısı.",
    ),
    language: Optional[str] = typer.Option(
        None,
        "--lang",
        help="Kaynak videonun ses dili (örn: tr, en, de). Boş bırakılırsa Whisper otomatik algılar.",
    ),
    vad_silence: int = typer.Option(
        300,
        "--vad-silence",
        help="VAD: iki konuşma arasındaki minimum sessizlik süresi (ms). Küçük değer = daha fazla segment.",
    ),
):
    """
    Tek bir hedef altyazıyı video, ses veya referans altyazı ile senkronize eder.
    """
    console.print(
        Panel.fit(
            "[bold cyan]altyazi-senkron[/bold cyan] - [bold white]AI Destekli Yüksek Hassasiyetli Senkronizasyon[/bold white]",
            border_style="cyan",
        )
    )

    if output is None:
        output = target_sub.parent / f"{target_sub.stem}_synced.srt"

    success, result, eval_metrics, err = process_single_sync(
        reference=reference,
        target_sub=target_sub,
        output=output,
        model=model,
        device=device,
        no_snap=no_snap,
        use_embedded=use_embedded,
        threads=threads,
        show_details=True,
        language=language,
        vad_min_silence=vad_silence,
    )

    if not success:
        console.print(f"\n[bold red]Hata:[/bold red] {escape(str(err))}")
        raise typer.Exit(code=1)

    console.print(f"[bold green]✔ Altyazı başarıyla kaydedildi:[/bold green] [underline]{escape(str(output))}[/underline]\n")

    # Özet Tablosu
    table = Table(title="Senkronizasyon Sonuç Raporu", show_header=True, header_style="bold magenta")
    table.add_column("Metrik", style="dim", width=25)
    table.add_column("Değer", style="bold")

    speed_pct = (result.detected_speed - 1.0) * 100.0
    speed_str = f"{result.detected_speed:.5f}x"
    if abs(speed_pct) > 0.01:
        speed_str += f" (%{speed_pct:+.2f} hız/FPS düzeltmesi)"

    status_color = "green" if eval_metrics["status"] in ["EXCELLENT", "GOOD"] else "yellow"
    if eval_metrics["status"] == "UNCERTAIN":
        status_color = "red"

    table.add_row("Durum", f"[{status_color}]{eval_metrics['status']}[/{status_color}]")
    table.add_row("Güven Skoru", f"%{eval_metrics['confidence_percentage']:.1f}")
    table.add_row("Sesle Örtüşen Satırlar", f"{eval_metrics['matched_count']} / {eval_metrics['total_subtitles']} (%{eval_metrics['matched_ratio']*100:.1f})")
    table.add_row("Hız Çarpanı", speed_str)
    table.add_row("Sabit Gecikme (Offset)", f"{result.detected_offset:+.3f} saniye")
    table.add_row("Parçalı Kesinti (Piecewise)", "Evet" if result.is_piecewise else "Hayır (Lineer)")

    console.print(table)

    if result.warnings:
        console.print("\n[bold yellow]Uyarılar:[/bold yellow]")
        for w in result.warnings:
            console.print(f"  [yellow]![/yellow] {w}")


@app.command(name="batch")
def batch_command(
    directory: Path = typer.Argument(
        Path("."),
        help="Video ve altyazıların bulunduğu klasör (Varsayılan: çalıştırılan dizin)",
        exists=True,
    ),
    model: str = typer.Option(
        "base",
        "-m", "--model",
        help="Whisper model boyutu: tiny, base, small, medium (Varsayılan: base)",
    ),
    device: str = typer.Option(
        "auto",
        "-d", "--device",
        help="Hesaplama birimi: cpu, cuda veya auto",
    ),
    no_snap: bool = typer.Option(
        False,
        "--no-snap",
        help="Milisaniyelik konuşma kenetlemesini devre dışı bırak.",
    ),
    use_embedded: bool = typer.Option(
        False,
        "--use-embedded",
        help="Videolarda gömülü altyazı varsa ses yerine doğrudan gömülü altyazıyı referans al.",
    ),
    force: bool = typer.Option(
        False,
        "-f", "--force",
        help=r"Zaten senkronlanmış .tr\[synced\].srt dosyası olsa bile tekrar işle.",
    ),
    recursive: bool = typer.Option(
        False,
        "-r", "--recursive",
        help="Alt dizinleri de tara.",
    ),
    threads: int = typer.Option(
        max(1, min(8, os.cpu_count() or 4)),
        "-t", "--threads",
        help="CPU iş parçacığı sayısı.",
    ),
    language: Optional[str] = typer.Option(
        None,
        "--lang",
        help="Kaynak videonun ses dili (örn: tr, en, de). Boş bırakılırsa Whisper otomatik algılar.",
    ),
    vad_silence: int = typer.Option(
        300,
        "--vad-silence",
        help="VAD: iki konuşma arasındaki minimum sessizlik süresi (ms).",
    ),
):
    r"""
    Dizindeki tüm videoları ve bunlara ait .tr.srt dosyalarını bulup
    tek seferde senkronize ederek .tr\[synced\].srt formatında kaydeder.
    """
    console.print(
        Panel.fit(
            "[bold cyan]altyazi-senkron batch[/bold cyan] - [bold white]Toplu Dizi / Film Senkronizasyonu[/bold white]",
            border_style="cyan",
        )
    )

    directory = directory.resolve()
    pairs = find_video_subtitle_pairs(directory, recursive=recursive)

    if not pairs:
        console.print(f"[bold yellow]Uyarı:[/bold yellow] [underline]{directory}[/underline] dizininde eşleşen video ve .srt/.tr.srt dosyası bulunamadı.")
        raise typer.Exit(code=0)

    console.print(f"[green]✔[/green] Toplam [bold]{len(pairs)}[/bold] adet video-altyazı eşleşmesi bulundu:\n")

    # Bulunan eşleşmeleri listele
    pair_table = Table(show_header=True, header_style="bold cyan")
    pair_table.add_column("#", width=4)
    pair_table.add_column("Video Dosyası")
    pair_table.add_column("Kaynak Altyazı (.tr.srt)")
    pair_table.add_column(escape("Hedef Çıktı (.tr[synced].srt)"))
    pair_table.add_column("Durum", width=12)

    to_process: List[Tuple[Path, Path, Path]] = []
    for idx, (vid, sub, out) in enumerate(pairs, start=1):
        if out.exists() and not force:
            status_str = "[dim yellow]Zaten Var[/dim yellow]"
        else:
            status_str = "[bold green]Kuyrukta[/bold green]"
            to_process.append((vid, sub, out))

        pair_table.add_row(str(idx), escape(vid.name), escape(sub.name), escape(out.name), status_str)

    console.print(pair_table)

    if not to_process:
        console.print(f"\n[bold green]Tüm dosyalar zaten senkronize edilmiş ({escape('.tr[synced].srt')} mevcut).[/bold green] Yeniden senkronlamak için [bold]--force[/bold] kullanabilirsiniz.")
        raise typer.Exit(code=0)

    console.print(f"\n[bold cyan]Senkronize edilecek {len(to_process)} dosya işleniyor...[/bold cyan]\n")

    # Modeli döngüden önce tek seferde yükle
    compute_device = "cuda" if device == "cuda" else "cpu"
    detector = SpeechDetector(
        model_size=model,
        device=compute_device,
        cpu_threads=threads,
    )

    results_summary = []

    for idx, (vid, sub, out) in enumerate(to_process, start=1):
        console.rule(f"[bold magenta]Dosya {idx}/{len(to_process)}: {escape(vid.name)}[/bold magenta]")
        
        prefix = f"[{idx}/{len(to_process)}] "
        success, res, metrics, err = process_single_sync(
            reference=vid,
            target_sub=sub,
            output=out,
            detector=detector,
            model=model,
            device=device,
            no_snap=no_snap,
            use_embedded=use_embedded,
            threads=threads,
            show_details=False,
            progress_prefix=prefix,
            language=language,
            vad_min_silence=vad_silence,
        )

        if success:
            console.print(f"[bold green]✔ Tamamlandı:[/bold green] {escape(out.name)} [cyan](Güven: %{metrics['confidence_percentage']:.1f} | Durum: {metrics['status']})[/cyan]\n")
            results_summary.append({
                "file": vid.name,
                "status": metrics["status"],
                "confidence": f"%{metrics['confidence_percentage']:.1f}",
                "offset": f"{res.detected_offset:+.2f}s",
                "output": out.name,
            })
        else:
            console.print(f"[bold red]✘ Hata:[/bold red] {escape(str(err))}\n")
            results_summary.append({
                "file": vid.name,
                "status": "HATA",
                "confidence": "-",
                "offset": "-",
                "output": escape(str(err)),
            })

    # Toplu İşlem Sonuç Özeti
    summary_table = Table(title="Toplu Senkronizasyon Raporu", show_header=True, header_style="bold green")
    summary_table.add_column("Video")
    summary_table.add_column("Durum")
    summary_table.add_column("Güven Skoru")
    summary_table.add_column("Gecikme (Offset)")
    summary_table.add_column("Çıktı Dosyası")

    for r in results_summary:
        st = r["status"]
        color = "green" if st in ["EXCELLENT", "GOOD"] else "yellow" if st == "ACCEPTABLE" else "red"
        summary_table.add_row(
            escape(r["file"]),
            f"[{color}]{st}[/{color}]",
            r["confidence"],
            r["offset"],
            escape(r["output"]),
        )

    console.print(summary_table)


@app.command(name="info")
def info_command(
    media_path: Path = typer.Argument(
        ...,
        help="İncelenecek medya dosyası (.mkv, .mp4, .avi, vb.)",
        exists=True,
    )
):
    """Medya dosyasındaki ses ve gömülü altyazı akışlarını listeler."""
    if not check_ffmpeg():
        console.print("[bold red]Hata:[/bold red] Sistemde 'ffmpeg' ve 'ffprobe' bulunamadı.")
        raise typer.Exit(code=1)

    subs = get_embedded_subtitles(media_path)
    console.print(f"\n[bold cyan]{media_path.name}[/bold cyan] analizi:")
    if not subs:
        console.print("[yellow]Gömülü altyazı akışı bulunamadı.[/yellow]")
    else:
        console.print(f"[green]Bulunan gömülü altyazılar ({len(subs)} adet):[/green]")
        for s in subs:
            def_badge = " [bold green](varsayılan)[/bold green]" if s['default'] else ""
            console.print(f"  • Akış #{s['index']}: Dil: [bold]{s['language']}[/bold] | Format: {s['codec']}{def_badge}")


def main():
    app()


if __name__ == "__main__":
    main()
