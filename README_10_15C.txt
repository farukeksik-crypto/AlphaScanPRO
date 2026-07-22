AlphaScan PRO — Sprint 10.15C
Robot Risk Enforcement

Eklenenler:
- PortfolioRiskManager'ın gerçek robot pozisyon açma akışına bağlanması
- İşlem öncesi APPROVED / REDUCED / REJECTED kararı
- Portföy limitlerine göre pozisyon miktarının otomatik küçültülmesi
- Günlük zarar, toplam risk, toplam maruziyet, sembol ve grup limitleri
- Kalıcı acil risk kilidi ve manuel sıfırlama
- robot_risk_events denetim günlüğü
- Ret, küçültme ve onay kararlarının neden ve metriklerle kaydı
- 10.15A ve 10.15B geriye dönük uyumluluk testleri

Kurulum:
1) ZIP içeriğini proje ana klasörüne çıkarın.
2) py -3.13 .\apply_sprint10_15c.py
3) py -3.13 .\verify_sprint10_15c.py
4) py -3.13 -m streamlit run app.py

Commit:
git add .
git commit -m "Sprint 10.15C robot risk enforcement"
