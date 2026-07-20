from __future__ import annotations

from typing import Any


class NotificationManager:
    """
    AlphaScan PRO bildirim yöneticisi.

    Şimdilik bildirimleri yalnızca log dosyasına yazar.
    Telegram, e-posta veya masaüstü bildirimi daha sonra eklenebilir.
    """

    def __init__(self, database, settings, logger):
        self.database = database
        self.settings = settings
        self.logger = logger

    def send(
        self,
        event_type: str,
        title: str,
        message: str,
        payload: dict[str, Any] | None = None,
    ) -> bool:
        payload = payload or {}

        try:
            self.logger.info(
                "BİLDİRİM | tür=%s | başlık=%s | mesaj=%s | veri=%s",
                event_type,
                title,
                message,
                payload,
            )
            return True

        except Exception:
            # Bildirim hatası robotu veya taramayı durdurmamalı.
            try:
                self.logger.exception(
                    "Bildirim kaydedilemedi: %s | %s",
                    event_type,
                    title,
                )
            except Exception:
                pass

            return False