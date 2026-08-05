"""Tum portfoy islemlerini ham 1dk veriyle teyit eder."""
from __future__ import annotations
import datetime as dt
import pandas as pd
import numpy as np
from veri_cache import cek_1dk

STOP = 0.03
KURALLAR = {"1": 0.01, "2": 0.02, "3": 0.03, "5": 0.05}
ACILIS_SON = dt.time(10, 5)


def bar_veri_hisse(hisse, baslangic):
    dk = cek_1dk(hisse)
    if len(dk) == 0:
        return {}
    gm = dk.sort_index().copy()
    gm["_t"] = gm.index.date
    out = {}
    for t, g in gm.groupby("_t"):
        if str(t) < baslangic:
            continue
        g = g.sort_index()
        out[str(t)] = {
            "gun": g,
            "lows": g["Low"].values.astype(float),
            "highs": g["High"].values.astype(float),
            "close": float(g.iloc[-1]["Close"]),
            "ilk_saat": g.index[0].time(),
            "ilk_open": float(g.iloc[0]["Open"]),
            "gun_low": float(g["Low"].min()),
            "gun_high": float(g["High"].max()),
        }
    return out


def simule_islem(hisse, giris_tarih, giris_fiyat, target, stop=STOP):
    """portfoy_compound ile ayni cikis mantigi (stop-first, giris gunu bar 1'den)."""
    bd = bar_veri_hisse(hisse, giris_tarih)
    if giris_tarih not in bd:
        return None
    ust = giris_fiyat * (1 + target)
    alt = giris_fiyat * (1 - stop)
    gunler = sorted(bd.keys())
    bas = gunler.index(giris_tarih)
    mh = giris_fiyat
    for di in range(bas, len(gunler)):
        D = gunler[di]
        lows, highs = bd[D]["lows"], bd[D]["highs"]
        start = 1 if D == giris_tarih else 0
        for k in range(start, len(lows)):
            hi, lo = highs[k], lows[k]
            if hi > mh:
                mh = hi
            hed, stp = hi >= ust, lo <= alt
            if stp and hed:
                return _sonuc(D, alt, "stop", giris_fiyat, mh, bd, giris_tarih, target)
            if hed:
                return _sonuc(D, ust, "hedef", giris_fiyat, mh, bd, giris_tarih, target)
            if stp:
                return _sonuc(D, alt, "stop", giris_fiyat, mh, bd, giris_tarih, target)
    # acik kaldi
    sonD = gunler[-1]
    sc = bd[sonD]["close"]
    return _sonuc(sonD, sc, "acik_kaldi", giris_fiyat, mh, bd, giris_tarih, target)


def _sonuc(cikis_tarih, cikis_fiyat, sebep, giris, mh, bd, gt, target):
    g = bd[gt]["gun"]
    gun_close = float(g.iloc[-1]["Close"])
    kapanis_pct = round((gun_close / giris - 1) * 100, 1)
    max_pct = round((mh / giris - 1) * 100, 2)
    alt = giris * (1 - STOP)
    stop_bar_n = int((g.iloc[1:]["Low"] <= alt).sum()) if len(g) > 1 else 0
    flags = []
    if g.index[0].time() > ACILIS_SON:
        flags.append("gec_acilis")
    if abs(float(g.iloc[0]["Open"]) - giris) > 0.02:
        flags.append("giris_fark")
    if sebep == "stop" and cikis_tarih == gt:
        if kapanis_pct >= 5:
            flags.append(f"stop_ama_gun_kapanis_+{kapanis_pct}%")
        if stop_bar_n == 1:
            t = g.iloc[1:][g.iloc[1:]["Low"] <= alt].index[0]
            nxt = g.loc[t:].iloc[1:3]
            if len(nxt) and float(nxt["Close"].mean()) > giris * 0.98:
                flags.append("tek_bar_wick")
    if sebep == "stop" and cikis_tarih == gt and max_pct >= target * 100:
        flags.append("stop_once_hedef_gun_icinde")
    durum = "SUPHELI" if flags else "OK"
    if sebep == "stop" and "tek_bar_wick" in flags:
        durum = "SUPHELI_WICK"
    if sebep == "stop" and any("stop_ama_gun_kapanis" in f for f in flags):
        durum = "SUPHELI_WICK"
    return {
        "beklenen_sebep": sebep,
        "beklenen_cikis": round(cikis_fiyat, 4),
        "beklenen_cikis_tarih": cikis_tarih,
        "gun_kapanis_%": kapanis_pct,
        "max_gordugu_%": max_pct,
        "ilk_bar_saat": str(g.index[0].time())[:5],
        "1dk_gun_low": round(bd[gt]["gun_low"], 4),
        "1dk_gun_high": round(bd[gt]["gun_high"], 4),
        "flags": "|".join(flags) if flags else "-",
        "durum": durum,
    }


