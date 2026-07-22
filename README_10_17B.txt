AlphaScan PRO Sprint 10.17B — 7/24 Paper Trading Mode

1) Paketi proje ana klasörüne çıkarın.
2) py -3.13 .\apply_sprint10_17b.py
3) py -3.13 .\verify_sprint10_17b.py
4) py -3.13 .\paper_trading_control.py start
5) py -3.13 .\paper_trading_control.py status
6) Background Worker çalışmıyorsa:
   py -3.13 .\background_worker.py

Sadece kriptoyu açmak:
py -3.13 .\paper_trading_control.py start --market KRIPTO

Durdurmak:
py -3.13 .\paper_trading_control.py stop

Bu mod gerçek emir göndermez. Robot hesaplarını ve Background Worker robot bayraklarını birlikte açar.
