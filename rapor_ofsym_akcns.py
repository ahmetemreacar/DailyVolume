"""OFSYM & AKCNS — 1dk / 15dk / saatlik rapor."""
from __future__ import annotations

import pandas as pd
from portfoy_compound import gunluk
from veri_cache import cek_saatlik, cek_15dk, cek_1dk
from tarayici import tara

HISSELER = ["OFSYM", "AKCNS"]
RT = 2 * (0.00009 + 0.000075)


def simule_bars(gun, giris):
    tp, sl = giris * 1.03, giris * 0.97
    mh, ml = giris, giris
    for i in range(len(gun)):
        hi, lo = float(gun.iloc[i].High), float(gun.iloc[i].Low)
        mh, ml = max(mh, hi), min(ml, lo)
        hed, stp = hi >= tp, lo <= sl
        ts = str(gun.index[i])[:16]
        if hed and stp:
            return "stop", sl, ts, mh, ml
        if hed:
            return "hedef", tp, ts, mh, ml
        if stp:
            return "stop", sl, ts, mh, ml
    c = float(gun.iloc[-1].Close)
    return "gun_sonu", c, str(gun.index[-1])[:16], mh, ml


def gun_sim(dk, gun_dt):
    if len(dk) == 0:
        return None
    gm = dk.sort_index()
    gm["_t"] = gm.index.date
    by = {t: g.sort_index() for t, g in gm.groupby("_t")}
    if gun_dt not in by:
        return None
    gun = by[gun_dt]
    giris = float(gun.iloc[0].Open)
    s, c, t, mh, ml = simule_bars(gun, giris)
    net = (c / giris - 1) - RT
    return {
        "tarih": str(gun_dt),
        "bar_sayisi": len(gun),
        "ilk_bar": str(gun.index[0])[11:16],
        "son_bar": str(gun.index[-1])[11:16],
        "giris": round(giris, 2),
        "high": round(float(gun.High.max()), 2),
        "low": round(float(gun.Low.min()), 2),
        "kapanis": round(float(gun.iloc[-1].Close), 2),
        "sebep": s,
        "cikis": round(c, 2),
        "cikis_saat": t[11:16],
        "getiri_%": round(net * 100, 2),
        "mfe_%": round((mh / giris - 1) * 100, 2),
        "mae_%": round((ml / giris - 1) * 100, 2),
    }


def son_saatlik_gun(hourly, n=8):
    hd = {t: g.sort_index() for t, g in hourly.groupby(hourly.index.date)}
    son = max(hd.keys())
    g = hd[son]
    d = gunluk(hourly)
    bl = d["ovol"].rolling(20, min_periods=20).mean().shift(1)
    bl_val = float(bl.loc[son]) if son in bl.index and not pd.isna(bl.loc[son]) else None
    rows = []
    cum = 0.0
    for idx, row in g.head(n).iterrows():
        cum += float(row.Volume)
        kat = cum / bl_val if bl_val else None
        rows.append({
            "saat": str(idx)[11:16],
            "open": round(float(row.Open), 2),
            "high": round(float(row.High), 2),
            "low": round(float(row.Low), 2),
            "close": round(float(row.Close), 2),
            "volume": int(row.Volume),
            "kum_kat": round(kat, 1) if kat else None,
        })
    return son, bl_val, rows


