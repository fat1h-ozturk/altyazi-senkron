# altyazi-senkron

**altyazi-senkron**, `ffsubsync` ve `alass-cli` gibi geleneksel araçların sıklıkla başarısız olduğu, anlamsız kaymalar yaptığı ve müzik/patlama seslerine takıldığı senaryoları çözmek için geliştirilmiş **yeni nesil, AI destekli ve yüksek hassasiyetli altyazı senkronizasyon aracıdır.

---

## 🎯 Neden altyazi-senkron?

| Problem | ffsubsync / alass | altyazi-senkron |
| :--- | :--- | :--- |
| **Gürültü & Müzik Yanılgısı** | WebRTC VAD müzik ve patlamaları "ses" sanır; yanlış sahneye kilitlenir. | **Faster-Whisper + Silero VAD** sadece gerçek insan konuşmalarını ayıklar, gürültüyü tamamen eler. |
| **Rastgele / Alakasız Kaymalar** | Çapraz korelasyon yerel tepe noktalarına takılıp altyazıyı $\pm 100$ sn kaydırabilir. | **RANSAC + Konuşma Parmak İzi (Fingerprinting)** ile aykırı değerler dışlanır, matematiksel küresel uyum bulunur. |
| **FPS / Hız Farkı (Drift)** | 23.976 $\leftrightarrow$ 25 FPS dönüşümlerinde zamanla açılma yaşanabilir. | Standart film/video kare hızlarını otomatik dener ve en küçük sapmayı hesaplar. |
| **Parçalı Kesintiler (Piecewise)** | TV reklam araları veya kesilmiş sahnelerde zincirleme olarak dağılır. | **Değişim noktası analizi (Change-point)** ile filmi parçalara ayırarak çözer. |
| **Milisaniyelik Uyum (Snapping)** | Altyazı kabaca oturur fakat diyalog başlangıcına tam kenetlenmez. | **Snapper Motoru** ile altyazı başlangıç ve bitişini konuşma sınırına kilitler. |
| **Doğrulama ve Güven Skoru** | Hatalı çıksa bile kullanıcıya bildirmeden yanlış dosyayı kaydeder. | İşlem sonunda Güven Skoru ve örtüşme raporu sunar. |

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
```

* **Otomatik Eşleşme:** `S01E01`, `1x01` gibi bölüm numaralarını akıllıca eşleştirir.
* **Akıllı Model Önbelleği:** Yapay zeka modeli her bölüm için tekrar tekrar yüklenmez; bellekte tutulur ve sonraki bölümler çok daha hızlı işlenir.
* **Kaldığı Yerden Devam:** Zaten `.tr[synced].srt` üretilmiş olan dosyalar otomatik atlanır (tekrar işlemek için `--force` eklenebilir).

---

### 2. Tek Bir Dosyayı Senkronize Etme (`sync`)
Belirli bir video ve altyazıyı senkronize etmek için:
```bash
altyazi-senkron sync film.mkv altyazi_tr.srt -o senkron_tr.srt
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
Elinizde videoyla tam uyumlu bir yabancı altyazı ve kaymış bir Türkçe altyazı varsa:
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

| Parametre | Açıklama |
| :--- | :--- |
| `-m, --model` | Whisper model boyutu: `tiny`, `base`, `small`, `medium` *(Varsayılan: `base`)* |
| `-d, --device` | Donanım birimi: `cpu`, `cuda` veya `auto` *(Varsayılan: `auto`)* |
| `--use-embedded` | Varsa videodaki gömülü altyazıyı referans alarak ses analizini atlar. |
| `--no-snap` | Milisaniyelik diyalog kenetlemesini (snapping) devre dışı bırakır. |
| `-f, --force` | *(batch)* Zaten `.tr[synced].srt` olsa bile tekrar senkronlar. |
| `-r, --recursive` | *(batch)* Alt klasörleri de tarar. |
| `-t, --threads` | Kullanılacak CPU iş parçacığı sayısı *(Varsayılan: sistem çekirdekleri)* |

---

## 🧪 Testleri Çalıştırma

Geliştiriciler için birim ve entegrasyon testleri:
```bash
pytest -v
```

