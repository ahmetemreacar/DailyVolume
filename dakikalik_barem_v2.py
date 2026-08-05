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


def hisse_isle(hourly, dk1, baseline_gun, min_ciro_tl, stop):
    if len(hourly) == 0 or len(dk1) == 0:
        return [], None
    gh = hourly.sort_index().copy()
    gh["_t"] = gh.index.date
    ilk = gh.groupby("_t").first()
    openvol = ilk["Volume"]; openprice = ilk["Open"]
    baseline = openvol.rolling(baseline_gun, min_periods=baseline_gun).mean().shift(1)

    gm = dk1.sort_index().copy()
    gm["_t"] = gm.index.date
    by_day = {t: g.sort_index() for t, g in gm.groupby("_t")}

    out = []
    for t in sorted(by_day.keys()):
        if t not in openvol.index or t not in baseline.index or pd.isna(baseline[t]):
            continue
        bl = float(baseline[t]); ov = float(openvol[t]); op = float(openprice[t])
        if bl <= 0 or op <= 0:
            continue
        kat = ov / bl
        if kat < 3 or op * ov < min_ciro_tl:
            continue
        gun = by_day[t]
        if len(gun) < 2:
            continue
        giris = float(gun.iloc[0]["Open"])
        if giris <= 0:
            continue
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
                    "en_yuksek_%": round(en_yuksek * 100, 2), "barem": barem, "stop": stoplandi})
    dk_gunler = sorted(by_day.keys())
    return out, ((dk_gunler[0] if dk_gunler else None), len(dk_gunler))


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
    a = p.parse_args()

    hisseler = evren_yukle(a.evren)
    hepsi = []; kapsama = []
    for i, h in enumerate(hisseler, 1):
        try:
            hourly = cek_saatlik(h, tv_user=a.tv_user, tv_pass=a.tv_pass, sessiz=True)
            dk1 = cek_1dk(h, tv_user=a.tv_user, tv_pass=a.tv_pass)
            kayit, kap = hisse_isle(hourly, dk1, a.baseline, a.min_ciro, a.stop)
            for k in kayit:
                k["hisse"] = h
            hepsi += kayit
            if kap and kap[0]:
                kapsama.append(kap)
            print(f"  [{i}/{len(hisseler)}] {h}: {len(kayit)} sinyal", file=sys.stderr)
        except Exception as e:
            print(f"  [{i}/{len(hisseler)}] {h}: HATA {e}", file=sys.stderr)

    if not hepsi:
        print("Sinyal yok."); return
    res = pd.DataFrame(hepsi)
    res.to_csv("dakikalik_barem_v2.csv", index=False)
    print("=" * 60)
    print(f"1-DK BAREM v2 | baseline=saatlik rolling {a.baseline}g | giris=eslesme | stop=%{a.stop*100:.0f}")
    if kapsama:
        print(f"1dk veri kapsami: en eski {min(k[0] for k in kapsama)} | ortanca hisse {int(np.median([k[1] for k in kapsama]))} gun")
    print(f"Toplam sinyal: {len(res)} | tarih {res['tarih'].min()} -> {res['tarih'].max()}")
    print("=" * 60)
    dd, n = dagilim(res); print(f"TUM ({n}):")
    for k, v in dd.items():
        print(f"   {k:>9}: {v}")
    for ad, lo, hi in KOVALAR:
        alt = res[res["kat_kova"] == ad]
        if len(alt) == 0:
            print(f"\n{ad}: sinyal yok"); continue
        dd, n = dagilim(alt); print(f"\n{ad} ({n} sinyal):")
        for k, v in dd.items():
            print(f"   {k:>9}: {v}")
    print("\n-> dakikalik_barem_v2.csv (her islem: tarih, hisse, kat, sonuc).")


if __name__ == "__main__":
    main()
