# Neural-Guided A* Search for Dynamic Route Optimization

İHA/SİHA otonom görev planlaması için sinir ağı destekli A* arama algoritması.
Bu birleşik sürüm, doğrulanmış zaman-genişletmeli A* çekirdeğini koyu temalı rota
karşılaştırmaları ve adım adım dinamik görev görselleriyle bir araya getirir.

Bu sürümde varsayılan demo **zaman-genişletmeli dinamik A*** kullanır. Yani tehditler rota boyunca varış zamanına göre kontrol edilir; yalnızca başlangıç anındaki statik harita kullanılmaz.

Güncel sürümde dinamik tehditler opsiyonel hareket desenine sahiptir. Özellikle
dinamik tehdit senaryosunda radar/SAM bölgeleri zamanla konum değiştirir ve demo
çalıştırıldığında her senaryo için İngilizce etiketli PNG görsellerin yanında
`*_dynamic_animation.gif` animasyon çıktısı üretilir.

## Kurulum

```bash
pip install -r requirements.txt
```

Python 3.10 veya daha yeni bir sürüm önerilir.

## Proje kökünden çalıştırma

```bash
# Varsayılan: dinamik A*, çıktı klasörü: visualizations/
python src/main.py --mode demo

# Açık şekilde dinamik A*
python src/main.py --mode demo --planner dynamic

# Grafik bağımlılıkları olmadan yalnızca algoritma ve sonuç özeti
python src/main.py --mode demo --planner dynamic --skip-visuals

# Statik A* karşılaştırmasını ayrı klasöre almak için
python src/main.py --mode demo --planner static --output visualizations_static

# Modeli yeniden eğitmek için
python src/main.py --mode train --epochs 80

# Güncel görsellerden PDF raporu üretmek için
python src/generate_report.py

# Çekirdek doğruluk testleri
python -m unittest discover -s tests -v
```

`src/` içine girip çalıştırmak da desteklenir; dosya yolları script konumuna göre çözüldüğü için proje kökünden veya `src/` klasöründen çalıştırma aynı şekilde çalışır.

## Klasör Yapısı

```text
neural_astar_uav_fixed_v2/
├── src/
│   ├── environment.py        # 50x50 İHA operasyon ortamı
│   ├── astar.py              # Statik A*, dinamik A* + klasik heuristic'ler
│   ├── neural_heuristic.py   # MLP (NumPy) + eğitim
│   ├── visualization.py      # Görselleştirme
│   ├── main.py               # Ana çalıştırma scripti
│   └── generate_report.py    # PDF rapor üretici
├── data/
│   └── mlp_heuristic.pkl     # Eğitilmiş model
├── visualizations/           # Güncel demo çıktıları
├── report/
│   └── proje_raporu.pdf      # Güncel rapor
├── requirements.txt
├── FIX_NOTES.md
└── README.md
```

## Karşılaştırılan Heuristic'ler

- **Dijkstra (h=0):** Optimum maliyet kontrolü için baseline.
- **Manhattan:** Klasik heuristic; 8-yönlü harekette admissible değildir.
- **Octile:** 8-yönlü hareket için admissible klasik baseline.
- **Neural (MLP):** 8 öznitelik → 64 → 64 → 32 → 1, NumPy ile sıfırdan.

## Düzeltilmiş Noktalar

- Proje kökünden `python src/main.py` çalıştırıldığında model ve çıktı yolları artık doğru çözülür.
- Dinamik planlama için zaman-genişletmeli A* eklendi: durum `(satır, sütun, zaman)`.
- Neural heuristic dinamik aramada her düğümün gerçek varış zamanını kullanır.
- Eğitim ground-truth değerleri, yönlü hücre maliyetlerine uygun ters Dijkstra ile üretilir.
- Doğrulama verisi eğitimden farklı harita seed'leriyle oluşturulur.
- `mission.max_range` arama sırasında kontrol edilir.
- Çapraz hareketlerde corner-cutting engellendi.
- Çakışan tehdit alanlarında herhangi bir aktif tehdit varsa hücre aktif tehdit sayılır.
- Dinamik tehditlere zaman-bağımlı hareket deseni eklendi.
- Dijkstra baseline demo sonuçlarına eklendi.
- Koyu temalı üst üste rota karşılaştırması, üç metrikli benchmark paneli ve
  Neural rota için zaman uyumlu snapshot/GIF animasyon çıktıları eklendi.
- Ana demo tarafından üretilen görsel başlıkları, lejantlar ve grafik etiketleri İngilizceye çevrildi.
- `generate_report.py` tabloları hardcoded eski değerler yerine `visualizations/ozet.txt` üzerinden güncel sonuçlardan üretir.
- Gereksiz `__pycache__` ve hatalı boş klasörler temizlendi.
