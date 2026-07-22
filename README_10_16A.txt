AlphaScan PRO - Sprint 10.16A Market Intelligence Core

Eklenenler:
- Ham OHLCV verisinden EMA, RSI, MACD, ATR ve ADX üretimi
- BULL / RECOVERY / SIDEWAYS / WEAK / BEAR rejim sınıflandırması
- LOW / MEDIUM / HIGH / EXTREME volatilite seviyesi
- Trend gücü, momentum ve likidite puanları
- Güven puanı ve robot modu: NORMAL / TEMKİNLİ / SAVUNMACI / VERİ BEKLE
- Volatiliteye duyarlı risk ve maksimum pozisyon çarpanları
- Streamlit menüsünde Market Intelligence ekranı
- Eski MarketRegimeEngine kullanımıyla geriye dönük uyumluluk

Kurulum:
py -3.13 .\apply_sprint10_16a.py
py -3.13 .\verify_sprint10_16a.py
py -3.13 -m streamlit run app.py

Commit:
git add .
git commit -m "Sprint 10.16A market intelligence core"
