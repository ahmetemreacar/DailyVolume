from __future__ import annotations
import argparse, sys
import numpy as np
import pandas as pd

from veri import cek_saatlik, _normalize
from evren import evren_yukle

KURALLAR = [("+1%", 0.01), ("+2%", 0.02), ("+3%", 0.03), ("+5%", 0.05), ("+5%+ride", None)]


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


def gunluk(df):
    g = df.sort_index().copy(); g["_t"] = g.index.date
    return g.groupby("_t").agg(Open=("Open", "first"), High=("High", "max"),
                               Low=("Low", "min"), Close=("Close", "last"), ovol=("Volume", "first"))


def trade_ozellik(gun, giris, stop):
    alt = giris * (1 - stop)
    en_yuksek = 0.0; stoplandi = False
    for _, bar in gun.iloc[1:].iterrows():
        if bar["Low"] <= alt:
            stoplandi = True; break
        en_yuksek = max(en_yuksek, float(bar["High"]) / giris - 1)
    return en_yuksek, stoplandi, float(gun.iloc[-1]["Close"]) / giris - 1


def kural_getiri(en_yuksek, stoplandi, kapanis_ret, hedef, stop):
    if hedef is None:
        return -stop if stoplandi else kapanis_ret
    if en_yuksek >= hedef:
        return hedef
    if stoplandi:
        return -stop
    return kapanis_ret


