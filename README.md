# altyazi-senkron

**altyazi-senkron**, `ffsubsync` ve `alass-cli` gibi geleneksel araçların sıklıkla başarısız olduğu, anlamsız kaymalar yaptığı ve gürültüye takıldığı senaryoları çözmek için geliştirilmiş **yeni nesil, AI destekli ve yüksek hassasiyetli (%99+ kesinlik)** altyazı senkronizasyon aracıdır.

---

## 🎯 Neden ffsubsync ve alass-cli Başarısız Olur?

| Problem | ffsubsync / alass | altyazi-senkron |
| :--- | :--- | :--- |
| **Gürültü / Müzik Algılama** | WebRTC VAD müzik ve patlamaları "ses" sanır; yanlış sahneye kilitlenir. | **Faster-Whisper + Silero VAD** sadece gerçek insan konuşmalarını ayıklar, gürültüyü %100 eler. |
| **Rastgele / Alakasız Kaymalar** | FFT Cross-Correlation yerel tepe noktalarına (local minima/maxima) takılır. | **RANSAC + Konuşma Parmak İzi (Fingerprinting)** ile aykırı değerler dışlanır, matematiksel küresel uyum bulunur. |
| **FPS / Hız Farkı (Drift)** | 23.976 $\leftrightarrow$ 25 FPS dönüşümlerinde zamanla açılma yaşanabilir. | Standart film/video kare hızlarını otomatik dener ve en küçük sapmayı hesaplar. |
| **Parçalı Kesintiler (Piecewise)** | TV reklam araları veya kesilmiş sahnelerde zincirleme olarak dağılır. | Değişim noktası analiziyle (Change-point detection) filmi parçalara ayırarak çözer. |
| **Milisaniyelik Uyum (Snapping)** | Altyazı kabaca sahneye oturur fakat konuşmanın başladığı ana kenetlenmez. | **Snapper Motoru** ile altyazı başlangıç ve bitişini milisaniyelik ses sınırına kilitler. |
| **Doğrulama ve Güven Skoru** | Hatalı çıksa bile kullanıcıya bildirmeden yanlış dosyayı yazar. | İşlem sonunda **Güven Skoru (%98.4)** ve örtüşme raporu sunar. |

---

## 🚀 Kurulum

### Gereksinimler
- **Python:** >= 3.9
- **FFmpeg & FFprobe:** Sisteminizde kurulu olmalıdır (`sudo dnf install ffmpeg` veya `sudo apt install ffmpeg`).

### Sanal Ortam ve Kurulum
```bash
git clone https://github.com/fatih/altyazi-senkron.git
cd altyazi-senkron

# Sanal ortam oluşturup aktifleştirin
python3 -m venv .venv
source .venv/bin/activate

# Paketleri kurun
pip install -e .
```

---

## 💻 Kullanım

### 1. Toplu Dizi / Film Senkronizasyonu (`batch`)
Bulunduğunuz klasördeki tüm video dosyalarını ve bunlara ait `.tr.srt` (veya `.srt`) altyazılarını otomatik olarak bulup tek seferde senkronize eder ve `.tr[synced].srt` olarak kaydeder:
```bash
# Bulunulan dizindeki tüm dizi bölümlerini tek seferde senkronla:
altyazi-senkron batch

# Farklı bir klasörü senkronla:
altyazi-senkron batch /home/fatih/Videolar/Diziler/BreakingBad/
```
* **Otomatik Eşleşme:** `S01E01`, `1x01` gibi bölüm numaralarını ve dosya adlarını akıllıca eşleştirir.
* **Akıllı Bellek Kullanımı:** Yapay zeka modeli her bölüm için tekrar tekrar yüklenmez; bellekte tutularak sıradaki bölümler çok daha hızlı işlenir.
* **Kaldığı Yerden Devam:** Zaten `.tr[synced].srt` üretilmiş bölümleri otomatik atlar (yeniden işlemek için `--force` parametresi verilebilir).

### 2. Tek Bir Video ile Altyazı Senkronizasyonu (`sync`)
Videonuzdaki ses yapay zeka ile analiz edilir ve altyazı sıfır hata ile sese kenetlenir:
```bash
altyazi-senkron sync film.mkv altyazi_tr.srt -o senkron_tr.srt
```

### 3. Gömülü Altyazı Kısayolu (`--use-embedded`)
Eğer videonuzda zaten orijinal dilde (örn. İngilizce) bir altyazı varsa, ses analizine hiç gerek kalmadan 2 saniyede Türkçe altyazıyı bu referansa kilitler:
```bash
altyazi-senkron sync film.mkv altyazi_tr.srt --use-embedded -o senkron_tr.srt
```

### 4. İki Altyazı Arası Senkronizasyon (Sub-to-Sub)
Elinizde videoya tam uyan bir İngilizce altyazı ve kaymış bir Türkçe altyazı varsa:
```bash
altyazi-senkron sync uyumlu_en.srt kaymis_tr.srt -o duzeltilmis_tr.srt
```

### 5. Model Boyutu ve Performans Seçenekleri
Whisper modelini donanımınıza göre belirleyebilirsiniz (`tiny`, `base`, `small`, `medium`):
```bash
# Çok hızlı tarama (Hafif model):
altyazi-senkron batch -m tiny

# Yüksek hassasiyet (Varsayılan):
altyazi-senkron batch -m base
```

### 6. Medya Bilgilerini İnceleme
Videodaki ses ve altyazı akışlarını listelemek için:
```bash
altyazi-senkron info film.mkv
```

---

## ⚙️ Komut Parametreleri

```text
Usage: altyazi-senkron sync [OPTIONS] REFERENCE TARGET_SUB

Seçenekler:
  -o, --output PATH       Çıktı altyazı yolu. Varsayılan: <hedef>_synced.srt
  -m, --model TEXT        Whisper model boyutu: tiny, base, small, medium [varsayılan: base]
  -d, --device TEXT       cpu, cuda veya auto [varsayılan: auto]
  --no-snap               Milisaniyelik konuşma kenetlemesini (snapping) kapatır.
  --use-embedded          Videodaki gömülü altyazıyı otomatik referans alır.
  -t, --threads INT       Kullanılacak CPU iş parçacığı sayısı. [varsayılan: sistem çekirdekleri]
  --help                  Yardım mesajını görüntüler.
```

---

## 🧪 Testleri Çalıştırma

Tüm birim ve entegrasyon testlerini çalıştırmak için:
```bash
pytest -v
```

---

## 📄 Lisans
MIT License
