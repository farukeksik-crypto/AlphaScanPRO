from datetime import datetime
import streamlit as st


def render_dashboard(cache_engine):
    st.title("🏠 AlphaScan PRO Dashboard")

    cache_status = cache_engine.status()
    c1, c2, c3 = st.columns(3)
    c1.metric("Sistem", "Aktif")
    c2.metric("Cache kaydı", len(cache_status))
    c3.metric("Saat", datetime.now().strftime("%H:%M:%S"))

    st.info(
        "Sprint 2: Arındırma 0, kripto ve emtia taramaları ortak sinyal motorunu kullanır."
    )

    st.subheader("Başarı kriteri")
    st.markdown(
        """
        - Veri kaynakları çalışmalı  
        - Tarama sonucu tabloya gelmeli  
        - Hata varsa sembol ve nedeni açıkça görünmeli  
        - İkinci tarama cache sayesinde daha hızlı tamamlanmalı
        """
    )
