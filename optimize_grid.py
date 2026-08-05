from __future__ import annotations
import argparse
import sys
import numpy as np
import pandas as pd

from veri import cek_saatlik
from sinyal import sinyal_uret
from evren import evren_yukle


def _gun_barlari(df):
    g = df.copy()
    g["_t"] = g.index.date
    return {t: gun.sort_index() for t, gun in g.groupby("_t")}


def islemler_tek(df, hedef, stop, baseline_gun, kat, min_ciro_tl, min_kat,
                 komisyon, slippage):
    """Tek hisse, tek (hedef,stop) icin islemler. Giris = ilk barin KAPANISI
    (auction fiyati, sinyal aninda belli), cikis 2. bardan itibaren High/Low
    sirasiyla. Ayni barda ikisi de gorulurse STOP ilk (konservatif)."""
    sig = sinyal_uret(df, baseline_gun, kat, min_ciro_tl)
    if len(sig) == 0:
        return []
    gunler = _gun_barlari(df)
    maliyet = (komisyon + slippage) * 2
    out = []
    sec = sig[sig["sinyal"] & (sig["kat_gerceklesen"] >= min_kat)]
    for tarih, satir in sec.iterrows():
        gun = gunler.get(tarih)
        if gun is None or len(gun) < 2:
            continue
        giris = float(gun.iloc[0]["Close"])  # auction/acilis fiyati
        if not np.isfinite(giris) or giris <= 0:
            continue
        ust, alt = giris * (1 + hedef), giris * (1 - stop)
        sonuc, cikis = None, None
        for _, bar in gun.iloc[1:].iterrows():
            if bar["Low"] <= alt:
                sonuc, cikis = "stop", alt
                break
            if bar["High"] >= ust:
                sonuc, cikis = "hedef", ust
                break
        if sonuc is None:
            sonuc, cikis = "kapanis", float(gun.iloc[-1]["Close"])
        net = cikis / giris - 1 - maliyet
        out.append(net)
    return out


def metrik(r):
    r = np.array(r)
    if len(r) == 0:
        return {"n": 0, "win_%": 0, "EV_%": 0, "PF": 0}
    kaz, kay = r[r > 0], r[r < 0]
    pf = kaz.sum() / abs(kay.sum()) if len(kay) and kay.sum() != 0 else np.inf
    return {
        "n": len(r),
        "win_%": round((r > 0).mean() * 100, 1),
        "EV_%": round(r.mean() * 100, 3),
        "PF": round(pf, 2) if np.isfinite(pf) else 99.0,
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--evren", default="test_evren.csv")
    p.add_argument("--tv_user", default=None)
    p.add_argument("--tv_pass", default=None)
    p.add_argument("--kat", type=float, default=3.0)
    p.add_argument("--min_kat", type=float, default=0.0,
                   help="sadece bu kattan buyuk sinyaller (orn 8 -> uc patlamalar)")
    p.add_argument("--baseline", type=int, default=10)
    p.add_argument("--min_ciro", type=float, default=200_000)
    p.add_argument("--komisyon", type=float, default=0.0005)
    p.add_argument("--slippage", type=float, default=0.003)
    p.add_argument("--csv", default=None,
                   help="sonuc CSV (varsayilan: optimize_grid_mk{min_kat}_slip{slippage}.csv)")
    a = p.parse_args()

    hedefler = [0.03, 0.05, 0.07]
    stoplar = [0.02, 0.03, 0.04, 0.05]

    hisseler = evren_yukle(a.evren)
    dfs = {}
    for i, h in enumerate(hisseler, 1):
        try:
            dfs[h] = cek_saatlik(h, tv_user=a.tv_user, tv_pass=a.tv_pass, sessiz=True)
            print(f"  [{i}/{len(hisseler)}] {h}: {len(dfs[h])} bar", file=sys.stderr)
        except Exception as e:
            print(f"  [{i}/{len(hisseler)}] {h}: HATA {e}", file=sys.stderr)

    csv_yolu = a.csv or f"optimize_grid_mk{int(a.min_kat)}_slip{int(a.slippage*1000):03d}.csv"
    satirlar = []
    tablolar = {}
    for hedef in hedefler:
        for stop in stoplar:
            r = []
            for h, df in dfs.items():
                r += islemler_tek(df, hedef, stop, a.baseline, a.kat,
                                  a.min_ciro, a.min_kat, a.komisyon, a.slippage)
            m = metrik(r)
            satirlar.append({
                "evren": a.evren,
                "min_kat": a.min_kat,
                "slippage": a.slippage,
                "komisyon": a.komisyon,
                "hedef_%": int(hedef * 100),
                "stop_%": int(stop * 100),
                **m,
            })
    pd.DataFrame(satirlar).to_csv(csv_yolu, index=False)

    print("=" * 70)
    print(f"HEDEF x STOP IZGARASI  | min_kat>={a.min_kat} | maliyet ~%{(a.komisyon+a.slippage)*200:.2f} cift yon")
    print("Giris: acilis/auction fiyati | cikis: gun-ici High/Low sirayla | stop-first")
    print("=" * 70)
    for metr_ad in ["EV_%", "PF", "win_%", "n"]:
        print(f"\n--- {metr_ad} ---")
        tablo = {}
        for hedef in hedefler:
            kol = {}
            for stop in stoplar:
                sat = next(s for s in satirlar
                           if s["hedef_%"] == int(hedef * 100) and s["stop_%"] == int(stop * 100))
                kol[f"stop{int(stop*100)}%"] = sat[metr_ad]
            tablo[f"hedef{int(hedef*100)}%"] = kol
        print(pd.DataFrame(tablo).to_string())
    print("\nNOT: Saatlik veride ayni bar hem hedef hem stop'u kapsarsa stop-first")
    print("varsayilir; yani sonuc KONSERVATIF (gercek dakikalik veride daha iyi")
    print("olabilir). EV ve PF pozitif/>1 olan hucre varsa edge adayidir.")
    print("Yatirim tavsiyesi degildir.")
    print(f"\n-> {csv_yolu} kaydedildi.")


if __name__ == "__main__":
    main()
