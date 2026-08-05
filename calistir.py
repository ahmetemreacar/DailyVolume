"""
calistir.py - Ana calistirici. XTUMY evreni uzerinde acilis-hacmi
anomali stratejisini test eder ve %1/%3/%5 hedeflerini kiyaslar.

Cursor'da / kendi makinende:
    python calistir.py
    python calistir.py --tv_user KULLANICI --tv_pass SIFRE   # TradingView girisli
    python calistir.py --kat 4 --baseline 15 --min_ciro 300000

Cikti:
    - Konsola hedef kiyas tablosu (beklenen deger, profit factor, win-rate...)
    - islemler.csv : tum islemlerin detayi (inceleme/optimizasyon icin)
"""
from __future__ import annotations
import argparse
import time
import sys
import pandas as pd

from veri import cek_saatlik
from backtest import hedef_taramasi
from evren import evren_yukle


def veri_topla(hisseler, tv_user=None, tv_pass=None, bekle=0.7):
    """Her hisse icin saatlik veri cek. Rate-limit'e takilmamak icin araya bekleme."""
    veri = {}
    for i, h in enumerate(hisseler, 1):
        try:
            df = cek_saatlik(h, tv_user=tv_user, tv_pass=tv_pass, sessiz=True)
            if len(df) >= 30:
                veri[h] = df
            print(f"  [{i}/{len(hisseler)}] {h}: {len(df)} bar", file=sys.stderr)
        except Exception as e:
            print(f"  [{i}/{len(hisseler)}] {h}: HATA {e}", file=sys.stderr)
        time.sleep(bekle)
    return veri


def main():
    p = argparse.ArgumentParser(description="BIST acilis-hacmi anomali backtest")
    p.add_argument("--evren", default="evren.csv")
    p.add_argument("--tv_user", default=None)
    p.add_argument("--tv_pass", default=None)
    p.add_argument("--kat", type=float, default=3.0, help="acilis hacmi / ortalama esigi")
    p.add_argument("--baseline", type=int, default=10, help="baseline gun sayisi")
    p.add_argument("--min_ciro", type=float, default=200_000, help="min acilis cirosu (TL)")
    p.add_argument("--stop", type=float, default=0.02)
    p.add_argument("--komisyon", type=float, default=0.0005)
    p.add_argument("--slippage", type=float, default=0.003,
                   help="dusuk hacimli paylarda yuksek tut")
    a = p.parse_args()

    hisseler = evren_yukle(a.evren)
    print(f"Evren: {len(hisseler)} hisse. Saatlik veri cekiliyor...", file=sys.stderr)
    veri = veri_topla(hisseler, a.tv_user, a.tv_pass)
    print(f"\nVeri cekilen hisse: {len(veri)}/{len(hisseler)}\n", file=sys.stderr)
    if not veri:
        print("Veri cekilemedi. TradingView girisi (--tv_user/--tv_pass) veya yfinance kurulumu gerekli.")
        return

    ozet, detay = hedef_taramasi(
        veri, hedefler=(0.01, 0.03, 0.05), stop=a.stop,
        baseline_gun=a.baseline, kat=a.kat, min_ciro_tl=a.min_ciro,
        komisyon=a.komisyon, slippage=a.slippage,
    )

    print("=" * 70)
    print(f"ACILIS-HACMI ANOMALI BACKTEST")
    print(f"Evren: {len(veri)} hisse | kat>={a.kat} | baseline={a.baseline}g | "
          f"min_ciro={a.min_ciro:,.0f}TL | stop=%{a.stop*100:.0f}")
    print(f"Maliyet: komisyon=%{a.komisyon*100:.3f} slippage=%{a.slippage*100:.2f} (cift yon)")
    print("=" * 70)
    print(ozet.to_string(index=False))
    print("=" * 70)
    # En iyi hedefi beklenen degere gore sec
    if ozet["islem_sayisi"].sum() > 0:
        en_iyi = ozet.loc[ozet["beklenen_deger_islem_%"].idxmax()]
        print(f"En yuksek beklenen deger: hedef %{en_iyi['hedef_%']} "
              f"(islem basina ~%{en_iyi['beklenen_deger_islem_%']}, "
              f"PF={en_iyi['profit_factor']}, n={en_iyi['islem_sayisi']})")
    print("\nNOT: Kazanma orani tek basina yaniltici. Asil olcu BEKLENEN DEGER ve")
    print("PROFIT FACTOR. n<30 ise sonuc istatistiksel olarak zayiftir.")
    print("UYARI: Bu bir analiz aracidir, yatirim tavsiyesi degildir. Brut takas")
    print("tedbirli paylarda ayni gun al-sat YAPILAMAZ - o filtre henuz eklenmedi.")

    # Detayli islemleri kaydet
    tum = []
    for hedef, d in detay.items():
        if len(d):
            tum.append(d.assign(hedef=hedef))
    if tum:
        pd.concat(tum, ignore_index=True).to_csv("islemler.csv", index=False)
        print("\n-> islemler.csv kaydedildi (detayli inceleme icin).")


if __name__ == "__main__":
    main()
