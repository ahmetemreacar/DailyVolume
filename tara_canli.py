"""Canli acilis hacmi taramasi."""
from __future__ import annotations
import argparse
import sys
import time

import pandas as pd
from evren import evren_yukle
from tarayici import tara
from veri_cache import cek_saatlik


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--evren", default="evren_kucuk.csv")
    p.add_argument("--tv_user", default=None)
    p.add_argument("--tv_pass", default=None)
    p.add_argument("--min_kat", type=float, default=5.0)
    p.add_argument("--baseline", type=int, default=20)
    p.add_argument("--hafta52", type=int, default=252)
    p.add_argument("--dip_esik", type=float, default=0.20)
    p.add_argument("--min_ciro", type=float, default=200_000)
    p.add_argument("--yenile", action="store_true", help="cache yenile (canli)")
    p.add_argument("--bekle", type=float, default=0.35, help="istek arasi sn")
    a = p.parse_args()

    hisseler = evren_yukle(a.evren)
    sonuc = []
    hatalar = []
    for i, h in enumerate(hisseler, 1):
        try:
            hourly = cek_saatlik(h, tv_user=a.tv_user, tv_pass=a.tv_pass,
                                 yenile=a.yenile)
            r = tara(hourly, a.baseline, a.hafta52, a.dip_esik)
            if r and r["kat"] >= a.min_kat and r["acilis_ciro_TL"] >= a.min_ciro:
                r["hisse"] = h
                sonuc.append(r)
        except Exception as e:
            hatalar.append(h)
            print(f"  [{i}] {h}: HATA", file=sys.stderr)
        if a.yenile and i < len(hisseler):
            time.sleep(a.bekle)
        if i % 50 == 0:
            print(f"  ... {i}/{len(hisseler)}", file=sys.stderr)

    if not sonuc:
        print("Bugun esige ulasan hisse yok.")
        if hatalar:
            print(f"({len(hatalar)} hisse veri hatasi)")
        return
    df = pd.DataFrame(sonuc).sort_values("kat", ascending=False)
    bugun = df["tarih"].mode()[0]
    df.to_csv(f"tarama_{bugun}.csv", index=False)

    dipkir = df[df["grup"].isin(["DIP", "KIRILIM"])].copy()
    kol = ["hisse", "kat", "grup", "pos52", "acilis", "acilis_ciro_TL"]
    print("=" * 68)
    print(f"CANLI TARAMA | {bugun} | kat>={a.min_kat} | DIP+KIRILIM")
    print("=" * 68)
    print(f"Yuksek hacim: {len(df)} | DIP+KIRILIM: {len(dipkir)} | hata: {len(hatalar)}")
    print("-" * 68)
    if len(dipkir):
        print(dipkir[kol].to_string(index=False))
    else:
        print("(DIP/KIRILIM yok)")
    diger = df[~df["grup"].isin(["DIP", "KIRILIM"])]
    if len(diger):
        print("\n--- DIGER (orta/tepe, bilgi) ---")
        print(diger[kol].to_string(index=False))
    print(f"\n-> tarama_{bugun}.csv")
    print("NOT: Brut takas/VBTS KAP'tan teyit et.")


if __name__ == "__main__":
    main()
