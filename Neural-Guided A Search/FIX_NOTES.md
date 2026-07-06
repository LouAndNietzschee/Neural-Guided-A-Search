# Düzeltme Notları

Bu sürüm, teslim/çalıştırma sırasında yakalanabilecek ana sorunları azaltmak için düzenlendi.

## Kod Düzeltmeleri

1. **Çalışma dizininden bağımsız yollar**
   - `main.py` ve `generate_report.py` artık `Path(__file__).resolve()` ile proje kökünü bulur.
   - Proje kökünden `python src/main.py` komutu çalışır.

2. **Dinamik A***
   - `astar_search_dynamic()` eklendi.
   - Durum mantığı `(satır, sütun, zaman)` olacak şekilde genişletildi.
   - Komşu hücrelerin geçilebilirliği varış zamanında kontrol edilir.
   - Bekleme aksiyonu desteklenir.

3. **Menzil kontrolü**
   - `mission.max_range` artık hem statik hem dinamik A* içinde kontrol edilir.

4. **Corner-cutting kontrolü**
   - Çapraz hareketlerde iki komşu kenar hücresi engelliyse çapraz geçiş yasaklandı.

5. **Çakışan tehdit güvenliği**
   - Bir hücre birden fazla tehdit alanında ise, herhangi biri aktif olduğunda hücre aktif tehdit kabul edilir.

6. **Dijkstra baseline**
   - Demo çıktılarında Dijkstra `(h=0)` eklendi.
   - Rota maliyetlerinde optimum referans olarak kullanılabilir.

## Rapor Düzeltmeleri

1. `generate_report.py` içindeki eski hardcoded sonuç tabloları kaldırıldı.
2. Rapor tabloları `visualizations/ozet.txt` dosyasından güncel sonuçları okur.
3. Neural heuristic için "her durumda optimaldir" iddiası kaldırıldı.
4. Neural sonuçları artık "düğüm genişletme - maliyet sapması" takası olarak anlatılır.
5. Eksik görsel varsa rapor üretici sessiz geçmek yerine uyarı basar.

## Teslimden Önce Önerilen Komutlar

```bash
python -m py_compile src/*.py
python src/main.py --mode demo --planner dynamic
python src/generate_report.py
```
