# Model ve Deney Notlari

## Mimari

- Giris: 8 normalize ozellik
- Gizli katmanlar: 64 -> 64 -> 32 (ReLU)
- Cikis: 1 lineer maliyet tahmini
- Kayip: Mean Squared Error (MSE)
- Optimizasyon: Adam

## Son Egitim

- Egitim harita seed baslangici: 42
- Dogrulama harita seed baslangici: 10042
- Egitim ornegi: 157,693
- Dogrulama ornegi: 31,668
- Epoch: 80
- Son egitim MSE: 15.5985
- Son dogrulama MSE: 11.9248

Egitim ve dogrulama verileri farkli harita seed'lerinden uretilmistir. Ground-truth
etiketleri, girilen hucreye bagli yonlu hareket maliyetlerini dikkate alan ters
Dijkstra ile hesaplanir.

## Yorumlama

Neural heuristic admissible olma garantisi tasimaz. Bu nedenle rota maliyeti her
senaryoda Dijkstra ve Octile ile birlikte raporlanir. Tek bir heuristic'in her harita
ailesinde en iyi olmasi beklenmez; dugum genisletme, calisma suresi ve rota maliyeti
birlikte degerlendirilmelidir.