def hisse_isle(hourly, dk1, baseline_gun, min_kat, min_ciro_tl, stop, min_bar,
               son_gun, hafta52, dip_esik, ust_esik, true_tl, false_tl):
    if len(hourly) == 0 or len(dk1) == 0:
        return []
    d = gunluk(hourly)
    if len(d) < hafta52 + 5:
        return []
    baseline = d["ovol"].rolling(baseline_gun, min_periods=baseline_gun).mean().shift(1)
    hi52 = d["High"].rolling(hafta52, min_periods=hafta52 // 2).max().shift(1)
    lo52 = d["Low"].rolling(hafta52, min_periods=hafta52 // 2).min().shift(1)
    dun_kapanis = d["Close"].shift(1)
    gm = dk1.sort_index().copy(); gm["_t"] = gm.index.date
    by_day = {t: g.sort_index() for t, g in gm.groupby("_t")}
    if not by_day:
        return []
    en_yeni = max(by_day.keys())
    gecerli = [t for t, g in by_day.items() if len(g) >= min_bar and (en_yeni - t).days <= son_gun]
    out = []
    for t in sorted(gecerli):
        if t not in baseline.index or pd.isna(baseline[t]) or pd.isna(hi52[t]) or pd.isna(lo52[t]):
            continue
        bl = float(baseline[t]); ov = float(d.loc[t, "ovol"])
        H, L, dk = float(hi52[t]), float(lo52[t]), float(dun_kapanis[t])
        if bl <= 0 or H <= L:
            continue
        kat = ov / bl
        if kat < min_kat:
            continue
        gun = by_day[t]; giris = float(gun.iloc[0]["Open"])
        if giris <= 0 or giris * ov < min_ciro_tl:
            continue
        pos52 = (giris - L) / (H - L)
        gun_yuksek = float(gun["High"].max())
        taze_kirilim = (dk < H) and (gun_yuksek >= H)
        dip = pos52 <= dip_esik
        if (pos52 >= ust_esik) and not taze_kirilim:
            continue
        if dip or taze_kirilim:
            tip, poz, grup = "TRUE", true_tl, ("dip" if dip else "kirilim")
        else:
            tip, poz, grup = "FALSE", false_tl, "orta"
        en_yuksek, stoplandi, kapanis_ret = trade_ozellik(gun, giris, stop)
        out.append({"tarih": str(t), "hisse": None, "tip": tip, "grup": grup,
                    "kat": round(kat, 1), "pos52": round(pos52, 3), "acilis": round(giris, 4),
                    "poz_tl": poz, "en_yuksek_%": round(en_yuksek*100, 2),
                    "kapanis_%": round(kapanis_ret*100, 2), "stop": stoplandi})
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--evren", default="evren_kucuk.csv")
    p.add_argument("--tv_user", default=None); p.add_argument("--tv_pass", default=None)
    p.add_argument("--sermaye", type=float, default=100_000)
    p.add_argument("--true_tl", type=float, default=20_000)
    p.add_argument("--false_tl", type=float, default=10_000)
    p.add_argument("--min_kat", type=float, default=8.0)
    p.add_argument("--stop", type=float, default=0.03)
    p.add_argument("--baseline", type=int, default=20)
    p.add_argument("--hafta52", type=int, default=252)
    p.add_argument("--dip_esik", type=float, default=0.20)
    p.add_argument("--ust_esik", type=float, default=0.80)
    p.add_argument("--min_ciro", type=float, default=200_000)
    p.add_argument("--min_bar", type=int, default=200)
    p.add_argument("--son_gun", type=int, default=90)
    p.add_argument("--komisyon", type=float, default=0.00009)
    p.add_argument("--bsmv", type=float, default=0.000075)
    p.add_argument("--slippage", type=float, default=0.0)
    a = p.parse_args()

    rt = 2 * (a.komisyon + a.bsmv + a.slippage)
    hisseler = evren_yukle(a.evren)
    hepsi = []
    for i, h in enumerate(hisseler, 1):
        try:
            hourly = cek_saatlik(h, tv_user=a.tv_user, tv_pass=a.tv_pass, sessiz=True)
            dk1 = cek_1dk(h, tv_user=a.tv_user, tv_pass=a.tv_pass)
            for k in hisse_isle(hourly, dk1, a.baseline, a.min_kat, a.min_ciro, a.stop,
                                a.min_bar, a.son_gun, a.hafta52, a.dip_esik, a.ust_esik,
                                a.true_tl, a.false_tl):
                k["hisse"] = h
                hepsi.append(k)
            print(f"  [{i}/{len(hisseler)}] {h}", file=sys.stderr)
        except Exception as e:
            print(f"  [{i}/{len(hisseler)}] {h}: HATA {e}", file=sys.stderr)

    if not hepsi:
        print("Islem yok."); return
    res = pd.DataFrame(hepsi)
    for ad, hedef in KURALLAR:
        net = res.apply(lambda r: kural_getiri(r["en_yuksek_%"]/100, r["stop"],
                        r["kapanis_%"]/100, hedef, a.stop) - rt, axis=1)
        res[f"ret_{ad}"] = (net*100).round(2)
        res[f"tl_{ad}"] = (net*res["poz_tl"]).round(0)
    res.to_csv("portfoy_backtest.csv", index=False)
    nt = (res["tip"]=="TRUE").sum(); nf = (res["tip"]=="FALSE").sum()
    print("="*64)
    print(f"PORTFOY | sermaye {a.sermaye:,.0f} | TRUE={a.true_tl:,.0f} FALSE={a.false_tl:,.0f}")
    print(f"maliyet cift-yon=%{rt*100:.3f} (slippage=%{a.slippage*100:.2f}) | {res['tarih'].min()}->{res['tarih'].max()}")
    print(f"Islem: {len(res)} (TRUE {nt}, FALSE {nf})")
    print("="*64)
    print(f"{'KURAL':>10} {'top_kar_TL':>12} {'getiri_%':>9} {'kazanan':>8} {'win_%':>7}")
    for ad, _ in KURALLAR:
        tl = res[f"tl_{ad}"].sum(); kaz=(res[f"ret_{ad}"]>0).sum(); win=(res[f"ret_{ad}"]>0).mean()*100
        print(f"{ad:>10} {tl:>12,.0f} {tl/a.sermaye*100:>8.2f}% {kaz:>8} {win:>6.1f}%")
    print("-> portfoy_backtest.csv (her islem: tarih, hisse, acilis, tip, poz_tl, her kural getiri+TL)")


if __name__ == "__main__":
    main()
