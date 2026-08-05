from __future__ import annotations
import argparse, sys
import numpy as np
import pandas as pd

from veri import cek_saatlik, _normalize
from evren import evren_yukle

BAREMLER = [0.01, 0.02, 0.03, 0.04, 0.05]
BAREM_AD = ["+1%", "+2%", "+3%", "+4%", "+5%+"]


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
    g = df.sort_index().copy()
    g["_t"] = g.index.date
    return g.groupby("_t").agg(Open=("Open", "first"), High=("High", "max"),
                               Low=("Low", "min"), Close=("Close", "last"),
                               ovol=("Volume", "first"))


def barem_hesap(gun, giris, stop):
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
    return en_yuksek, barem, stoplandi


def hisse_isle(hourly, dk1, baseline_gun, min_kat, min_ciro_tl, stop,
               min_bar, son_gun, hafta52, dip_esik):
    if len(hourly) == 0 or len(dk1) == 0:
        return []
    d = gunluk(hourly)
    if len(d) < hafta52 + 5:
        return []
    baseline = d["ovol"].rolling(baseline_gun, min_periods=baseline_gun).mean().shift(1)
    hi52 = d["High"].rolling(hafta52, min_periods=hafta52 // 2).max().shift(1)
    lo52 = d["Low"].rolling(hafta52, min_periods=hafta52 // 2).min().shift(1)
    dun_kapanis = d["Close"].shift(1)

    gm = dk1.sort_index().copy()
    gm["_t"] = gm.index.date
    by_day = {t: g.sort_index() for t, g in gm.groupby("_t")}
    if not by_day:
        return []
    en_yeni = max(by_day.keys())
    gecerli = [t for t, g in by_day.items()
               if len(g) >= min_bar and (en_yeni - t).days <= son_gun]

    out = []
    for t in sorted(gecerli):
        if t not in baseline.index or pd.isna(baseline[t]) or pd.isna(hi52[t]) or pd.isna(lo52[t]):
            continue
        bl = float(baseline[t]); ov = float(d.loc[t, "ovol"])
        H, L, dk = float(hi52[t]), float(lo52[t]), float(dun_kapanis[t])
        if bl <= 0 or H <= L:
            continue
        gun = by_day[t]
        giris = float(gun.iloc[0]["Open"])
        if giris <= 0 or giris * ov < min_ciro_tl:
            continue
        kat = ov / bl
        gun_yuksek = float(gun["High"].max())
        pos52 = (giris - L) / (H - L)
        dip = pos52 <= dip_esik
        taze_kirilim = (dk < H) and (gun_yuksek >= H)
        if not (dip or taze_kirilim):
            continue
        grup = "dip" if dip else "taze_kirilim"
        tip = "sinyal" if kat >= min_kat else ("kontrol" if kat < 3 else "ara")
        if tip == "ara":
            continue
        en_yuksek, barem, stoplandi = barem_hesap(gun, giris, stop)
        out.append({"tarih": t, "hisse": None, "tip": tip, "grup": grup,
                    "kat": round(kat, 2), "pos52": round(pos52, 3),
                    "acilis": round(giris, 4), "gun_yuksek_%": round((gun_yuksek/giris-1)*100, 2),
                    "en_yuksek_%": round(en_yuksek*100, 2), "barem": barem,
                    "stop": stoplandi, "bar_sayisi": len(gun)})
    return out


def dagilim(df):
    sira = ["stop/<1%"] + BAREM_AD
    d = df["barem"].value_counts().reindex(sira).fillna(0).astype(int)
    n = len(df)
    return " | ".join(f"{ad}:{int(d[ad])}(%{int(round(int(d[ad])/n*100))})" for ad in sira), n


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--evren", default="evren_kucuk.csv")
    p.add_argument("--tv_user", default=None)
    p.add_argument("--tv_pass", default=None)
    p.add_argument("--baseline", type=int, default=20)
    p.add_argument("--min_kat", type=float, default=8.0)
    p.add_argument("--min_ciro", type=float, default=200_000)
    p.add_argument("--stop", type=float, default=0.03)
    p.add_argument("--min_bar", type=int, default=200)
    p.add_argument("--son_gun", type=int, default=90)
    p.add_argument("--hafta52", type=int, default=252)
    p.add_argument("--dip_esik", type=float, default=0.20)
    a = p.parse_args()

    hisseler = evren_yukle(a.evren)
    hepsi = []
    for i, h in enumerate(hisseler, 1):
        try:
            hourly = cek_saatlik(h, tv_user=a.tv_user, tv_pass=a.tv_pass, sessiz=True)
            dk1 = cek_1dk(h, tv_user=a.tv_user, tv_pass=a.tv_pass)
            for k in hisse_isle(hourly, dk1, a.baseline, a.min_kat, a.min_ciro, a.stop,
                                a.min_bar, a.son_gun, a.hafta52, a.dip_esik):
                k["hisse"] = h
                hepsi.append(k)
            print(f"  [{i}/{len(hisseler)}] {h}", file=sys.stderr)
        except Exception as e:
            print(f"  [{i}/{len(hisseler)}] {h}: HATA {e}", file=sys.stderr)

    if not hepsi:
        print("Kayit yok."); return
    res = pd.DataFrame(hepsi)
    res.to_csv("dakikalik_v4_52hafta.csv", index=False)
    sin = res[res["tip"] == "sinyal"]; kon = res[res["tip"] == "kontrol"]
    print("=" * 68)
    print(f"v4 52-HAFTA | 8x+ VE (dip<=%{int(a.dip_esik*100)} VEYA taze 52h kirilim) | giris eslesme | stop=%{int(a.stop*100)}")
    print(f"Tarih: {res['tarih'].min()} -> {res['tarih'].max()}")
    print("=" * 68)
    def yaz(ad, df):
        if len(df) == 0:
            print(f"{ad}: kayit yok"); return
        s, n = dagilim(df)
        print(f"{ad} (n={n}, +5%+=%{round((df['barem']=='+5%+').mean()*100,1)}):\n   {s}")
    yaz("SECILI SINYAL (8x+)", sin)
    yaz("  DIP", sin[sin['grup']=='dip'])
    yaz("  TAZE-KIRILIM", sin[sin['grup']=='taze_kirilim'])
    print("-"*68)
    yaz("KONTROL (normal hacim, ayni filtre)", kon)
    print("-"*68)
    if len(sin) and len(kon):
        print(f"KIYAS +5%+: sinyal %{round((sin['barem']=='+5%+').mean()*100,1)} vs kontrol %{round((kon['barem']=='+5%+').mean()*100,1)}")
    print("\n-> dakikalik_v4_52hafta.csv")


if __name__ == "__main__":
    main()
