"""
sinyal.py - Acilis hacmi anomali sinyali.

Mantik: Gunun ILK saatlik bari = acilis seansi. O gunun acilis hacmi, onceki
N gunun acilis hacmi ortalamasinin 'kat' katindan buyukse -> "para girisi" sinyali.

Lookahead yok: bugunun sinyali SADECE oncesi gunlerin verisiyle hesaplanir
(baseline shift(1) ile gecikir). Giris ise gunun IKINCI barinin acilisinda
yapilir (cunku ilk barin tam hacmi ancak o bar kapaninca bilinir).

Bir gunun "acilis ozellikleri":
  acilis_hacim   : ilk barin hacmi (adet)
  acilis_ciro    : ilk barin Open * Volume  (TL proxy - senin takip ettigin sayi)
  giris_fiyat    : ikinci barin Open'i (lookahead-safe giris)
  gun_barlari    : o gunun 2. bardan itibaren OHLC barlari (cikis simulasyonu icin)
"""
from __future__ import annotations
import pandas as pd


def gunluk_acilis(df: pd.DataFrame) -> pd.DataFrame:
    """Saatlik df'ten gun bazli acilis tablosu uretir.

    Doner: index=tarih(date), kolonlar: acilis_hacim, acilis_ciro, giris_fiyat,
           bar_sayisi. Cikis simulasyonu icin ham gun-gruplari ayri tutulur.
    """
    if len(df) == 0:
        return pd.DataFrame()
    g = df.copy()
    g["_tarih"] = g.index.date
    satirlar = []
    for tarih, gun in g.groupby("_tarih", sort=True):
        gun = gun.sort_index()
        if len(gun) < 2:
            continue  # yarim gun / tek bar -> islem yapilamaz
        ilk = gun.iloc[0]
        ikinci = gun.iloc[1]
        satirlar.append({
            "tarih": tarih,
            "acilis_hacim": float(ilk["Volume"]),
            "acilis_ciro": float(ilk["Open"]) * float(ilk["Volume"]),
            "giris_fiyat": float(ikinci["Open"]),
            "bar_sayisi": len(gun),
        })
    return pd.DataFrame(satirlar).set_index("tarih") if satirlar else pd.DataFrame()


def sinyal_uret(df: pd.DataFrame, baseline_gun: int = 10, kat: float = 3.0,
                min_ciro_tl: float = 200_000) -> pd.DataFrame:
    """Her gun icin sinyal (bool) ve gerekce metriklerini ekler.

    baseline_gun : kac gunluk acilis hacmi ortalamasina bakilacak
    kat          : acilis hacmi ortalamanin kac katini gecerse sinyal
    min_ciro_tl  : likidite tabani - cok olu paylarda sahte kat patlamasini ele

    Lookahead-safe: baseline shift(1) ile, sinyal gunu HARIC onceki gunlerden.
    """
    t = gunluk_acilis(df)
    if len(t) == 0:
        return t
    # Onceki N gunun ortalamasi (bugunu DAHIL ETMEDEN)
    t["baseline"] = t["acilis_hacim"].rolling(baseline_gun, min_periods=baseline_gun) \
                                     .mean().shift(1)
    t["kat_gerceklesen"] = t["acilis_hacim"] / t["baseline"]
    t["sinyal"] = (
        (t["kat_gerceklesen"] >= kat)
        & (t["acilis_ciro"] >= min_ciro_tl)
        & t["baseline"].notna()
    )
    return t


if __name__ == "__main__":
    # Sentetik dogrulama: 30 gun normal, sonra 1 gun patlama
    import numpy as np
    rng = np.random.default_rng(0)
    gunler = pd.date_range("2025-01-01 10:00", periods=40, freq="B", tz="Europe/Istanbul")
    rows = []
    for d in gunler:
        for h in range(8):  # gunde 8 saatlik bar
            ts = d + pd.Timedelta(hours=h)
            hac = rng.integers(50_000, 80_000)
            rows.append((ts, 4.0, 4.05, 3.95, 4.0, hac))
    sdf = pd.DataFrame(rows, columns=["ts", "Open", "High", "Low", "Close", "Volume"]).set_index("ts")
    # 35. gunun acilis hacmini 10x yap
    patlama_gun = gunler[35].date()
    mask = (sdf.index.date == patlama_gun) & (sdf.index.hour == 10)
    sdf.loc[mask, "Volume"] *= 12
    out = sinyal_uret(sdf, baseline_gun=10, kat=3.0, min_ciro_tl=100_000)
    print(out[["acilis_hacim", "baseline", "kat_gerceklesen", "sinyal"]].tail(8))
