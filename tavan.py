"""BIST tavan acilis kontrolu — pozisyon acilamaz."""
from __future__ import annotations

TAVAN_10 = 0.095
TAVAN_20 = 0.195
TOL = 0.004


def tavan_fiyat(prev_close: float, oran: float = 0.10) -> float:
    return prev_close * (1 + oran)


def tavan_acilis_mi(open_: float, prev_close: float, high: float | None = None) -> bool:
    """Onceki kapanisa gore %10/%20 bant tavan acilisi."""
    if prev_close <= 0 or open_ <= 0:
        return False
    chg = open_ / prev_close - 1
    for oran, esik in ((0.10, TAVAN_10), (0.20, TAVAN_20)):
        tv = tavan_fiyat(prev_close, oran)
        fiyat_yakin = open_ >= tv * (1 - TOL) or abs(open_ - tv) / tv < TOL
        if chg >= esik or (fiyat_yakin and chg >= esik - 0.01):
            return True
    return False


def tavan_detay(open_: float, prev_close: float, high: float | None = None) -> dict:
    if prev_close <= 0 or open_ <= 0:
        return {"tavan": False, "neden": ""}
    chg = open_ / prev_close - 1
    for oran, esik in ((0.10, TAVAN_10), (0.20, TAVAN_20)):
        tv = tavan_fiyat(prev_close, oran)
        fiyat_yakin = open_ >= tv * (1 - TOL) or abs(open_ - tv) / tv < TOL
        if chg >= esik or (fiyat_yakin and chg >= esik - 0.01):
            tavan_kilit = high is not None and high > 0 and (high - open_) / open_ < 0.005
            return {
                "tavan": True,
                "bant_%": int(oran * 100),
                "degisim_%": round(chg * 100, 2),
                "tavan_fiyat": round(tv, 4),
                "tavan_kilit": tavan_kilit,
                "neden": f"acilis +{chg*100:.1f}% (~%{int(oran*100)} bant)"
                + (" | tavanda kilit" if tavan_kilit else ""),
            }
    return {"tavan": False, "neden": "", "degisim_%": round(chg * 100, 2)}
