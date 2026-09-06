# altyazi-senkron

**altyazi-senkron**, `ffsubsync` ve `alass-cli` gibi geleneksel araçların sıklıkla başarısız olduğu, anlamsız kaymalar yaptığı ve müzik/patlama seslerine takıldığı senaryoları çözmek için geliştirilmiş **yeni nesil, AI destekli ve yüksek hassasiyetli altyazı senkronizasyon aracıdır**.

---

## 🎯 Neden altyazi-senkron?

| Problem | ffsubsync / alass | altyazi-senkron |
| :--- | :--- | :--- |
| **Gürültü & Müzik Yanılgısı** | WebRTC VAD müzik ve patlamaları "ses" sanır; yanlış sahneye kilitlenir. | **Faster-Whisper + Silero VAD + `no_speech_prob` filtresi** ile sahte sesler elenir, yalnızca gerçek diyaloglar referans alınır. |
| **Rastgele / Alakasız Kaymalar** | Çapraz korelasyon yerel tepe noktalarına takılıp altyazıyı $\pm 100$ sn kaydırabilir. | **RANSAC + Konuşma Ritim Analizi (Fingerprinting)** ile aykırı değerler dışlanır, matematiksel küresel uyum bulunur. |
| **FPS / Hız Farkı (Drift)** | 23.976 $\leftrightarrow$ 25 FPS gibi dönüşümlerde zamanla açılma yaşanır. | 23.976, 24, 25 (PAL), 29.97 (NTSC), 30 FPS arası tüm standart dönüşüm oranlarını otomatik dener (0.79x – 1.26x). |
| **Çoklu Reklam Araları / Kesintiler** | TV yayınlarında reklam aralarından sonra zincirleme olarak senkron dağılır. | **Rekürsif Değişim Noktası Analizi (Recursive Multi-cut)** ile 1, 2 veya 3 reklam arası içeren bölümleri parçalara ayırarak çözer. |
| **Milisaniyelik Uyum (Snapping)** | Altyazı kabaca oturur fakat dudak hareketlerine tam kenetlenmez. | **$O(\log N)$ Snapper Motoru** ile altyazı başlangıç ve bitişini milisaniyelik hassasiyetle konuşma sınırlarına kilitler. |
| **Çift / Çoklu Bölüm Desteği** | `S01E01-E02` gibi yayınları tanıyamaz veya yanlış eşleştirir. | Özel Regex motoru `S01E01-E02`, `1x01-02`, `Ep01` gibi tüm kalıpları çözer. |
| **Doğrulama ve Güven Skoru** | Hatalı çıksa bile kullanıcıya bildirmeden yanlış dosyayı kaydeder. | İşlem sonunda örtüşme yüzdesi, güven skoru ve net durum raporu sunar. |

---

## 🚀 Kurulum Rehberi

Aracın videolardan ses analizi yapabilmesi için sisteminizde **FFmpeg** ve **Python (>= 3.9)** bulunmalıdır.

### 1. Ön Gereksinim: FFmpeg Kurulumu

* **Windows:** PowerShell'i yönetici olarak açın ve çalıştırın:
  ```powershell
  winget install Gyan.FFmpeg
  ```
* **Ubuntu / Debian:**
  ```bash
  sudo apt install ffmpeg
  ```
* **Fedora / RHEL:**
  ```bash
  sudo dnf install ffmpeg
  ```
* **Arch Linux:**
  ```bash
  sudo pacman -S ffmpeg
  ```
* **macOS:**
  ```bash
  brew install ffmpeg
  ```

---

### 2. İşletim Sistemine Göre Kurulum

Projeyi bilgisayarınıza klonlayın:
```bash
git clone https://github.com/fatihozturk-1/altyazi-senkron.git
cd altyazi-senkron
```

---

#### 🪟 Windows Kurulumu (`pipx` ile - Önerilen)

Windows'ta aracı herhangi bir klasörden (C:\, D:\ vb.) bağımsız bir program gibi çalıştırabilmek için **`pipx`** kullanılır.

1. **pipx'in kurulu olduğundan emin olun:**
   ```powershell
   pip install pipx
   pipx ensurepath
   ```
   *(Not: `pipx ensurepath` komutunu çalıştırdıktan sonra terminali bir kez kapatıp yeniden açın).*

2. **altyazi-senkron'u kurun:**
   ```powershell
   pipx install .
   ```

> **Tebrikler!** Artık PowerShell, CMD veya Windows Terminal'de nerede olursanız olun doğrudan `altyazi-senkron` yazarak kullanabilirsiniz.

---

#### 🐧 Linux & macOS Kurulumu

Aşağıdaki yöntemlerden birini seçebilirsiniz:

##### Yöntem A: Otomatik Kurulum Scripti (En Kolay)
Repodaki hazır script sanal ortamı kurar, bağımlılıkları yükler ve global komutu oluşturur:
```bash
./install.sh
```

##### Yöntem B: pipx ile Kurulum
```bash
pipx install .
```

##### Yöntem C: Klasik Python Sanal Ortam (`venv`)
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .

