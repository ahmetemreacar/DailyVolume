"""Dogrulanmis haziran verisinden markdown rapor uret."""
from __future__ import annotations

from collections import defaultdict

import numpy as np
import pandas as pd

SERMAYE = 100_000


def compound_allin(df):
    by_day = defaultdict(list)
    for _, r in df.iterrows():
        by_day[r["tarih"]].append(r)
    cash = float(SERMAYE)
    gunler = []
    for d in sorted(by_day.keys()):
        todays = by_day[d]
        poz = cash / len(todays)
        cash = sum(poz * (1 + t["getiri_%"] / 100) for t in todays)
        gunler.append({"tarih": d, "olay": len(todays), "portfoy": round(cash, 0)})
    return cash, pd.DataFrame(gunler)


def hisse_ozet(df):
    rows = []
    for (h, g), sub in df.groupby(["hisse", "grup"]):
        rets = sub["getiri_%"].values / 100
        comp = (np.prod(1 + rets) - 1) * 100
        sb = sub["sebep"].value_counts().to_dict()
        rows.append({
            "hisse": h, "grup": g.upper(), "olay": len(sub),
            "H": sb.get("hedef", 0), "S": sb.get("stop", 0), "G": sb.get("gun_sonu", 0),
            "compound_%": round(comp, 2),
            "durum": "KAR" if comp > 0 else ("ZARAR" if comp < 0 else "BASABAS"),
            "ort_get%": round(sub["getiri_%"].mean(), 2),
            "ort_max%": round(sub["max_%"].mean(), 2),
            "ort_min%": round(sub["min_%"].mean(), 2),
        })
    return pd.DataFrame(rows).sort_values(["grup", "compound_%"], ascending=[True, False])


def main():
    df = pd.read_csv("haziran_2026_dipkir.csv")
    chk = pd.read_csv("haziran_double_check.csv")
    son, gun_df = compound_allin(df)
    getiri = (son / SERMAYE - 1) * 100
    hdf = hisse_ozet(df)
    pass_n = (chk["durum"] == "PASS").sum()

    lines = [
        "# Haziran 2026 Strateji Raporu",
        "",
        "**Strateji:** 5x+ açılış hacmi | DIP + KIRILIM | TP %3 / SL %3 | compound all-in",
        "**Evren:** evren_kucuk.csv | **Dönem:** 1–30 Haziran 2026",
        f"**Double-check:** {pass_n}/{len(chk)} işlem doğrulandı (`haziran_double_check.csv`)",
        "",
        "---",
        "",
        "## 1. Özet",
        "",
        f"| Metrik | Değer |",
        f"|--------|-------|",
        f"| Başlangıç | {SERMAYE:,.0f} TL |",
        f"| Ay sonu | **{son:,.0f} TL** |",
        f"| Getiri | **+{getiri:.2f}%** |",
        f"| İşlem | {len(df)} olay / {df['tarih'].nunique()} gün |",
        f"| Win% | {(df['getiri_%']>0).mean()*100:.1f}% |",
        f"| Hedef / Stop / Gün sonu | { (df['sebep']=='hedef').sum() } / { (df['sebep']=='stop').sum() } / { (df['sebep']=='gun_sonu').sum() } |",
        f"| Ort. işlem getiri | {df['getiri_%'].mean():+.2f}% |",
        f"| Ort. gün içi max / min | {df['max_%'].mean():+.2f}% / {df['min_%'].mean():+.2f}% |",
        "",
        "### Simülasyon kuralları (v2)",
        "- Giriş: saatlik açılış fiyatı",
        "- SL kontrolü: 10:15 sonrası (açılış wick koruması)",
        "- Bar içi: O→H→L→C yolu (stop-first değil)",
        "- Veri: 1dk varsa 1dk, yoksa 15dk",
        "",
        "---",
        "",
        "## 2. Haftalık portföy",
        "",
        "| Tarih | Olay | Portföy (TL) |",
        "|-------|------|-------------|",
    ]
    for _, r in gun_df.iterrows():
        lines.append(f"| {r['tarih']} | {int(r['olay'])} | {int(r['portfoy']):,} |")

    lines += [
        "",
        "---",
        "",
        "## 3. Hisse performansı",
        "",
        "| Hisse | Grup | Olay | H/S/G | Compound | Durum | Ort get% | Ort max% | Ort min% |",
        "|-------|------|------|-------|----------|-------|----------|----------|----------|",
    ]
    for _, r in hdf.iterrows():
        lines.append(
            f"| {r['hisse']} | {r['grup']} | {int(r['olay'])} | "
            f"{int(r['H'])}/{int(r['S'])}/{int(r['G'])} | {r['compound_%']:+.2f}% | "
            f"{r['durum']} | {r['ort_get%']:+.2f}% | {r['ort_max%']:+.2f}% | {r['ort_min%']:+.2f}% |"
        )

    lines += [
        "",
        "---",
        "",
        "## 4. Tüm işlemler",
        "",
        "| Tarih | Hisse | Grup | TF | Giriş | TP | SL | Çıkış | Saat | Sonuç | Get% | Max | Min | Max% | Min% |",
        "|-------|-------|------|-----|-------|-----|-----|-------|------|-------|------|-----|-----|------|------|",
    ]
    for _, r in df.sort_values(["tarih", "hisse"]).iterrows():
        g, tp, sl = r["giris"], round(r["giris"] * 1.03, 2), round(r["giris"] * 0.97, 2)
        lines.append(
            f"| {r['tarih']} | {r['hisse']} | {r['grup']} | {r['tf']} | {g} | {tp} | {sl} | "
            f"{r['cikis']} | {r.get('cikis_saat','')} | {r['sebep']} | {r['getiri_%']:+.2f}% | "
            f"{r['max_fiyat']} | {r['min_fiyat']} | {r['max_%']:+.1f}% | {r['min_%']:+.1f}% |"
        )

    lines += [
        "",
        "---",
        "",
        "## 5. CSV dosyaları",
        "",
        "- `haziran_2026_dipkir.csv` — işlem detayı",
        "- `haziran_kontrol_tam.csv` — kontrol tablosu",
        "- `haziran_double_check.csv` — bağımsız doğrulama",
        "- `haziran_2026_ozet.csv` — özet metrikler",
        "",
    ]

    text = "\n".join(lines)
    with open("haziran_2026_RAPOR.md", "w", encoding="utf-8") as f:
        f.write(text)
    print(text[:2000])
    print("\n... (tam rapor -> haziran_2026_RAPOR.md)")


if __name__ == "__main__":
    main()
