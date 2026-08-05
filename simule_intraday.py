"""Intraday TP/SL simulasyonu — seans filtresi, OHLC yolu, acilis SL gecikmesi."""
from __future__ import annotations

import datetime as dt
from typing import Optional, Tuple

import pandas as pd

ACILIS = dt.time(10, 0)
SL_BASLA = dt.time(10, 15)  # acilis dalgalanmasi / kotu wick korumasi


def _bar_time(idx) -> dt.time:
    ts = idx.to_pydatetime() if hasattr(idx, "to_pydatetime") else idx
    if hasattr(ts, "tzinfo") and ts.tzinfo is not None:
        ts = ts.astimezone().replace(tzinfo=None)
    return ts.time()


def seans_filtre(gun: pd.DataFrame) -> pd.DataFrame:
    """10:00 oncesi barlari at."""
    if len(gun) == 0:
        return gun
    g = gun.sort_index()
    return g[[_bar_time(i) >= ACILIS for i in g.index]]


def _ohlc_path(o: float, h: float, l: float, c: float) -> list[float]:
    return [o, h, l, c] if c >= o else [o, l, h, c]


def simule_gun(
    gun: pd.DataFrame,
    giris: float,
    target: float = 0.03,
    stop: float = 0.03,
    sl_basla: Optional[dt.time] = SL_BASLA,
) -> Tuple[str, float, str]:
    """
    Donus: (sebep, cikis_fiyat, cikis_saat)
    sebep: hedef | stop | gun_sonu
    """
    g = seans_filtre(gun)
    if len(g) == 0:
        g = gun.sort_index()
    else:
        g = g.sort_index()

    tp, sl = giris * (1 + target), giris * (1 - stop)

    for i in range(len(g)):
        row = g.iloc[i]
        o, h, l, c = float(row.Open), float(row.High), float(row.Low), float(row.Close)
        ts = _bar_time(g.index[i])
        sl_aktif = sl_basla is None or ts >= sl_basla

        for p in _ohlc_path(o, h, l, c):
            if p >= tp:
                return "hedef", tp, str(g.index[i])[11:16]
            if sl_aktif and p <= sl:
                return "stop", sl, str(g.index[i])[11:16]

    c = float(g.iloc[-1].Close)
    return "gun_sonu", c, str(g.index[-1])[11:16]


def simule_tut(
    gun_by_day: dict,
    gun_list: list,
    giris: float,
    target: float = 0.03,
    stop: float = 0.03,
    max_gun: Optional[int] = None,
) -> Tuple[str, float, str, int]:
    """
  Cok gunlu tutma: TP/SL'ye ulasana kadar devam et.
  max_gun: None=sınırsız; 3=ilk 3 islem gunu sonra kapanis (max_gun sebep).
  Donus: (sebep, cikis, nerede, tut_gun)
  """
    if max_gun is not None and max_gun > 0:
        gun_list = gun_list[:max_gun]
    tp, sl = giris * (1 + target), giris * (1 - stop)
    for di, gun_dt in enumerate(gun_list):
        gun = gun_by_day.get(gun_dt)
        if gun is None or len(gun) == 0:
            continue
        g = seans_filtre(gun)
        if len(g) == 0:
            g = gun.sort_index()
        for i in range(len(g)):
            row = g.iloc[i]
            o, h, l, c = float(row.Open), float(row.High), float(row.Low), float(row.Close)
            if di > 0 and i == 0:
                if o >= tp:
                    return "hedef", tp, f"{gun_dt} acilis", di
                if o <= sl:
                    return "stop", sl, f"{gun_dt} acilis", di
            sl_aktif = di > 0 or _bar_time(g.index[i]) >= SL_BASLA
            for p in _ohlc_path(o, h, l, c):
                if p >= tp:
                    return "hedef", tp, f"{gun_dt} {str(g.index[i])[11:16]}", di
                if sl_aktif and p <= sl:
                    return "stop", sl, f"{gun_dt} {str(g.index[i])[11:16]}", di
        if di < len(gun_list) - 1:
            continue
    last = gun_list[-1]
    g = seans_filtre(gun_by_day[last])
    if len(g) == 0:
        g = gun_by_day[last].sort_index()
    sebep = "max_gun" if max_gun is not None else "veri_bitti"
    return sebep, float(g.iloc[-1].Close), f"{last} kapanis", len(gun_list) - 1


def simule_gun_eski(gun: pd.DataFrame, giris: float, target: float = 0.03, stop: float = 0.03):
    """Eski mantik: stop-first, seans filtresi yok."""
    tp, sl = giris * (1 + target), giris * (1 - stop)
    g = gun.sort_index()
    for i in range(len(g)):
        hi, lo = float(g.iloc[i].High), float(g.iloc[i].Low)
        if hi >= tp and lo <= sl:
            return "stop", sl, str(g.index[i])[11:16]
        if hi >= tp:
            return "hedef", tp, str(g.index[i])[11:16]
        if lo <= sl:
            return "stop", sl, str(g.index[i])[11:16]
    c = float(g.iloc[-1].Close)
    return "gun_sonu", c, str(g.index[-1])[11:16]
