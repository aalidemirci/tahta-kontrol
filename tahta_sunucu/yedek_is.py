"""Otomatik yedeği ana zamanlayıcıyı bekletmeden, tek iş olarak yürütür."""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable

gunluk = logging.getLogger("tahta-sunucu")


class YedekIsleyici:
    def __init__(self):
        self._kilit = threading.Lock()
        self._kapandi = False
        self._parca: threading.Thread | None = None

    def baslat(self, is_: Callable[[], object]) -> bool:
        """Önceki iş sürüyorsa veya kapanış başladıysa bu turu atlar."""
        with self._kilit:
            if self._kapandi or (self._parca is not None and self._parca.is_alive()):
                return False
            parca = threading.Thread(target=self._calistir, args=(is_,), name="otomatik-yedek", daemon=True)
            parca.start()
            self._parca = parca
            return True

    @staticmethod
    def _calistir(is_: Callable[[], object]) -> None:
        baslangic = time.monotonic()
        try:
            is_()
        except Exception:
            gunluk.exception("Otomatik yedek işi başarısız")
        finally:
            gunluk.debug("Otomatik yedek işi %.2f saniyede tamamlandı.", time.monotonic() - baslangic)

    def durdur(self, zaman_asimi: float = 0) -> bool:
        """Yeni işleri engeller; süren işi verilen süre kadar bekler. I/O zorla kesilmez."""
        with self._kilit:
            self._kapandi = True
            parca = self._parca
        if parca is not None:
            parca.join(timeout=zaman_asimi)
            return not parca.is_alive()
        return True
