from __future__ import annotations
import argparse, sys
import numpy as np
import pandas as pd

from veri import cek_saatlik, _normalize
from evren import evren_yukle

BAREMLER = [0.01, 0.02, 0.03, 0.04, 0.05]
BAREM_AD = ["+1%", "+2%", "+3%", "+4%", "+5%+"]
KOVALAR = [("3-5x", 3, 5), ("5-8x", 5, 8), ("8x+", 8, 1e9)]


def cek_1dk(hisse, n_bars=5000, tv_user=None, tv_pass=None):
    kod = hisse.replace(".IS", "")
    try:
        from tvDatafeed import TvDatafeed, Interval
        tv = TvDatafeed(tv_user, tv_pass) if tv_user else TvDatafeed()
        df = _normalize(pd.DataFrame(tv.get_hist(symbol=kod, exchange="BIST",
                        interval=Interval.in_1_minute, n_bars=n_bars)))
        if len(df):
            return df
    except Exception:
        pass
    try:
        import yfinance as yf
        sym = kod if kod.endswith(".IS") else kod + ".IS"
        df = yf.download(sym, period="7d", interval="1m", auto_adjust=False, progress=False)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        return _normalize(df)
    except Exception:
        return pd.DataFrame()


def hisse_isle(hourly, dk1, baseline_gun, min_ciro_tl, stop, min_bar, son_gun):
    if len(hourly) == 0 or len(dk1) == 0:
        return [], None, None
    gh = hourly.sort_index().copy()
    gh["_t"] = gh.index.date
    ilk = gh.groupby("_t").first()
    openvol = ilk["Volume"]; openprice = ilk["Open"]
    baseline = openvol.rolling(baseline_gun, min_periods=baseline_gun).mean().shift(1)

    gm = dk1.sort_index().copy()
    gm["_t"] = gm.index.date
    by_day = {t: g.sort_index() for t, g in gm.groupby("_t")}
    if not by_day:
        return [], None, None
    en_yeni = max(by_day.keys())
    gecerli = [t for t, g in by_day.items()
               if len(g) >= min_bar and (en_yeni - t).days <= son_gun]

    out = []
    for t in sorted(gecerli):
        if t not in openvol.index or t not in baseline.index or pd.isna(baseline[t]):
            continue
        bl = float(baseline[t]); ov = float(openvol[t]); op = float(openprice[t])
        if bl <= 0 or op <= 0:
            continue
        kat = ov / bl
        if kat < 3 or op * ov < min_ciro_tl:
            continue
        gun = by_day[t]
        giris = float(gun.iloc[0]["Open"])
        if giris <= 0:
            continue
        gun_yuksek = float(gun["High"].max()); gun_dusuk = float(gun["Low"].min())
        alt = giris * (1 - stop)
        en_yuksek = 0.0; stoplandi = False
        for _, bar in gun.iloc[1:].iterrows():
            if bar["Low"] <= alt:
                stoplandi = True; break
            en_yuksek = max(en_yuksek, float(bar["High"]) / giris - 1)
        barem = "stop/<1%"
        for i, b in enumerate(BAREMLER):
            if en_yuksek >= b:
                barem = BAREM_AD[i]
        kova = next((ad for ad, lo, hi in KOVALAR if lo <= kat < hi), "?")
        out.append({"tarih": t, "hisse": None, "kat": round(kat, 2), "kat_kova": kova,
                    "acilis": round(giris, 4), "gun_yuksek": round(gun_yuksek, 4),
                    "gun_dusuk": round(gun_dusuk, 4),
                    "gun_yuksek_%": round((gun_yuksek / giris - 1) * 100, 2),
                    "gun_dusuk_%": round((gun_dusuk / giris - 1) * 100, 2),
                    "en_yuksek_%": round(en_yuksek * 100, 2),
                    "barem": barem, "stop": stoplandi, "bar_sayisi": len(gun)})
    gt = sorted(gecerli)
    return out, (gt[0] if gt else None), len(gt)


def dagilim(df):
    sira = ["stop/<1%"] + BAREM_AD
    d = df["barem"].value_counts().reindex(sira).fillna(0).astype(int)
    n = len(df)
    return {ad: f"{int(d[ad])} (%{round(int(d[ad])/n*100,1)})" for ad in sira}, n


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--evren", default="evren_kucuk.csv")
    p.add_argument("--tv_user", default=None)
    p.add_argument("--tv_pass", default=None)
    p.add_argument("--baseline", type=int, default=20)
    p.add_argument("--min_ciro", type=float, default=200_000)
    p.add_argument("--stop", type=float, default=0.03)
    p.add_argument("--min_bar", type=int, default=200)
    p.add_argument("--son_gun", type=int, default=90)
    a = p.parse_args()

    hisseler = evren_yukle(a.evren)
    hepsi = []; en_eskiler = []; gun_sayilari = []
    for i, h in enumerate(hisseler, 1):
        try:
            hourly = cek_saatlik(h, tv_user=a.tv_user, tv_pass=a.tv_pass, sessiz=True)
            dk1 = cek_1dk(h, tv_user=a.tv_user, tv_pass=a.tv_pass)
            kayit, eski, gsay = hisse_isle(hourly, dk1, a.baseline, a.min_ciro, a.stop,
                                           a.min_bar, a.son_gun)
            for k in kayit:
                k["hisse"] = h
            hepsi += kayit
            if eski:
                en_eskiler.append(eski)
            if gsay:
                gun_sayilari.append(gsay)
            print(f"  [{i}/{len(hisseler)}] {h}: {len(kayit)} sinyal", file=sys.stderr)
        except Exception as e:
            print(f"  [{i}/{len(hisseler)}] {h}: HATA {e}", file=sys.stderr)

    if not hepsi:
        print("Sinyal yok (yogun 1dk seans bulunamadi)."); return
    res = pd.DataFrame(hepsi)
    res.to_csv("dakikalik_barem_v3.csv", index=False)
    print("=" * 62)
    print(f"1-DK BAREM v3 (TEMIZ) | baseline=saatlik {a.baseline}g | giris=eslesme | stop=%{a.stop*100:.0f}")
    print(f"Filtre: gunde >= {a.min_bar} bar + son {a.son_gun} gun")
    if en_eskiler:
        print(f"Kullanilan 1dk: en eski {min(en_eskiler)} | ortanca hisse {int(np.median(gun_sayilari))} gun")
    print(f"Toplam sinyal: {len(res)} | tarih {res['tarih'].min()} -> {res['tarih'].max()}")
    print("=" * 62)
    dd, n = dagilim(res); print(f"TUM ({n}):")
    for k, v in dd.items():
        print(f"   {k:>9}: {v}")
    for ad, lo, hi in KOVALAR:
        alt = res[res["kat_kova"] == ad]
        if len(alt) == 0:
            print(f"\n{ad}: sinyal yok"); continue
        dd, n = dagilim(alt); print(f"\n{ad} ({n}):")
        for k, v in dd.items():
            print(f"   {k:>9}: {v}")
    print("\n-> dakikalik_barem_v3.csv (tarih,hisse,kat,acilis,gun_yuksek,gun_dusuk,en_yuksek_%,barem,stop,bar_sayisi)")


if __name__ == "__main__":
    main()
