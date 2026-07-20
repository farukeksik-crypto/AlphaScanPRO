from __future__ import annotations

import streamlit as st

COMMON = {
    "NET AL": "Teknik koşulların büyük bölümünün aynı anda olumlu olduğu en güçlü aday sınıfıdır; tek başına kesin alım emri değildir.",
    "AL ADAY": "Olumlu sinyal üretmiş ancak ek teyit bekleyen varlığı ifade eder.",
    "Teknik Puan": "Trend, momentum, hacim ve gösterge koşullarının 100 puanlık birleşik sonucudur.",
    "Güven Puanı": "Sinyalin veri kalitesi, gösterge uyumu ve geçmiş başarı ölçütleriyle hesaplanan güven derecesidir.",
    "Başarı Göstergesi": "Benzer sinyallerin geçmiş testlerdeki sonuçlarından türetilen olasılık göstergesidir; garanti değildir.",
    "Risk Seviyesi": "Fiyat oynaklığı, stop mesafesi ve sinyal belirsizliğine göre Düşük, Orta veya Yüksek olarak sınıflandırılır.",
    "Stop": "Zararın kontrol altında tutulması amacıyla pozisyonun kapatılmasının planlandığı fiyat seviyesidir.",
    "Hedef 1 / Hedef 2": "Kârın kademeli alınmasının planlandığı fiyat bölgeleridir.",
    "RSI": "Göreceli Güç Endeksi; 0-100 arasında momentumu ölçer. Genellikle 70 üzeri aşırı alım, 30 altı aşırı satım kabul edilir.",
    "EMA20 / EMA50 / EMA200": "Üssel hareketli ortalamalardır. Sırasıyla kısa, orta ve uzun vadeli trendi izlemek için kullanılır.",
    "MACD": "İki hareketli ortalama arasındaki ilişkiyi ölçerek trend ve momentum değişimini gösterir.",
    "ADX": "Trend yönünü değil gücünü ölçer. 20-25 üzerindeki değerler belirgin trend oluşumuna işaret edebilir.",
    "ATR": "Ortalama Gerçek Aralık; fiyat oynaklığını ölçer ve stop mesafesi belirlemede kullanılır.",
    "Hacim": "Belirli sürede gerçekleşen işlem miktarıdır. Fiyat hareketinin piyasa katılımıyla desteklenip desteklenmediğini gösterir.",
    "K/Z": "Kâr/Zarar kısaltmasıdır.",
}

FINANCIAL = {
    "F/K": "Fiyat/Kazanç oranıdır. Hisse fiyatının yıllık hisse başına kârın kaç katı olduğunu gösterir; sektör ve büyüme ile birlikte değerlendirilmelidir.",
    "PD/DD": "Piyasa Değeri/Defter Değeri oranıdır. Şirketin özkaynaklarına göre nasıl fiyatlandığını gösterir.",
    "ROE": "Özsermaye kârlılığıdır. Şirketin ortakların sermayesini ne kadar verimli kullandığını ölçer.",
    "ROA": "Aktif kârlılığıdır. Şirketin toplam varlıklarından ne kadar kâr ürettiğini gösterir.",
    "FAVÖK": "Faiz, amortisman ve vergi öncesi kârdır; ana faaliyet performansını karşılaştırmada kullanılır.",
    "FD/FAVÖK": "Firma Değeri/FAVÖK oranıdır. Borç ve nakdi de hesaba katan değerleme göstergesidir.",
    "Net Borç/FAVÖK": "Şirketin net borcunun faaliyet kârıyla kaç yılda karşılanabileceğini yaklaşık olarak gösterir.",
    "PEG": "F/K oranını kâr büyümesiyle birlikte değerlendirir. Tek başına kullanılmamalıdır.",
    "Cari Oran": "Dönen varlıkların kısa vadeli borçlara oranıdır; kısa vadeli ödeme gücünü gösterir.",
    "Asit-Test Oranı": "Stoklar hariç likit varlıkların kısa vadeli borçları karşılama gücünü gösterir.",
    "Borç/Özsermaye": "Toplam borcun özkaynağa oranıdır. Yüksek değer finansal kaldıraç ve riskin arttığına işaret edebilir.",
    "Net Kâr Marjı": "Her 100 TL satıştan kaç TL net kâr kaldığını gösterir.",
    "Brüt Kâr Marjı": "Satışlardan ürün/hizmet maliyeti çıkarıldıktan sonra kalan marjı gösterir.",
    "Faaliyet Kâr Marjı": "Şirketin ana faaliyetlerinden elde ettiği kârın satışlara oranıdır.",
    "Serbest Nakit Akışı": "Faaliyet nakit akışından yatırım harcamaları çıkarıldıktan sonra kalan nakittir.",
    "Faaliyet Nakit Akışı": "Şirketin esas faaliyetlerinden ürettiği gerçek nakdi gösterir.",
    "Ciro Büyümesi": "Satış gelirlerinin önceki döneme göre artış oranıdır.",
    "Kâr Büyümesi": "Net kârın önceki döneme göre değişim oranıdır.",
    "Beta": "Hissenin piyasa hareketlerine duyarlılığını ölçer; 1 üzeri genellikle daha yüksek oynaklık anlamına gelir.",
}

