AlphaScan PRO Sprint 10.16C — Multi-Timeframe Market Intelligence

Kurulum:
  py -3.13 .\apply_sprint10_16c.py
  py -3.13 .\verify_sprint10_16c.py
  py -3.13 -m streamlit run app.py

Yeni özellikler:
- 15m, 1h, 4h ve 1d rejimlerini ağırlıklı birleştirme
- Uyum skoru ve zaman dilimi çatışma seviyesi
- Üst zaman dilimi zayıf/ayı olduğunda işlem kilidi
- Orta/yüksek çatışmada pozisyon ve risk azaltma
- Adaptif minimum giriş puanına MTF farkı ekleme
- Robot miktarına MTF pozisyon çarpanı uygulama
- Market Intelligence ekranında MTF matrisi
- Eski tek-zaman-dilimi akışıyla geriye dönük uyumluluk
