"""Dinamik 5x canli tarama — hacim Nx oldugu saatte DIP+KIRILIM."""
from __future__ import annotations
import argparse
import datetime as dt
import sys
import time

import pandas as pd
from evren import evren_yukle
from portfoy_compound import gunluk
from portfoy_dinamik_kat import (
    baseline_kum_saat, tetik_bul, giris_15dk, MAX_SAAT_BAR,
)
from veri_cache import cek_saatlik, cek_15dk


def tara_hisse(h, p, bl_cache, bugun):
    if h not in bl_cache:
        hourly = cek_saatlik(h, tv_user=p.tv_user, tv_pass=p.tv_pass, yenile=p.yenile)
        if len(hourly) == 0:
            bl_cache[h] = None
            return None
        d = gunluk(hourly)
        if len(d) < p.hafta52 + 5:
            bl_cache[h] = None
            return None
        bl_cache[h] = {
            "bl_saat": baseline_kum_saat(hourly, p.baseline),
            "hi52": d["High"].rolling(p.hafta52, min_periods=p.hafta52 // 2).max().shift(1),
            "lo52": d["Low"].rolling(p.hafta52, min_periods=p.hafta52 // 2).min().shift(1),
            "dunk": d["Close"].shift(1),
            "hourly_days": {t: g.sort_index() for t, g in hourly.groupby(hourly.index.date)},
        }
    meta = bl_cache[h]
    if meta is None or bugun not in meta["hourly_days"]:
        return None

    dk = cek_15dk(h, tv_user=p.tv_user, tv_pass=p.tv_pass, yenile=p.yenile)
    if len(dk) == 0:
        return None
    gm = dk.sort_index().copy()
    gm["_t"] = gm.index.date
    by_dk = {t: g.sort_index() for t, g in gm.groupby("_t")}
    if bugun not in by_dk:
        return None

    gun_h = meta["hourly_days"][bugun]
    gun_dk = by_dk[bugun]
    tetik = tetik_bul(gun_h, meta["bl_saat"], p.min_kat)
    if tetik is None:
        return None
    bar_i, kat, kapanis, kum_vol = tetik
    entry_idx, giris = giris_15dk(gun_dk, kapanis)
    if entry_idx is None or giris <= 0:
        return None

    hi52, lo52 = meta["hi52"], meta["lo52"]
    if bugun not in hi52.index or pd.isna(hi52.loc[bugun]) or pd.isna(lo52.loc[bugun]):
        return None
    H, L = float(hi52.loc[bugun]), float(lo52.loc[bugun])
    if H <= L:
        return None
    if giris * kum_vol < p.min_ciro:
        return None

    tepe = float(gun_dk.iloc[: entry_idx + 1]["High"].max())
    pos52 = (giris - L) / (H - L)
    dunk = float(meta["dunk"].loc[bugun]) if bugun in meta["dunk"].index else float("nan")
    taze = (dunk < H) and (tepe >= H)
    if pos52 <= p.dip_esik:
        grup = "DIP"
    elif taze:
        grup = "KIRILIM"
    elif pos52 >= p.ust_esik:
        return None
    else:
        return None

    acilis = float(gun_dk.iloc[0]["Open"])
    chase = (giris - acilis) / acilis if acilis > 0 else 0
    return {
        "hisse": h, "kat": round(kat, 1), "grup": grup,
        "pos52": round(pos52, 2), "giris": round(giris, 3),
        "acilis": round(acilis, 3), "chase_%": round(chase * 100, 2),
        "giris_saat": str(gun_dk.index[entry_idx])[:16],
        "tetik_bar": bar_i + 1,
        "ciro_TL": int(giris * kum_vol),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--evren", default="evren_kucuk.csv")
    ap.add_argument("--min_kat", type=float, default=5.0)
    ap.add_argument("--tarih", default=None, help="YYYY-MM-DD (varsayilan bugun)")
    ap.add_argument("--yenile", action="store_true")
    ap.add_argument("--bekle", type=float, default=0.35)
    a = ap.parse_args()

    class Cfg:
        evren = a.evren
        tv_user = tv_pass = None
        baseline = 20
        hafta52 = 252
        dip_esik = 0.20
        ust_esik = 0.80
        min_ciro = 200_000
        min_kat = a.min_kat
        yenile = a.yenile

    bugun = dt.date.fromisoformat(a.tarih) if a.tarih else dt.date.today()
    hisseler = evren_yukle(Cfg.evren)
    bl_cache = {}
    sonuc = []
    hatalar = []

    for i, h in enumerate(hisseler, 1):
        try:
            r = tara_hisse(h, Cfg(), bl_cache, bugun)
            if r:
                sonuc.append(r)
        except Exception:
            hatalar.append(h)
        if a.yenile and i < len(hisseler):
            time.sleep(a.bekle)
        if i % 50 == 0:
            print(f"  ... {i}/{len(hisseler)}", file=sys.stderr)

    print("=" * 72)
    print(f"DINAMIK {a.min_kat}x CANLI | {bugun} | DIP+KIRILIM")
    print("=" * 72)
    if not sonuc:
        print("Bugun sinyal yok.")
        if hatalar:
            print(f"({len(hatalar)} hisse veri hatasi)")
        return

    df = pd.DataFrame(sonuc).sort_values("kat", ascending=False)
    tag = f"dinamik_tarama_{bugun}.csv"
    df.to_csv(tag, index=False)
    kol = ["hisse", "kat", "grup", "pos52", "giris", "giris_saat", "chase_%", "ciro_TL"]
    print(f"Sinyal: {len(df)} | hata: {len(hatalar)}")
    print("-" * 72)
    print(df[kol].to_string(index=False))
    print(f"\n-> {tag}")
    print("NOT: Brut takas/VBTS KAP'tan teyit et.")


if __name__ == "__main__":
    main()