PAGE_TERMS = {
    "Bilanço ve Yapay Zekâ Analizi": [*FINANCIAL.keys(), "RSI", "EMA20 / EMA50 / EMA200"],
    "Sanal İşlem Robotu": ["NET AL", "AL ADAY", "Teknik Puan", "Güven Puanı", "Başarı Göstergesi", "Risk Seviyesi", "Stop", "Hedef 1 / Hedef 2", "K/Z"],
    "Kripto": ["NET AL", "AL ADAY", "Teknik Puan", "RSI", "EMA20 / EMA50 / EMA200", "MACD", "ADX", "ATR", "Hacim", "Risk Seviyesi"],
    "Emtia": ["NET AL", "AL ADAY", "Teknik Puan", "RSI", "EMA20 / EMA50 / EMA200", "MACD", "ADX", "ATR", "Risk Seviyesi"],
    "Arındırma 0": ["NET AL", "AL ADAY", "Teknik Puan", "RSI", "EMA20 / EMA50 / EMA200", "MACD", "ADX", "Hacim"],
    "Katılım Tüm": ["NET AL", "AL ADAY", "Teknik Puan", "RSI", "EMA20 / EMA50 / EMA200", "MACD", "ADX"],
    "Katılım 100": ["NET AL", "AL ADAY", "Teknik Puan", "RSI", "EMA20 / EMA50 / EMA200", "MACD", "ADX"],
    "Göreceli Güç": ["Teknik Puan", "RSI", "EMA20 / EMA50 / EMA200", "Hacim"],
    "Geçmiş Strateji Testi": ["K/Z", "Stop", "Hedef 1 / Hedef 2", "Teknik Puan", "Risk Seviyesi"],
    "Strateji Laboratuvarı": ["K/Z", "Stop", "Teknik Puan", "Risk Seviyesi"],
    "Ana Panel": ["NET AL", "AL ADAY", "Teknik Puan", "Güven Puanı", "Risk Seviyesi", "K/Z"],
}


def render_page_glossary(page: str) -> None:
    terms = PAGE_TERMS.get(page, ["Teknik Puan", "Güven Puanı", "Risk Seviyesi", "K/Z"])
    source = {**COMMON, **FINANCIAL}
    with st.expander("📘 Terimler ve Kısaltmalar — Anlamı ve Önemi"):
        for term in terms:
            explanation = source.get(term)
            if explanation:
                st.markdown(f"**{term}:** {explanation}")
        st.caption("Göstergeler tek başına karar vermek için yeterli değildir; piyasa koşulları ve risk yönetimiyle birlikte değerlendirilmelidir.")
