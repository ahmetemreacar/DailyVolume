"""Tavan acilis kontrolu — giris mumkun olmayan islemleri isaretle."""
from __future__ import annotations

import argparse
from collections import defaultdict

import pandas as pd

from portfoy_compound import gunluk
from tavan import tavan_detay
from veri_cache import cek_saatlik

SERMAYE = 100_000


def onceki_kapanis(hisse: str, tarih: str) -> tuple[float, float, float]:
    h = cek_saatlik(hisse)
    d = gunluk(h)
    t = pd.Timestamp(tarih).date()
    days = list(d.index)
    if t not in days:
        return 0.0, 0.0, 0.0
    idx = days.index(t)
    open_ = float(d.iloc[idx]["Open"])
    high = float(d.iloc[idx]["High"])
    if idx == 0:
        return 0.0, open_, high
    return float(d.iloc[idx - 1]["Close"]), open_, high


def compound(df):
    by = defaultdict(list)
    for _, r in df.iterrows():
        by[r["tarih"]].append(r)
    cash = float(SERMAYE)
    for d in sorted(by.keys()):
        poz = cash / len(by[d])
        cash = sum(poz * (1 + r["getiri_%"] / 100) for r in by[d])
    return cash


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--csv", default="haziran_2026_dipkir.csv")
    p.add_argument("--onek", default="haziran")
    a = p.parse_args()

    df = pd.read_csv(a.csv)
    rows = []
    for _, r in df.iterrows():
        prev_c, _, high_d = onceki_kapanis(r["hisse"], r["tarih"])
        hi = high_d if high_d > 0 else float(r.get("max_fiyat", r["giris"]))
        chk = tavan_detay(float(r["giris"]), prev_c, hi)
        rows.append({
            "tarih": r["tarih"], "hisse": r["hisse"], "grup": r["grup"],
            "kat": r["kat"], "giris": r["giris"], "onceki_kapanis": round(prev_c, 4),
            "degisim_%": chk.get("degisim_%", 0),
            "tavan": chk["tavan"], "bant_%": chk.get("bant_%", ""),
            "tavan_fiyat": chk.get("tavan_fiyat", ""),
            "tavan_kilit": chk.get("tavan_kilit", False),
            "neden": chk.get("neden", ""),
            "sebep": r["sebep"], "getiri_%": r["getiri_%"],
        })

    out = pd.DataFrame(rows)
    tavan_df = out[out["tavan"]].copy()
    temiz = df[~out["tavan"].values].copy()

    son_tum = compound(df)
    son_temiz = compound(temiz)

    out.to_csv(f"{a.onek}_tavan_kontrol.csv", index=False)
    temiz.to_csv(f"{a.onek}_dipkir_tavan_haric.csv", index=False)
    tavan_df.to_csv(f"{a.onek}_dipkir_tavan_elenen.csv", index=False)

    print("=" * 72)
    print(f"{a.onek.upper()} TAVAN ACILIS KONTROLU")
    print("=" * 72)
    print(f"Tavan acilis (giris mumkun degil): {len(tavan_df)} / {len(df)}")
    print(f"\nCompound:")
    print(f"  Tum islemler:     {son_tum:,.0f} TL ({(son_tum/SERMAYE-1)*100:+.2f}%)")
    print(f"  Tavan haric:      {son_temiz:,.0f} TL ({(son_temiz/SERMAYE-1)*100:+.2f}%)")
    print(f"  Fark:             {son_temiz-son_tum:+,.0f} TL")
    if len(tavan_df):
        print("\n## ELENEN (tavan acilis)")
        cols = ["tarih", "hisse", "grup", "kat", "giris", "onceki_kapanis",
                "degisim_%", "bant_%", "sebep", "getiri_%", "neden"]
        print(tavan_df[cols].to_string(index=False))
    print(f"\n-> {a.onek}_tavan_kontrol.csv | {a.onek}_dipkir_tavan_haric.csv")


if __name__ == "__main__":
    main()
