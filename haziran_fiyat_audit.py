"""Haziran DIP+KIRILIM: eski vs yeni simulasyon + 15dk/1dk karsilastirma."""
from __future__ import annotations

import sys

import pandas as pd
import yfinance as yf

from simule_intraday import simule_gun, simule_gun_eski, seans_filtre
from veri_cache import cek_1dk, cek_15dk
from veri import _normalize

TARGET = STOP = 0.03
RT = 2 * (0.00009 + 0.000075)


def _yf_1dk(hisse: str, gun_str: str) -> pd.DataFrame:
    try:
        sym = hisse if hisse.endswith(".IS") else hisse + ".IS"
        gun = pd.Timestamp(gun_str)
        df = yf.download(sym, start=str(gun.date()), end=str((gun + pd.Timedelta(days=1)).date()),
                         interval="1m", auto_adjust=False, progress=False)
        if df is None or len(df) == 0:
            return pd.DataFrame()
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df = _normalize(df)
        if len(df) == 0:
            return pd.DataFrame()
        try:
            df.index = df.index.tz_convert("Europe/Istanbul")
        except Exception:
            pass
        return df[df.index.date == gun.date()].sort_index()
    except Exception:
        return pd.DataFrame()


def gun_bars(hisse: str, gun_str: str):
    gun_dt = pd.Timestamp(gun_str).date()
    d1 = cek_1dk(hisse.replace(".IS", ""))
    d15 = cek_15dk(hisse.replace(".IS", ""))
    out = {}
    for label, df in [("1dk", d1), ("15dk", d15)]:
        if len(df) == 0:
            continue
        gm = df.sort_index()
        gm["_t"] = gm.index.date
        by = {t: g.sort_index() for t, g in gm.groupby("_t")}
        if gun_dt in by:
            out[label] = by[gun_dt]
    yf = _yf_1dk(hisse.replace(".IS", ""), gun_str)
    if len(yf):
        out["yf1m"] = yf
    return out


def main():
    df = pd.read_csv("haziran_2026_dipkir.csv")
    rows = []
    for _, r in df.iterrows():
        hisse, tarih = r["hisse"], r["tarih"]
        giris = float(r["giris"])
        bars = gun_bars(hisse, tarih)
        rec = {
            "tarih": tarih, "hisse": hisse, "grup": r["grup"],
            "rapor_sebep": r["sebep"], "rapor_getiri_%": r["getiri_%"],
            "max_%": r["max_%"], "tf_rapor": r["tf"],
        }
        for tf, gun in bars.items():
            if len(gun) == 0:
                continue
            g0 = seans_filtre(gun)
            giris_tf = float(g0.iloc[0]["Open"]) if len(g0) else float(gun.iloc[0]["Open"])
            eski = simule_gun_eski(gun, giris_tf, TARGET, STOP)
            yeni = simule_gun(gun, giris_tf, TARGET, STOP)
            rec[f"{tf}_eski"] = eski[0]
            rec[f"{tf}_yeni"] = yeni[0]
            rec[f"{tf}_giris"] = round(giris_tf, 4)
        rows.append(rec)

    out = pd.DataFrame(rows)
    out.to_csv("haziran_fiyat_audit.csv", index=False)

    # tutarsizliklar
    sorunlu = []
    for _, r in out.iterrows():
        max_tp = float(r["max_%"]) >= TARGET * 100 - 0.05
        rapor_stop = r["rapor_sebep"] == "stop"
        yeni_hedef = any(str(r.get(c, "")) == "hedef" for c in out.columns if c.endswith("_yeni"))
        if max_tp and rapor_stop:
            sorunlu.append(r)
        if rapor_stop and yeni_hedef:
            sorunlu.append(r)

    # dedupe
    keys = set()
    uniq = []
    for r in sorunlu:
        k = (r["tarih"], r["hisse"])
        if k not in keys:
            keys.add(k)
            uniq.append(r)

    print("=" * 80)
    print("HAZIRAN FIYAT AUDIT | eski=stop-first+15dk | yeni=OHLC+seans+SL10:15")
    print("=" * 80)
    degisen = out[
        (out.get("15dk_eski", pd.Series(dtype=str)) != out.get("15dk_yeni", pd.Series(dtype=str)))
        | (out["rapor_sebep"] != out.get("15dk_yeni", out["rapor_sebep"]))
    ]
    print(f"Toplam islem: {len(out)}")
    print(f"15dk eski->yeni degisen: {len(degisen)}")
    if "yf1m_yeni" in out.columns:
        yf_fark = out[out["rapor_sebep"] != out["yf1m_yeni"]]
        print(f"Rapor vs yfinance 1m (yeni sim): {len(yf_fark)} fark")

    print("\n## Rapor STOP ama max>=TP veya yeni sim HEDEF")
    cols = ["tarih", "hisse", "rapor_sebep", "rapor_getiri_%", "max_%",
            "15dk_eski", "15dk_yeni", "yf1m_eski", "yf1m_yeni", "tf_rapor"]
    cols = [c for c in cols if c in out.columns]
    if uniq:
        print(pd.DataFrame(uniq)[cols].drop_duplicates().to_string(index=False))
    else:
        print("(yok)")

    print("\n## Tum degisenler (15dk yeni != rapor)")
    fark = out[out["rapor_sebep"] != out.get("15dk_yeni", out["rapor_sebep"])]
    if len(fark):
        print(fark[cols].to_string(index=False))
    print("\n-> haziran_fiyat_audit.csv")


if __name__ == "__main__":
    main()
