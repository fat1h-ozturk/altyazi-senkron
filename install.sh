#!/usr/bin/env bash
set -e

echo "========================================="
echo "  altyazi-senkron Kurulum Sihirbazı"
echo "========================================="

# 1. FFmpeg Kontrolü
if ! command -v ffmpeg &> /dev/null; then
    echo "⚠️  UYARI: 'ffmpeg' sisteminizde bulunamadı!"
    echo "   altyazi-senkron'un ses analizi yapabilmesi için ffmpeg gereklidir."
    echo "   Ubuntu/Debian: sudo apt install ffmpeg"
    echo "   Fedora/RHEL:   sudo dnf install ffmpeg"
    echo "   Arch Linux:    sudo pacman -S ffmpeg"
    echo "   macOS:         brew install ffmpeg"
    echo ""
fi

# 2. Python Kontrolü
if ! command -v python3 &> /dev/null; then
    echo "❌ HATA: Python 3 bulunamadı. Lütfen Python 3.9 veya üzerini kurun."
    exit 1
fi

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$PROJECT_DIR/.venv"

echo "📦 1/3: Sanal ortam oluşturuluyor (.venv)..."
python3 -m venv "$VENV_DIR"

echo "⬇️  2/3: Bağımlılıklar kuruluyor..."
"$VENV_DIR/bin/pip" install --upgrade pip --quiet
"$VENV_DIR/bin/pip" install -e "$PROJECT_DIR" --quiet

echo "🔗 3/3: Komut satırı kısayolu oluşturuluyor..."
mkdir -p "$HOME/.local/bin"
ln -sf "$VENV_DIR/bin/altyazi-senkron" "$HOME/.local/bin/altyazi-senkron"

echo ""
echo "========================================="
echo "🎉 Kurulum Başarıyla Tamamlandı!"
echo "========================================="
echo ""
echo "Artık herhangi bir klasörde terminali açıp doğrudan şu komutları kullanabilirsiniz:"
echo ""
echo "  • Bulunulan dizindeki tüm bölümleri senkronla: altyazi-senkron batch"
echo "  • Tek bir filmi senkronla:                     altyazi-senkron sync film.mkv altyazi.srt"
echo "  • Yardım menüsü:                               altyazi-senkron --help"
echo ""
if [[ ":$PATH:" != *":$HOME/.local/bin:"* ]]; then
    echo "⚠️  Not: ~/.local/bin dizini PATH değişkeninizde ekli değilse,"
    echo "   terminal profilinize (~/.bashrc veya ~/.zshrc) şunu ekleyin:"
    echo '   export PATH="$HOME/.local/bin:$PATH"'
fi
