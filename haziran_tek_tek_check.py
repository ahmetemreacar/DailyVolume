"""Haziran DIP+KIRILIM: her islemi tek tek dogrula (eski vs yeni sim)."""
from __future__ import annotations

import sys

import pandas as pd

from simule_intraday import simule_gun, simule_gun_eski, seans_filtre
from veri_cache import cek_1dk, cek_15dk

TARGET = STOP = 0.03
RT = 2 * (0.00009 + 0.000075)


def _bars_by_day(df):
    if len(df) == 0:
        return {}
    gm = df.sort_index()
    gm["_t"] = gm.index.date
    return {t: g.sort_index() for t, g in gm.groupby("_t")}


def gun_veri(hisse: str, tarih: str):
    gun_dt = pd.Timestamp(tarih).date()
    d1 = cek_1dk(hisse)
    d15 = cek_15dk(hisse)
    by1, by15 = _bars_by_day(d1), _bars_by_day(d15)
    if gun_dt in by1:
        return "1dk", by1[gun_dt]
    if gun_dt in by15:
        return "15dk", by15[gun_dt]
    return None, None


def mfe(gun, giris):
    g = seans_filtre(gun)
    if len(g) == 0:
        g = gun.sort_index()
    mh = float(g["High"].max())
    ml = float(g["Low"].min())
    return mh, ml, round((mh / giris - 1) * 100, 2), round((ml / giris - 1) * 100, 2)


def check_one(tarih, hisse, grup, rapor_row, eski_rapor):
    tf, gun = gun_veri(hisse, tarih)
    if gun is None or len(gun) < 2:
        return {
            "tarih": tarih, "hisse": hisse, "grup": grup, "durum": "VERI_YOK",
            "not": "intraday veri yok",
        }
    giris = float(rapor_row["giris"]) if rapor_row is not None else float(seans_filtre(gun).iloc[0]["Open"])
    tp, sl = giris * 1.03, giris * 0.97

    eski = simule_gun_eski(gun, giris, TARGET, STOP)
    yeni = simule_gun(gun, giris, TARGET, STOP)
    mh, ml, max_p, min_p = mfe(gun, giris)

    def net(sebep, cikis):
        return round((cikis / giris - 1 - RT) * 100, 2)

    eski_g = net(eski[0], eski[1])
    yeni_g = net(yeni[0], yeni[1])

    degisti = eski[0] != yeni[0]
    rapor_fark = eski_rapor and (
        eski_rapor.get("sebep") != yeni[0] or abs(float(eski_rapor.get("getiri_%", 0)) - yeni_g) > 0.01
    )
    rapor_uyum = rapor_row is not None and rapor_row.get("sebep") == yeni[0]

    # suphe: max>=TP ama stop
    suphe = yeni[0] == "stop" and max_p >= TARGET * 100 - 0.05

    if degisti:
        durum = "DEGISTI"
        not_ = f"eski={eski[0]}@{eski[2]} -> yeni={yeni[0]}@{yeni[2]}"
    elif suphe:
        durum = "SUPHELI"
        not_ = f"stop ama max {max_p}% >= TP"
    elif not rapor_uyum and rapor_row is not None:
        durum = "UYUMSUZ"
        not_ = f"rapor={rapor_row.get('sebep')} sim={yeni[0]}"
    elif rapor_fark:
        durum = "GUNCELLENDI"
        not_ = f"eski rapor={eski_rapor.get('sebep')} -> yeni={yeni[0]}"
    else:
        durum = "OK"
        not_ = ""

    return {
        "tarih": tarih, "hisse": hisse, "grup": grup, "tf": tf,
        "giris": round(giris, 4), "tp": round(tp, 4), "sl": round(sl, 4),
        "eski_sebep": eski[0], "eski_cikis": round(eski[1], 4), "eski_saat": eski[2],
        "eski_getiri_%": eski_g,
        "yeni_sebep": yeni[0], "yeni_cikis": round(yeni[1], 4), "yeni_saat": yeni[2],
        "yeni_getiri_%": yeni_g,
        "rapor_sebep": rapor_row.get("sebep") if rapor_row is not None else "",
        "rapor_getiri_%": rapor_row.get("getiri_%") if rapor_row is not None else "",
        "max_fiyat": round(mh, 4), "min_fiyat": round(ml, 4),
        "max_%": max_p, "min_%": min_p,
        "durum": durum, "not": not_,
    }


def main():
    yeni_df = pd.read_csv("haziran_2026_dipkir.csv") if __import__("os").path.exists("haziran_2026_dipkir.csv") else None
    eski_df = pd.read_csv("haziran_2026_dipkir_eski.csv") if __import__("os").path.exists("haziran_2026_dipkir_eski.csv") else None
    kaynak = yeni_df if yeni_df is not None else eski_df
    if kaynak is None:
        print("haziran_2026_dipkir.csv bulunamadi", file=sys.stderr)
        sys.exit(1)

    eski_map = {}
    if eski_df is not None:
        for _, r in eski_df.iterrows():
            eski_map[(r["tarih"], r["hisse"])] = r.to_dict()

    rows = []
    print("=" * 100)
    print("HAZIRAN TEK TEK CHECK | yeni=OHLC + seans>=10:00 + SL 10:15 sonrasi")
    print("=" * 100)

    for i, r in kaynak.sort_values(["tarih", "hisse"]).iterrows():
        key = (r["tarih"], r["hisse"])
        rec = check_one(r["tarih"], r["hisse"], r["grup"], r.to_dict(), eski_map.get(key))
        rows.append(rec)

        print(f"\n[{len(rows):02d}] {rec['tarih']} {rec['hisse']} ({rec.get('grup','?').upper()}) "
              f"[{rec.get('durum','?')}]")
        if rec.get("durum") == "VERI_YOK":
            print(f"    !! {rec['not']}")
            continue
        print(f"    TF={rec['tf']} | Giris={rec['giris']} TP={rec['tp']} SL={rec['sl']}")
        print(f"    Max={rec['max_fiyat']} ({rec['max_%']}%) | Min={rec['min_fiyat']} ({rec['min_%']}%)")
        print(f"    ESKI: {rec['eski_sebep']} @ {rec['eski_cikis']} ({rec['eski_saat']}) -> {rec['eski_getiri_%']:+.2f}%")
        print(f"    SIM:  {rec['yeni_sebep']} @ {rec['yeni_cikis']} ({rec['yeni_saat']}) -> {rec['yeni_getiri_%']:+.2f}%")
        if rec.get("not"):
            print(f"    >> {rec['not']}")

    out = pd.DataFrame(rows)
    out.to_csv("haziran_tek_tek_check.csv", index=False)

    print("\n" + "=" * 100)
    print("OZET")
    for d in ["OK", "DEGISTI", "SUPHELI", "GUNCELLENDI", "UYUMSUZ", "VERI_YOK"]:
        n = (out["durum"] == d).sum()
        if n:
            print(f"  {d}: {n}")
    deg = out[out["durum"] == "DEGISTI"]
    if len(deg):
        print("\nDegisen islemler:")
        for _, r in deg.iterrows():
            print(f"  {r['tarih']} {r['hisse']}: {r['eski_sebep']} -> {r['yeni_sebep']} "
                  f"({r['eski_getiri_%']:+.2f}% -> {r['yeni_getiri_%']:+.2f}%)")
    print("\n-> haziran_tek_tek_check.csv")


if __name__ == "__main__":
    main()