def main():
    rows_kapsam, rows_tara, rows_hist, rows_sim, rows_saat = [], [], [], [], []

    for h in HISSELER:
        hourly = cek_saatlik(h, yenile=True)
        d15 = cek_15dk(h, yenile=True)
        d1 = cek_1dk(h, yenile=True)

        r = tara(hourly, 20, 252, 0.20)
        if r:
            rows_tara.append({"hisse": h, **r})

        for name, df in [("saatlik", hourly), ("15dk", d15), ("1dk", d1)]:
            rows_kapsam.append({
                "hisse": h, "tf": name,
                "baslangic": str(df.index.min().date()) if len(df) else "-",
                "bitis": str(df.index.max().date()) if len(df) else "-",
                "bar": len(df),
            })

        d = gunluk(hourly)
        if len(d) >= 22:
            bl = d["ovol"].rolling(20, min_periods=20).mean().shift(1)
            hi52 = d["High"].rolling(252, min_periods=126).max().shift(1)
            lo52 = d["Low"].rolling(252, min_periods=126).min().shift(1)
            dunk = d["Close"].shift(1)
            for t in d.index[-8:]:
                if pd.isna(bl.loc[t]) or bl.loc[t] <= 0:
                    continue
                ov = float(d.loc[t, "ovol"])
                op = float(d.loc[t, "Open"])
                H, L = float(hi52.loc[t]), float(lo52.loc[t])
                if H <= L:
                    continue
                kat = ov / bl.loc[t]
                pos52 = (op - L) / (H - L)
                dk_c = float(dunk.loc[t])
                gy = float(d.loc[t, "High"])
                taze = dk_c < H and gy >= H
                if pos52 <= 0.20:
                    g = "DIP"
                elif taze:
                    g = "KIRILIM"
                elif pos52 >= 0.80:
                    g = "tepe"
                else:
                    g = "orta"
                rows_hist.append({
                    "hisse": h, "tarih": str(t), "kat": round(kat, 1),
                    "grup": g, "pos52": round(pos52, 2), "acilis": round(op, 2),
                    "ciro_TL": int(op * ov), "5x+": kat >= 5,
                })

        gunler = sorted({t for t in d15.groupby(d15.index.date).groups.keys()})[-3:] if len(d15) else []
        for gun_dt in gunler:
            for tf, df in [("1dk", d1), ("15dk", d15)]:
                a = gun_sim(df, gun_dt)
                if a:
                    rows_sim.append({"hisse": h, "tf": tf, **a})

        if len(hourly):
            son, bl_val, bars = son_saatlik_gun(hourly)
            for b in bars:
                rows_saat.append({"hisse": h, "tarih": str(son), "baseline_ovol": int(bl_val) if bl_val else None, **b})

    print("=" * 80)
    print("OFSYM & AKCNS — 1dk / 15dk / SAATLIK RAPOR")
    print("=" * 80)

    print("\n## 1) CANLI TARAMA (son gun, saatlik acilis)")
    print(pd.DataFrame(rows_tara).to_string(index=False) if rows_tara else "yok")

    print("\n## 2) VERI KAPSAMI")
    print(pd.DataFrame(rows_kapsam).to_string(index=False))

    print("\n## 3) SON IS GUNLERI (acilis hacmi)")
    dfh = pd.DataFrame(rows_hist).sort_values(["hisse", "tarih"])
    print(dfh.to_string(index=False))

    print("\n## 4) GUNLUK SIM (acilis giris, TP3/SL3)")
    dfs = pd.DataFrame(rows_sim).sort_values(["hisse", "tarih", "tf"])
    cols = ["hisse", "tf", "tarih", "giris", "high", "low", "kapanis", "sebep",
            "getiri_%", "mfe_%", "mae_%", "bar_sayisi", "ilk_bar", "son_bar"]
    print(dfs[cols].to_string(index=False))

    print("\n## 5) SAATLIK BAR (son gun, ilk 8 saat)")
    print(pd.DataFrame(rows_saat).to_string(index=False))

    out = {
        "tarama": pd.DataFrame(rows_tara),
        "kapsam": pd.DataFrame(rows_kapsam),
        "tarihsel": dfh,
        "simulasyon": dfs,
        "saatlik": pd.DataFrame(rows_saat),
    }
    with pd.ExcelWriter("rapor_ofsym_akcns.xlsx", engine="openpyxl") as w:
        for name, df in out.items():
            if len(df):
                df.to_excel(w, sheet_name=name[:31], index=False)
    dfs.to_csv("rapor_ofsym_akcns.csv", index=False)
    print("\n-> rapor_ofsym_akcns.csv | rapor_ofsym_akcns.xlsx")


if __name__ == "__main__":
    main()