def teyit_dosya(dosya, hedef_ad):
    target = KURALLAR[hedef_ad]
    df = pd.read_csv(dosya)
    rows = []
    for _, r in df.iterrows():
        h = r["hisse"]
        gt = r["giris_tarih"]
        giris = float(r["giris"])
        sim = simule_islem(h, gt, giris, target)
        row = {
            "hedef_%": int(hedef_ad),
            "hisse": h,
            "giris_tarih": gt,
            "cikis_tarih": r["cikis_tarih"],
            "grup": r["grup"],
            "kat": r["kat"],
            "giris": giris,
            "kayitli_sebep": r["sebep"],
            "kayitli_cikis": r["cikis"],
            "kayitli_getiri_%": r["getiri_%"],
            "kayitli_tl_kar": r["tl_kar"],
        }
        if sim is None:
            row.update({"durum": "VERI_YOK", "flags": "1dk_yok", "beklenen_sebep": "-",
                        "gun_kapanis_%": None, "max_gordugu_%": None})
        else:
            row.update(sim)
            sebep_ok = (row["kayitli_sebep"] == sim["beklenen_sebep"]) or (
                row["kayitli_sebep"] == "stop" and sim["beklenen_sebep"] == "stop"
                and abs(row["kayitli_cikis"] - sim["beklenen_cikis"]) < 0.02
            )
            tarih_ok = str(row["cikis_tarih"]) == str(sim["beklenen_cikis_tarih"])
            if not sebep_ok or not tarih_ok:
                row["durum"] = "UYUMSUZ"
                row["flags"] = (row.get("flags", "") + "|kayit_uyumsuz").strip("|")
        rows.append(row)
    return pd.DataFrame(rows)


def main():
    tum = []
    for ad in ["1", "2", "3", "5"]:
        tum.append(teyit_dosya(f"portfoy_{ad}.csv", ad))
    out = pd.concat(tum, ignore_index=True)
    out.to_csv("teyit_tum_islemler.csv", index=False)

    print("=" * 90)
    print("TEYIT OZETI (stop=%3 sabit)")
    for ad in ["1", "2", "3", "5"]:
        alt = out[out["hedef_%"] == int(ad)]
        print(f"\n--- HEDEF %{ad} | stop %3 | {len(alt)} islem ---")
        print(alt["durum"].value_counts().to_string())
    print("\n" + "=" * 90)
    print("TUM ISLEMLER TABLOSU")
    kol = ["hedef_%", "hisse", "giris_tarih", "grup", "giris", "kayitli_sebep",
           "kayitli_getiri_%", "gun_kapanis_%", "max_gordugu_%", "durum", "flags"]
    pd.set_option("display.max_rows", 500)
    pd.set_option("display.width", 200)
    print(out[kol].to_string(index=False))
    print(f"\n-> teyit_tum_islemler.csv ({len(out)} satir)")


if __name__ == "__main__":
    main()
