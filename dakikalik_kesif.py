from __future__ import annotations
import argparse
import sys
import numpy as np
import pandas as pd

from veri import _normalize
from evren import evren_yukle


def cek_5dk(hisse, n_bars=5000, tv_user=None, tv_pass=None):
    kod = hisse.replace(".IS", "")
    try:
        from tvDatafeed import TvDatafeed, Interval
        tv = TvDatafeed(tv_user, tv_pass) if tv_user else TvDatafeed()
        df = _normalize(pd.DataFrame(tv.get_hist(symbol=kod, exchange="BIST",
                        interval=Interval.in_5_minute, n_bars=n_bars)))
        if len(df):
            return df
    except Exception:
        pass
    try:
        import yfinance as yf
        sym = kod if kod.endswith(".IS") else kod + ".IS"
        df = yf.download(sym, period="60d", interval="5m", auto_adjust=False, progress=False)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        return _normalize(df)
    except Exception:
        return pd.DataFrame()


def gun_kayitlari(df, gozlem_bar, baseline_gun, min_kat, min_ciro_tl, hedef, stop,
                  komisyon, slippage):
    g = df.copy()
    g["_t"] = g.index.date
    gunluk = {t: gun.sort_index() for t, gun in g.groupby("_t")}
    tarihler = sorted(gunluk.keys())
    acilis_vol = {}
    for t in tarihler:
        gun = gunluk[t]
        if len(gun) >= gozlem_bar:
            acilis_vol[t] = float(gun.iloc[:gozlem_bar]["Volume"].sum())
    serisi = pd.Series(acilis_vol).sort_index()
    baseline = serisi.rolling(baseline_gun, min_periods=baseline_gun).mean().shift(1)
    maliyet = (komisyon + slippage) * 2
    out = []
    for t in tarihler:
        if t not in acilis_vol or t not in baseline.index or pd.isna(baseline[t]):
            continue
        gun = gunluk[t]
        if len(gun) < gozlem_bar + 1:
            continue
        av, bl = acilis_vol[t], baseline[t]
        acilis_fiyat = float(gun.iloc[0]["Open"])
        if acilis_fiyat <= 0 or bl <= 0:
            continue
        if (av / bl) < min_kat or acilis_fiyat * av < min_ciro_tl:
            continue
        gozlem = gun.iloc[:gozlem_bar]
        giris = float(gozlem.iloc[-1]["Close"])
        if giris <= 0:
            continue
        ilk_ret = giris / acilis_fiyat - 1
        kalan = gun.iloc[gozlem_bar:]
        ust, alt = giris * (1 + hedef), giris * (1 - stop)
        sonuc, cikis = None, None
        for _, bar in kalan.iterrows():
            if bar["Low"] <= alt:
                sonuc, cikis = "stop", alt
                break
            if bar["High"] >= ust:
                sonuc, cikis = "hedef", ust
                break
        if sonuc is None:
            sonuc, cikis = "kapanis", float(kalan.iloc[-1]["Close"]) if len(kalan) else giris
        net = cikis / giris - 1 - maliyet
        out.append({"tarih": t, "kat": av / bl, "ilk_ret": ilk_ret,
                    "getiri_net": net, "sonuc": sonuc})
    return out


def metrik(df):
    if len(df) == 0:
        return {"n": 0, "win_%": 0, "EV_%": 0, "PF": 0, "ilk_ret_ort_%": 0}
    r = df["getiri_net"]
    kaz, kay = r[r > 0], r[r < 0]
    pf = kaz.sum() / abs(kay.sum()) if len(kay) and kay.sum() != 0 else np.inf
    return {"n": len(r), "win_%": round((r > 0).mean() * 100, 1),
            "EV_%": round(r.mean() * 100, 3),
            "PF": round(pf, 2) if np.isfinite(pf) else 99.0,
            "ilk_ret_ort_%": round(df["ilk_ret"].mean() * 100, 2)}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--evren", default="evren_kucuk.csv")
    p.add_argument("--tv_user", default=None)
    p.add_argument("--tv_pass", default=None)
    p.add_argument("--gozlem_dk", type=int, default=15)
    p.add_argument("--min_kat", type=float, default=8.0)
    p.add_argument("--baseline", type=int, default=10)
    p.add_argument("--min_ciro", type=float, default=200_000)
    p.add_argument("--hedef", type=float, default=0.05)
    p.add_argument("--stop", type=float, default=0.03)
    p.add_argument("--komisyon", type=float, default=0.0005)
    p.add_argument("--slippage", type=float, default=0.003)
    a = p.parse_args()

    gozlem_bar = max(1, a.gozlem_dk // 5)
    hisseler = evren_yukle(a.evren)
    hepsi = []
    for i, h in enumerate(hisseler, 1):
        try:
            df = cek_5dk(h, tv_user=a.tv_user, tv_pass=a.tv_pass)
            if len(df) < gozlem_bar + 1:
                print(f"  [{i}/{len(hisseler)}] {h}: veri yok/az", file=sys.stderr)
                continue
            kayit = gun_kayitlari(df, gozlem_bar, a.baseline, a.min_kat, a.min_ciro,
                                  a.hedef, a.stop, a.komisyon, a.slippage)
            for k in kayit:
                k["hisse"] = h
            hepsi += kayit
            print(f"  [{i}/{len(hisseler)}] {h}: {len(kayit)} sinyal gunu", file=sys.stderr)
        except Exception as e:
            print(f"  [{i}/{len(hisseler)}] {h}: HATA {e}", file=sys.stderr)

    if not hepsi:
        print("Sinyal gunu bulunamadi (5dk gecmis kisa olabilir).")
        return
    res = pd.DataFrame(hepsi)
    res.to_csv("dakikalik_kesif.csv", index=False)
    eyukari = res[res["ilk_ret"] > 0]
    easagi = res[res["ilk_ret"] <= 0]
    print("=" * 64)
    print(f"DAKIKALIK KESIF | gozlem={a.gozlem_dk}dk | min_kat>={a.min_kat} | "
          f"hedef=%{a.hedef*100:.0f} stop=%{a.stop*100:.0f}")
    print("=" * 64)
    print(pd.DataFrame({"TUM": metrik(res), "Erken YUKARI": metrik(eyukari),
                        "Erken ASAGI": metrik(easagi)}).to_string())
    print("-" * 64)
    print("'Erken YUKARI' pozitif EV/PF>1, 'Erken ASAGI' negatifse erken yon bilgi katiyor.")
    print("NOT: 5dk gecmis kisa; KESIF aracidir. Yatirim tavsiyesi degildir.")


if __name__ == "__main__":
    main()
