"""
backtest.py - Olay-tabanli (event-driven) gun-ici backtest.

Strateji:
  - Sinyal gunu (acilis hacmi patlamasi) tespit edilirse,
  - giris = o gunun 2. saatlik barinin Open'i,
  - cikis = gun icinde once HEDEF'e (+%X) ulasirsa kar al,
           once STOP'a (-%Y) ulasirsa zarar kes,
           ikisi de olmazsa gun sonu (son bar Close) kapat.
  - Ayni saatlik barda hem hedef hem stop gorulurse: STOP ilk varsayilir (konservatif).

Maliyet: her islemde (komisyon + slippage) x 2 (giris + cikis) dusulur.
DUSUK HACIMLI paylarda slippage komisyondan cok daha buyuk olur - parametreyi
ona gore yuksek tut.

ASLA sadece toplam getiri rapor etme: beklenen deger, profit factor, win-rate,
ort kazanc/kayip birlikte verilir.
"""
from __future__ import annotations
import numpy as np
import pandas as pd

from sinyal import sinyal_uret


def _gun_barlari(df: pd.DataFrame):
    g = df.copy()
    g["_t"] = g.index.date
    return {t: gun.sort_index() for t, gun in g.groupby("_t")}


def islemleri_uret(df: pd.DataFrame, hedef: float, stop: float = 0.02,
                   baseline_gun: int = 10, kat: float = 3.0,
                   min_ciro_tl: float = 200_000,
                   komisyon: float = 0.0005, slippage: float = 0.003) -> pd.DataFrame:
    """Tek hisse icin tum sinyal gunlerinde islem simule eder.

    hedef/stop oran (0.03 = %3). Doner: islem tablosu (tarih, sonuc, getiri_net...).
    """
    sig = sinyal_uret(df, baseline_gun, kat, min_ciro_tl)
    if len(sig) == 0:
        return pd.DataFrame()
    gunler = _gun_barlari(df)
    maliyet = (komisyon + slippage) * 2  # giris + cikis
    islemler = []
    for tarih, satir in sig[sig["sinyal"]].iterrows():
        gun = gunler.get(tarih)
        if gun is None or len(gun) < 2:
            continue
        giris = satir["giris_fiyat"]
        if not np.isfinite(giris) or giris <= 0:
            continue
        hedef_fiyat = giris * (1 + hedef)
        stop_fiyat = giris * (1 - stop)
        sonuc, cikis_fiyat = None, None
        # 2. bardan itibaren gun-ici barlari yuru
        for _, bar in gun.iloc[1:].iterrows():
            # Konservatif: once stop kontrol (ayni barda ikisi de olursa stop)
            if bar["Low"] <= stop_fiyat:
                sonuc, cikis_fiyat = "stop", stop_fiyat
                break
            if bar["High"] >= hedef_fiyat:
                sonuc, cikis_fiyat = "hedef", hedef_fiyat
                break
        if sonuc is None:  # gun sonu kapat
            sonuc, cikis_fiyat = "kapanis", gun.iloc[-1]["Close"]
        brut = cikis_fiyat / giris - 1
        net = brut - maliyet
        islemler.append({
            "tarih": tarih, "giris": giris, "cikis": cikis_fiyat,
            "sonuc": sonuc, "getiri_brut": brut, "getiri_net": net,
            "kat": satir["kat_gerceklesen"], "acilis_ciro": satir["acilis_ciro"],
        })
    return pd.DataFrame(islemler)


def metrikler(islem_df: pd.DataFrame) -> dict:
    """Islem-bazli dururst metrikler. Kazanma orani TEK BASINA yetmez;
    asil olcu beklenen deger ve profit factor."""
    if len(islem_df) == 0:
        return {"islem_sayisi": 0, "not": "sinyal/islem yok"}
    r = islem_df["getiri_net"]
    kazanan, kaybeden = r[r > 0], r[r < 0]
    pf = (kazanan.sum() / abs(kaybeden.sum())) if len(kaybeden) and kaybeden.sum() != 0 else float("inf")
    win = len(kazanan) / len(r)
    beklenen_deger = r.mean()  # islem basina ortalama net getiri (edge'in ozu)
    # Esit-agirlik, ardisik bilesik egri (pozisyon boyutu ayri konu)
    equity = (1 + r).cumprod()
    zirve = equity.cummax()
    maxdd = (equity / zirve - 1).min()
    return {
        "islem_sayisi": int(len(r)),
        "kazanma_orani_%": round(win * 100, 1),
        "beklenen_deger_islem_%": round(beklenen_deger * 100, 3),
        "profit_factor": round(pf, 2) if np.isfinite(pf) else "inf",
        "ort_kazanc_%": round(kazanan.mean() * 100, 2) if len(kazanan) else 0.0,
        "ort_kayip_%": round(kaybeden.mean() * 100, 2) if len(kaybeden) else 0.0,
        "bilesik_getiri_%": round((equity.iloc[-1] - 1) * 100, 1),
        "max_drawdown_%": round(maxdd * 100, 1),
        "hedefe_ulasma_%": round((islem_df["sonuc"] == "hedef").mean() * 100, 1),
        "stop_olma_%": round((islem_df["sonuc"] == "stop").mean() * 100, 1),
    }


def hedef_taramasi(df_dict: dict, hedefler=(0.01, 0.03, 0.05), stop: float = 0.02,
                   **kw) -> pd.DataFrame:
    """Coklu hisse + coklu hedef. df_dict: {hisse: saatlik_df}.
    Her hedef icin tum hisselerin islemlerini birlestirip metrik uretir."""
    ozet = []
    detay = {}
    for hedef in hedefler:
        hepsi = []
        for hisse, df in df_dict.items():
            it = islemleri_uret(df, hedef=hedef, stop=stop, **kw)
            if len(it):
                it = it.assign(hisse=hisse)
                hepsi.append(it)
        birlesik = pd.concat(hepsi, ignore_index=True) if hepsi else pd.DataFrame()
        detay[hedef] = birlesik
        m = metrikler(birlesik)
        m = {"hedef_%": round(hedef * 100, 1), "stop_%": round(stop * 100, 1), **m}
        ozet.append(m)
    return pd.DataFrame(ozet), detay


if __name__ == "__main__":
    # Sentetik dogrulama
    rng = np.random.default_rng(1)
    gunler = pd.date_range("2025-01-01 10:00", periods=60, freq="B", tz="Europe/Istanbul")
    rows = []
    for d in gunler:
        taban = 4.0 + rng.normal(0, 0.02)
        patlama = rng.random() < 0.15  # %15 gun sinyal benzeri
        for h in range(8):
            ts = d + pd.Timedelta(hours=h)
            hac = rng.integers(50_000, 80_000) * (12 if (patlama and h == 0) else 1)
            drift = 0.012 if (patlama and h > 0) else 0.0  # sinyal gunu hafif yukari
            px = taban * (1 + drift * h + rng.normal(0, 0.004))
            rows.append((ts, px, px * 1.012, px * 0.992, px, hac))
    sdf = pd.DataFrame(rows, columns=["ts", "Open", "High", "Low", "Close", "Volume"]).set_index("ts")
    ozet, _ = hedef_taramasi({"TEST": sdf}, baseline_gun=10, kat=3.0, min_ciro_tl=100_000)
    print(ozet.to_string(index=False))
