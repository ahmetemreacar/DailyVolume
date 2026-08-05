from __future__ import annotations
import argparse
import sys
import numpy as np
import pandas as pd

from veri import _normalize
from evren import evren_yukle

BAREMLER = [0.01, 0.02, 0.03, 0.04, 0.05]
BAREM_AD = ["+1%", "+2%", "+3%", "+4%", "+5%", "+5%+"]


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


def gun_baremleri(df, baseline_gun, min_kat, min_ciro_tl, stop, acilis_bar=1):
    g = df.copy()
    g["_t"] = g.index.date
    gunluk = {t: gun.sort_index() for t, gun in g.groupby("_t")}
    tarihler = sorted(gunluk.keys())
    acilis_vol = {t: float(gunluk[t].iloc[:acilis_bar]["Volume"].sum())
                  for t in tarihler if len(gunluk[t]) >= acilis_bar}
    serisi = pd.Series(acilis_vol).sort_index()
    baseline = serisi.rolling(baseline_gun, min_periods=baseline_gun).mean().shift(1)
    out = []
    for t in tarihler:
        if t not in acilis_vol or t not in baseline.index or pd.isna(baseline[t]):
            continue
        gun = gunluk[t]
        if len(gun) < acilis_bar + 1:
            continue
        av, bl = acilis_vol[t], baseline[t]
        giris = float(gun.iloc[0]["Open"])   # ESLESME fiyati
        if giris <= 0 or bl <= 0:
            continue
        if (av / bl) < min_kat or giris * av < min_ciro_tl:
            continue
        alt = giris * (1 - stop)
        en_yuksek_oran = 0.0
        stoplandi = False
        for _, bar in gun.iloc[acilis_bar:].iterrows():
            if bar["Low"] <= alt:
                stoplandi = True
                break
            en_yuksek_oran = max(en_yuksek_oran, float(bar["High"]) / giris - 1)
        barem = "stop/<1%"
        for i, b in enumerate(BAREMLER):
            if en_yuksek_oran >= b:
                barem = BAREM_AD[i]
        if en_yuksek_oran >= 0.05:
            barem = "+5%+"
        out.append({"tarih": t, "kat": av / bl, "en_yuksek_%": round(en_yuksek_oran * 100, 2),
                    "barem": barem, "stop": stoplandi})
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--evren", default="evren_kucuk.csv")
    p.add_argument("--tv_user", default=None)
    p.add_argument("--tv_pass", default=None)
    p.add_argument("--min_kat", type=float, default=8.0)
    p.add_argument("--baseline", type=int, default=5)
    p.add_argument("--min_ciro", type=float, default=200_000)
    p.add_argument("--stop", type=float, default=0.03)
    a = p.parse_args()

    hisseler = evren_yukle(a.evren)
    hepsi = []
    for i, h in enumerate(hisseler, 1):
        try:
            df = cek_1dk(h, tv_user=a.tv_user, tv_pass=a.tv_pass)
            if len(df) < a.baseline + 2:
                print(f"  [{i}/{len(hisseler)}] {h}: veri yok/az", file=sys.stderr)
                continue
            for k in gun_baremleri(df, a.baseline, a.min_kat, a.min_ciro, a.stop):
                k["hisse"] = h
                hepsi.append(k)
            print(f"  [{i}/{len(hisseler)}] {h}: ok", file=sys.stderr)
        except Exception as e:
            print(f"  [{i}/{len(hisseler)}] {h}: HATA {e}", file=sys.stderr)

    if not hepsi:
        print("Sinyal gunu yok (1dk gecmis cok kisa olabilir).")
        return
    res = pd.DataFrame(hepsi)
    res.to_csv("dakikalik_barem.csv", index=False)
    sira = ["stop/<1%"] + BAREM_AD
    dag = res["barem"].value_counts().reindex(sira).fillna(0).astype(int)
    print("=" * 56)
    print(f"1-DK BAREM | giris=eslesme | stop=%{a.stop*100:.0f} | min_kat>={a.min_kat}")
    print(f"Sinyal: {len(res)} | tarih: {res['tarih'].min()} -> {res['tarih'].max()}")
    print("=" * 56)
    for ad in sira:
        n = int(dag[ad]); print(f"  {ad:>8} : {n:4d}  (%{round(n/len(res)*100,1)})")
    print("-" * 56)
    print(f"+%3'e ulasan: %{round((res['en_yuksek_%']>=3).mean()*100,1)} | "
          f"+%5'e ulasan: %{round((res['en_yuksek_%']>=5).mean()*100,1)}")
    print("NOT: 1dk gecmis kisa -> az sinyal, KESIF. Stop-first konservatif.")


if __name__ == "__main__":
    main()
