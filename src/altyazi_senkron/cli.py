import os
import sys
from pathlib import Path
from typing import Optional
import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn

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
from .models import SpeechSegment

app = typer.Typer(
    name="altyazi-senkron",
    help="AI destekli, yüksek hassasiyetli film ve dizi altyazı senkronizasyon aracı.",
    add_completion=False,
)
console = Console()


def _is_subtitle_file(path: Path) -> bool:
    return path.suffix.lower() in [".srt", ".vtt", ".ass", ".ssa", ".sub"]


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
):
    """
    Hedef altyazıyı video, ses veya referans altyazı ile %99 kesinlikle senkronize eder.
    """
    console.print(
        Panel.fit(
            "[bold cyan]altyazi-senkron[/bold cyan] - [bold white]AI Destekli Yüksek Hassasiyetli Senkronizasyon[/bold white]",
            border_style="cyan",
        )
    )

    if output is None:
        output = target_sub.parent / f"{target_sub.stem}_synced.srt"

    # 1. Altyazıyı Yükle
    with console.status("[bold green]Hedef altyazı yükleniyor...[/bold green]"):
        try:
            target_items = load_subtitles(target_sub)
        except Exception as e:
            console.print(f"[bold red]Hata:[/bold red] Altyazı okunamadı: {e}")
            raise typer.Exit(code=1)

    console.print(f"[green]✔[/green] Hedef altyazı okundu: [bold]{len(target_items)}[/bold] satır.")

    speech_segments = []
    temp_files = []

    try:
        # Senaryo A: Referans olarak başka bir altyazı verilmişse (Sub-to-Sub)
        if _is_subtitle_file(reference):
            console.print("[yellow]ℹ[/yellow] Referans olarak altyazı dosyası sağlandı. Altyazı-altyazı eşleşmesi yapılıyor...")
            ref_items = load_subtitles(reference)
            speech_segments = [
                SpeechSegment(start=item.start, end=item.end, text=item.text)
                for item in ref_items
            ]
        else:
            # Senaryo B: Video veya ses dosyası
            if not check_ffmpeg():
                console.print("[bold red]Hata:[/bold red] Sistemde 'ffmpeg' bulunamadı.")
                raise typer.Exit(code=1)

            # Gömülü altyazı kontrolü
            embedded_subs = get_embedded_subtitles(reference)
            if embedded_subs:
                console.print(f"[cyan]ℹ[/cyan] Videoda [bold]{len(embedded_subs)}[/bold] adet gömülü altyazı tespit edildi:")
                for sub in embedded_subs:
                    lang = sub.get('language') or 'belirtilmemiş'
                    title = f" - {sub['title']}" if sub.get('title') else ""
                    console.print(f"   • İndeks #{sub['index']}: {lang.upper()}{title}")

                if use_embedded:
                    ref_track = embedded_subs[0]['index']
                    console.print(f"[green]✔[/green] Gömülü altyazı #{ref_track} referans olarak çekiliyor...")
                    extracted_sub = reference.parent / f"{reference.stem}_extracted_ref.srt"
                    temp_files.append(extracted_sub)
                    extract_embedded_subtitle(reference, ref_track, extracted_sub)
                    ref_items = load_subtitles(extracted_sub)
                    speech_segments = [
                        SpeechSegment(start=item.start, end=item.end, text=item.text)
                        for item in ref_items
                    ]

            # Gömülü altyazı kullanılmadıysa, ses ve ASR ile devam et
            if not speech_segments:
                # 2. Sesi Çıkar
                with console.status("[bold green]Video dosyasından 16kHz ses ayıklanıyor (FFmpeg)...[/bold green]"):
                    wav_path = extract_audio_wav(reference)
                    temp_files.append(wav_path)

                console.print("[green]✔[/green] Ses akışı hazırlandı.")

                # Donanım seçimi
                compute_device = "cpu"
                if device == "cuda":
                    compute_device = "cuda"
                elif device == "auto":
                    compute_device = "cpu"  # default safe fallback

                # 3. Konuşma Tespiti (Whisper + Silero VAD)
                detector = SpeechDetector(
                    model_size=model,
                    device=compute_device,
                    cpu_threads=threads,
                )

                with Progress(
                    SpinnerColumn(),
                    TextColumn("[progress.description]{task.description}"),
                    BarColumn(),
                    TimeElapsedColumn(),
                    console=console,
                ) as progress:
                    task = progress.add_task(
                        f"[cyan]Yapay Zeka Ses & Konuşma Analizi ({model})...[/cyan]",
                        total=100.0,
                    )

                    def update_progress(current_sec: float, total_sec: float):
                        if total_sec > 0:
                            pct = min(100.0, (current_sec / total_sec) * 100.0)
                            progress.update(task, completed=pct)

                    speech_segments = detector.detect_segments(
                        wav_path,
                        progress_callback=update_progress,
                    )
                    progress.update(task, completed=100.0)

                console.print(f"[green]✔[/green] Toplam [bold]{len(speech_segments)}[/bold] konuşma aralığı tespit edildi.")

        # 4. Eşleştirme Motoru (RANSAC & Rhythm Fingerprinting)
        with console.status("[bold green]RANSAC ve konuşma ritim eşleştirmesi yapılıyor...[/bold green]"):
            matcher = SubtitleMatcher()
            result = matcher.align(target_items, speech_segments)

        # 5. Snapping (Milisaniyelik Konuşma Başlangıç/Bitiş Kenetleme)
        if not no_snap:
            with console.status("[bold green]Milisaniyelik konuşma sınırlarına kenetleniyor (Snapping)...[/bold green]"):
                snapper = SubtitleSnapper()
                final_subtitles = snapper.snap(target_items, speech_segments, result.segments)
        else:
            # Sadece lineer dönüşüm uygula
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

        # 6. Doğrulama ve İstatistikler
        eval_metrics = AlignmentValidator.evaluate(final_subtitles, speech_segments, result)

        # 7. Sonucu Kaydet
        save_srt(final_subtitles, output)
        console.print(f"[bold green]✔ Altyazı başarıyla kaydedildi:[/bold green] [underline]{output}[/underline]\n")

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

    finally:
        # Geçici dosyaları temizle
        for f in temp_files:
            try:
                if f.exists():
                    f.unlink()
            except Exception:
                pass


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
