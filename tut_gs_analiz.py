"""Gun sonu satilanlari TP/SL'ye ulasana kadar tut — aylik karsilastirma."""
from __future__ import annotations

import argparse
import datetime as dt
from collections import defaultdict

import pandas as pd

from simule_intraday import seans_filtre, simule_tut
from veri_cache import cek_1dk, cek_15dk

TARGET = STOP = 0.03
RT = 2 * (0.00009 + 0.000075)
SERMAYE = 100_000


def _bars_by_day(df):
    if len(df) == 0:
        return {}
    gm = df.sort_index()
    gm["_t"] = gm.index.date
    return {t: g.sort_index() for t, g in gm.groupby("_t")}


def gunler_hisse(hisse: str, bas: dt.date, son: dt.date):
    d1, d15 = cek_1dk(hisse), cek_15dk(hisse)
    by = _bars_by_day(d1)
    for k, v in _bars_by_day(d15).items():
        if k not in by:
            by[k] = v
    days = sorted(t for t in by.keys() if bas <= t <= son)
    return by, days


def compound(rows):
    by = defaultdict(list)
    for r in rows:
        by[r["tarih"]].append(r)
    cash = float(SERMAYE)
    for d in sorted(by.keys()):
        poz = cash / len(by[d])
        cash = sum(poz * (1 + t["getiri_%"] / 100) for t in by[d])
    return cash


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--csv", default="haziran_2026_dipkir.csv")
    p.add_argument("--son", default="2026-06-30")
    p.add_argument("--onek", default="haziran")
    a = p.parse_args()
    son = pd.Timestamp(a.son).date()

    df = pd.read_csv(a.csv)
    cols = list(df.columns)
    rows_tut, detay = [], []

    for _, r in df.iterrows():
        hisse, giris = r["hisse"], float(r["giris"])
        bas = pd.Timestamp(r["tarih"]).date()
        by, gun_list = gunler_hisse(hisse, bas, son)
        gun_list = [d for d in gun_list if d >= bas]

        if r["sebep"] in ("hedef", "stop") or not gun_list:
            rows_tut.append(r.to_dict())
            continue

        sebep, cikis, nerede, tut_gun = simule_tut(by, gun_list, giris)
        net = round((cikis / giris - 1 - RT) * 100, 2)
        rec = r.to_dict()
        rec.update({"sebep": sebep, "cikis": round(cikis, 4), "cikis_saat": nerede,
                    "getiri_%": net, "tut_gun": tut_gun})
        rows_tut.append(rec)
        detay.append({
            "tarih": r["tarih"], "hisse": hisse, "grup": r["grup"],
            "giris": giris, "mevcut_get%": r["getiri_%"],
            "tut_sebep": sebep, "tut_get%": net, "tut_gun": tut_gun,
            "nerede": nerede, "fark_%": round(net - r["getiri_%"], 2),
        })

    son_mevcut = compound(df.to_dict("records"))
    son_tut = compound(rows_tut)
    gs = df[df["sebep"] == "gun_sonu"]
    ddf = pd.DataFrame(detay)

    ddf.to_csv(f"{a.onek}_tut_gs_detay.csv", index=False)
    pd.DataFrame(rows_tut).to_csv(f"{a.onek}_tut_gs_dipkir.csv", index=False)

    iyilesen = (ddf["fark_%"] > 0).sum() if len(ddf) else 0
    kotulesen = (ddf["fark_%"] < 0).sum() if len(ddf) else 0
    ayni = (ddf["fark_%"] == 0).sum() if len(ddf) else 0
    hedef_tut = (ddf["tut_sebep"] == "hedef").sum() if len(ddf) else 0
    stop_tut = (ddf["tut_sebep"] == "stop").sum() if len(ddf) else 0

    print("=" * 72)
    print(f"{a.onek.upper()} | Gun sonu sat vs TP/SL'ye kadar tut (max {son})")
    print("=" * 72)
    print(f"Gun sonu islem: {len(gs)} / {len(df)}")
    print(f"\nCompound ({len(df)} islem):")
    print(f"  Mevcut:  {son_mevcut:,.0f} TL ({(son_mevcut/SERMAYE-1)*100:+.2f}%)")
    print(f"  Tut:     {son_tut:,.0f} TL ({(son_tut/SERMAYE-1)*100:+.2f}%)")
    print(f"  Fark:    {son_tut-son_mevcut:+,.0f} TL ({(son_tut/son_mevcut-1)*100:+.2f}% rel)")
    print(f"\nGS->tut: {iyilesen} iyilesir | {kotulesen} kotulesir | {ayni} ayni")
    print(f"  Tut sonucu: {hedef_tut} hedef | {stop_tut} stop | "
          f"{len(ddf)-hedef_tut-stop_tut} veri_bitti")
    if len(ddf):
        print("\n## Detay")
        print(ddf.sort_values("fark_%", ascending=False).to_string(index=False))
    print(f"\n-> {a.onek}_tut_gs_detay.csv")


if __name__ == "__main__":
    main()
