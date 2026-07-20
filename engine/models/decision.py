from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class Decision:
    """
    Signal Engine tarafından üretilen tip güvenli karar sonucu.

    Bu model hesaplama yapmaz; yalnızca teknik karar, güven seviyesi,
    pozisyon katsayısı, risk seviyeleri ve açıklama alanlarını taşır.
    """

    ok: bool
    action: str
    quality: str
    score: float
    reason: str

    price: float
    stop: float
    target1: float
    target2: float

    risk_reward1: float
    risk_reward2: float

    rsi: float | None = None
    adx: float | None = None

    # Güven puanı işlemi doğrudan engellemez.
    # Pozisyon büyüklüğünü ve sinyal sınıfını destekler.
    confidence: float = 0.0
    position_multiplier: float = 0.25

    @property
    def decision(self) -> str:
        """Eski isimlendirmeyle uyumluluk sağlar."""
        return self.action

    @property
    def confidence_label(self) -> str:
        """Güven puanını okunabilir bir sınıfa dönüştürür."""

        if self.confidence >= 80:
            return "ÇOK GÜÇLÜ"

        if self.confidence >= 65:
            return "GÜÇLÜ"

        if self.confidence >= 50:
            return "NORMAL"

        return "ZAYIF"

    @property
    def suggested_position_percent(self) -> float:
        """
        Pozisyon katsayısını yüzde olarak döndürür.

        Örnek:
        0.75 katsayısı -> %75 pozisyon kullanımı
        """

        return round(self.position_multiplier * 100, 2)

    def to_dict(self) -> dict[str, Any]:
        """
        Eski sözlük tabanlı modüller için geriye uyumlu çıktı üretir.
        """

        result = asdict(self)
        result["decision"] = result.pop("action")
        result["confidence_label"] = self.confidence_label
        result["suggested_position_percent"] = (
            self.suggested_position_percent
        )

        return result