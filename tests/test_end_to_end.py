from typer.testing import CliRunner
from pathlib import Path
from altyazi_senkron.cli import app
from altyazi_senkron.subtitle import format_srt_timestamp

runner = CliRunner()


def test_cli_sub_to_sub_sync(tmp_path: Path):
    """Test full CLI pipeline when syncing two subtitle files (sub-to-sub)."""
    # Create ground truth reference subtitles (already in sync with video)
    ref_content = """1
00:00:05,000 --> 00:00:08,000
English line one.

2
00:00:12,500 --> 00:00:16,000
English line two.

3
00:00:20,000 --> 00:00:24,000
English line three.

4
00:00:30,000 --> 00:00:33,500
English line four.
"""
    ref_file = tmp_path / "reference.srt"
    ref_file.write_text(ref_content, encoding="utf-8")

    # Create target subtitles with +3.500s constant delay
    shift = 3.500
    target_content = f"""1
{format_srt_timestamp(5.0 - shift)} --> {format_srt_timestamp(8.0 - shift)}
Türkçe satır bir.

2
{format_srt_timestamp(12.5 - shift)} --> {format_srt_timestamp(16.0 - shift)}
Türkçe satır iki.

3
{format_srt_timestamp(20.0 - shift)} --> {format_srt_timestamp(24.0 - shift)}
Türkçe satır üç.

4
{format_srt_timestamp(30.0 - shift)} --> {format_srt_timestamp(33.5 - shift)}
Türkçe satır dört.
"""
    target_file = tmp_path / "target.srt"
    target_file.write_text(target_content, encoding="utf-8")

    output_file = tmp_path / "synced_output.srt"

    result = runner.invoke(
        app,
        ["sync", str(ref_file), str(target_file), "-o", str(output_file)],
    )

    assert result.exit_code == 0
    assert output_file.exists()
    assert "Senkronizasyon Sonuç Raporu" in result.output


def test_cli_batch_empty_dir(tmp_path: Path):
    """Test batch command when no matching pairs are present in directory."""
    result = runner.invoke(app, ["batch", str(tmp_path)])
    assert result.exit_code == 0
    assert "dosyası bulunamadı" in result.output