# Her dizinden doğrudan çalıştırabilmek için global kısayol ekleyin:
mkdir -p ~/.local/bin
ln -sf $(pwd)/.venv/bin/altyazi-senkron ~/.local/bin/altyazi-senkron
```

---

## 💻 Kullanım Kılavuzu

Kurulum tamamlandıktan sonra terminali **istediğiniz klasörde** açıp doğrudan komutları çalıştırabilirsiniz.

### 1. Toplu Dizi / Film Senkronizasyonu (`batch`)
Bulunduğunuz klasördeki tüm video dosyalarını ve bunlara ait `.tr.srt` (veya `.srt`) altyazılarını otomatik tespit eder, sırayla senkronize eder ve `.tr[synced].srt` olarak kaydeder:

```bash
# Bulunduğunuz klasördeki tüm bölümleri tek seferde senkronla:
altyazi-senkron batch

# Dışarıdan başka bir klasörü senkronla:
altyazi-senkron batch "D:\Diziler\The Walking Dead\Season 03"

# Kaynak ses dilini belirterek daha hızlı ve kesin sonuç al:
altyazi-senkron batch --lang en
```

* **Gelişmiş Bölüm Eşleştirme:** `S01E01`, `1x01` ve çift bölümlü `S01E01-E02` / `1x01-02` dosyalarını kusursuz eşleştirir.
* **Akıllı Model Önbelleği:** Yapay zeka modeli her bölüm için tekrar tekrar yüklenmez; bellekte tutulur ve sonraki bölümler çok daha hızlı işlenir.
* **Kaldığı Yerden Devam:** Zaten `.tr[synced].srt` üretilmiş olan dosyalar otomatik atlanır (tekrar işlemek için `--force` eklenebilir).

---

### 2. Tek Bir Dosyayı Senkronize Etme (`sync`)
Belirli bir video ve altyazıyı senkronize etmek için:
```bash
altyazi-senkron sync film.mkv altyazi_tr.srt -o senkron_tr.srt
```

#### 💡 İpucu: En Yüksek Hassasiyet İçin Parametreler
```bash
# İngilizce sesli bir film için dil ipucu ve daha büyük model:
altyazi-senkron sync film.mkv altyazi_tr.srt --lang en --model small

# Hızlı konuşulan dizilerde diyalog ayrımını hassaslaştırmak için:
altyazi-senkron sync dizi.mkv altyazi_tr.srt --vad-silence 150
```

---

### 3. Gömülü Altyazı Kısayolu (`--use-embedded`)
Videonuzun içinde zaten orijinal dilde (örn. İngilizce) gömülü bir altyazı varsa, ses analizine hiç girmeden **2 saniyede** Türkçe altyazıyı bu referansa kilitler:
```bash
altyazi-senkron sync film.mkv altyazi_tr.srt --use-embedded
# veya toplu işlemde:
altyazi-senkron batch --use-embedded
```

---

### 4. İki Altyazı Arası Senkronizasyon (Sub-to-Sub)
Elinizde videoyla tam uyumlu bir yabancı altyazı ve kaymış bir Türkçe altyazı varsa ses analizine gerek kalmadan doğrudan senkronlayabilirsiniz:
```bash
altyazi-senkron sync ingilizce.srt turkce.srt -o duzeltilmis_turkce.srt
```

---

### 5. Medya Bilgilerini İnceleme (`info`)
Video dosyasındaki ses kanallarını ve gömülü altyazı akışlarını listelemek için:
```bash
altyazi-senkron info film.mkv
```

---

## ⚙️ Parametreler ve Seçenekler

| Parametre | Komut | Açıklama |
| :--- | :--- | :--- |
| `-m, --model` | `sync`, `batch` | Whisper model boyutu: `tiny`, `base`, `small`, `medium` *(Varsayılan: `base`, zorlu sesler için `small` önerilir)* |
| `--lang` | `sync`, `batch` | Kaynak videonun ses dili (örn: `en`, `tr`, `de`, `fr`). Otomatik tespiti atlar, hız ve doğruluğu artırır. |
| `--vad-silence` | `sync`, `batch` | İki konuşma arası minimum sessizlik eşiği (ms) *(Varsayılan: `300`). Hızlı konuşmalar için `150-200` önerilir.* |
| `-d, --device` | `sync`, `batch` | Donanım birimi: `cpu`, `cuda` veya `auto` *(Varsayılan: `auto`)* |
| `--use-embedded` | `sync`, `batch` | Varsa videodaki gömülü altyazıyı referans alarak ses analizini atlar. |
| `--no-snap` | `sync`, `batch` | Milisaniyelik diyalog kenetlemesini (snapping) devre dışı bırakır. |
| `-f, --force` | `batch` | Zaten `.tr[synced].srt` olsa bile dosyayı tekrar senkronlar. |
| `-r, --recursive` | `batch` | Alt klasörleri de tarar. |
| `-t, --threads` | `sync`, `batch` | Kullanılacak CPU iş parçacığı sayısı *(Varsayılan: sistem çekirdekleri)* |
| `-o, --output` | `sync` | Özel çıktı dosyası yolu *(Varsayılan: `<hedef>_synced.srt`)* |

---

## 🧪 Testleri Çalıştırma

Proje 17 adet kapsamlı birim ve uçtan uca entegrasyon testi ile korunmaktadır:
```bash
pytest -v
```

