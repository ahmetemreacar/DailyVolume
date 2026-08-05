"""
evren.py - Hisse evreni (universe) yonetimi.

XTUMY (tum BIST) ~750 hisse. Guncel listeyi programatik cekmek icin saglam tek
bir ucretsiz API yok; pratik yontemler:

  1) TradingView'de XTUMY / "Tum Hisseler" ekranindan sembol listesini disa aktar,
     bir CSV'ye 'hisse' kolonu olarak koy: evren.csv
  2) KAP / Borsa Istanbul endeks bilesen sayfalarindan al.
  3) isyatirimhisse / borsapy endeks bilesenleri sunuyorsa oradan cek.

Survivorship bias notu: bugunku listeyi 2 yil geriye uygularsan, o donemde olup
sonra cikan/birlesip kaybolan paylari kacirirsin -> sonuc olduğundan iyi gorunur.
Mumkunse donemsel liste kullan; degilse bu kisiti raporda belirt.
"""
from __future__ import annotations
import os
import pandas as pd

# Hizli test icin kucuk ornek evren (gercek calismada evren.csv kullan)
ORNEK_EVREN = [
    "QUAGR", "THYAO", "GARAN", "ASELS", "EREGL", "KCHOL", "SISE",
    "TUPRS", "BIMAS", "FROTO", "PGSUS", "SASA", "HEKTS", "ISCTR",
]


def evren_yukle(csv_yolu: str = "evren.csv") -> list[str]:
    """evren.csv varsa 'hisse' kolonundan okur; yoksa ORNEK_EVREN doner."""
    if os.path.exists(csv_yolu):
        df = pd.read_csv(csv_yolu)
        kol = "hisse" if "hisse" in df.columns else df.columns[0]
        return [str(s).strip().upper().replace(".IS", "") for s in df[kol].dropna()]
    print(f"[evren] {csv_yolu} bulunamadi -> ORNEK_EVREN ({len(ORNEK_EVREN)} hisse) kullaniliyor")
    return list(ORNEK_EVREN)
