AlphaScan PRO — Sprint 10.20B
Evren Bazlı Bağımsız Sanal Hesaplar

Eklenenler
- BIST Katılım için bağımsız sanal hesap: 10.000.000 TRY
- Arındırma 0 için bağımsız sanal hesap: 10.000.000 TRY
- Tüm BIST için bağımsız sanal hesap: 25.000.000 TRY
- Kripto ve emtia hesapları korunur.
- Background Orchestrator, BIST robotunu evren adına göre doğru hesaba yönlendirir.
- Her hesabın nakdi, açık pozisyonları, K/Z ve robot ayarları birbirinden ayrıdır.
- Eski BIST işlemleri bist_main hesabında korunur; geçmiş veri taşınmaz veya silinmez.
- Evren Yöneticisi ekranına bağımsız hesap durum tablosu eklenir.
- robot_accounts tablosundaki eski piyasa UNIQUE kısıtı güvenli biçimde kaldırılır.

Kurulum
1) ZIP içeriğini proje ana klasörüne çıkarın.
2) py -3.13 .\apply_sprint10_20b.py
3) py -3.13 .\verify_sprint10_20b.py
4) py -3.13 .\capital_control.py status
5) Background Worker'ı yeniden başlatın.

Git
 git add engine/market_accounts.py engine/paper_capital_manager.py engine/background_orchestrator.py database/robot_migrations.py ui/universe_manager_page.py capital_control.py tests/test_multi_universe_accounts_10_20b.py apply_sprint10_20b.py verify_sprint10_20b.py README_10_20B.txt
 git commit -m "Sprint 10.20B independent BIST universe accounts"
