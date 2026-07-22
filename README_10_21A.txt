AlphaScan PRO — Sprint 10.21A
Açıklanabilir Finansal Kalite Motoru

Bu sprint:
- BIST bilanço ekranına 0-100 Finansal Kalite puanı ekler.
- A+, A, B+, B, C+, C, D ve E notu üretir.
- Büyüme, Kârlılık, Finansal Yapı, Nakit/Likidite ve Değerleme alt puanlarını gösterir.
- Eksik veriyi sıfır puan saymaz; veri kapsama oranını ayrıca gösterir.
- Her ölçütün değerini, puanını, kaynağını ve açıklamasını görünür yapar.
- Yahoo Finance info verisi eksik olduğunda son iki gelir tablosu döneminden gelir/net kâr değişimini kullanabilir.
- Güçlü alanlar ve dikkat gerektiren noktaları otomatik özetler.
- Robotun mevcut giriş/çıkış kurallarını değiştirmez.

Kurulum:
1) ZIP içeriğini C:\Users\Faruk\AlphaScanPRO_Git_Temiz klasörüne çıkar.
2) PowerShell:

py -3.13 .\apply_sprint10_21a.py
py -3.13 .\verify_sprint10_21a.py

Git:

git add engine/fundamental_quality.py ui/financial_analysis_page.py tests/test_fundamental_quality_10_21a.py apply_sprint10_21a.py verify_sprint10_21a.py README_10_21A.txt
git commit -m "Sprint 10.21A explainable financial quality engine"

Kontrol:
AlphaScan > Bilanço ve Yapay Zekâ Analizi > bir BIST kodu gir > Bilançoyu Getir.
