"""TV cache vs yfinance — fiyat double-check (gunluk + saatlik acilis)."""
from __future__ import annotations

import argparse
import time

import pandas as pd
import yfinance as yf

from portfoy_compound import gunluk
from veri import _normalize
from veri_cache import cek_saatlik

TOL_PCT = 0.015   # %1.5 fiyat farki esigi
TOL_ABS = 0.02    # dusuk fiyatli hisseler icin mutlak TL


def _yf_flat(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or len(df) == 0:
        return pd.DataFrame()
    if isinstance(df.columns, pd.MultiIndex):
        df = df.copy()
        df.columns = df.columns.get_level_values(0)
    drop = [c for c in df.columns if str(c).lower().startswith("adj")]
    return df.drop(columns=drop, errors="ignore")


def _yf_daily(hisse: str, bas: str, son: str) -> pd.DataFrame:
    sym = hisse if hisse.endswith(".IS") else f"{hisse}.IS"
    df = yf.download(sym, start=bas, end=son, interval="1d",
                     auto_adjust=False, progress=False)
    df = _yf_flat(df)
    if len(df) == 0:
        return pd.DataFrame()
    df = _normalize(df)
    df.index = pd.to_datetime(df.index).date
    return df


def _yf_hourly(hisse: str, bas: str, son: str) -> pd.DataFrame:
    sym = hisse if hisse.endswith(".IS") else f"{hisse}.IS"
    df = yf.download(sym, start=bas, end=son, interval="1h",
                     auto_adjust=False, progress=False)
    df = _yf_flat(df)
    if len(df) == 0:
        return pd.DataFrame()
    return _normalize(df)


def tv_gunluk(hisse: str) -> pd.DataFrame:
    return gunluk(cek_saatlik(hisse))


def fark_pct(a: float, b: float) -> float:
    if a == 0 and b == 0:
        return 0.0
    mid = (abs(a) + abs(b)) / 2 or 1
    return abs(a - b) / mid * 100


def uyumlu(a: float, b: float) -> bool:
    if pd.isna(a) or pd.isna(b):
        return False
    return abs(a - b) <= TOL_ABS or fark_pct(a, b) <= TOL_PCT * 100


def yf_acilis_1h(yf_h: pd.DataFrame, gun) -> float | None:
    """YF saatlik veride o gunun ilk bar acilisi (Istanbul)."""
    if len(yf_h) == 0:
        return None
    gun_bars = yf_h[yf_h.index.date == gun].sort_index()
    if len(gun_bars) == 0:
        return None
    return float(gun_bars.iloc[0]["Open"])


def kontrol_satir(hisse: str, tarih: str, rapor_giris: float,
                  tv_d: pd.DataFrame, yf_d: pd.DataFrame, yf_h: pd.DataFrame) -> dict:
    gun = pd.Timestamp(tarih).date()
    rec = {
        "tarih": tarih, "hisse": hisse, "rapor_giris": rapor_giris,
        "tv_kaynak": "cache_saatlik",
        "yf_kaynak": "yfinance",
    }
    if gun not in tv_d.index:
        rec["durum"] = "TV_VERI_YOK"
        return rec

    tv_row = tv_d.loc[gun]
    rec["tv_open"] = round(float(tv_row["Open"]), 4)
    rec["tv_high"] = round(float(tv_row["High"]), 4)
    rec["tv_low"] = round(float(tv_row["Low"]), 4)
    rec["tv_close"] = round(float(tv_row["Close"]), 4)

    days = list(tv_d.index)
    idx = days.index(gun)
    if idx > 0:
        rec["tv_prev_close"] = round(float(tv_d.iloc[idx - 1]["Close"]), 4)
    else:
        rec["tv_prev_close"] = None

    if gun in yf_d.index:
        yf_row = yf_d.loc[gun]
        rec["yf_open"] = round(float(yf_row["Open"]), 4)
        rec["yf_high"] = round(float(yf_row["High"]), 4)
        rec["yf_low"] = round(float(yf_row["Low"]), 4)
        rec["yf_close"] = round(float(yf_row["Close"]), 4)
        yf_days = list(yf_d.index)
        yf_idx = yf_days.index(gun)
        rec["yf_prev_close"] = round(float(yf_d.iloc[yf_idx - 1]["Close"]), 4) if yf_idx > 0 else None
    else:
        rec["yf_open"] = rec["yf_high"] = rec["yf_low"] = rec["yf_close"] = None
        rec["yf_prev_close"] = None

    yf_op = yf_acilis_1h(yf_h, gun)
    rec["yf_1h_open"] = round(yf_op, 4) if yf_op is not None else None

    # farklar
    rec["open_fark_%"] = round(fark_pct(rec["tv_open"], rec.get("yf_open", 0)), 3) if rec.get("yf_open") else None
    rec["giris_tv_fark_%"] = round(fark_pct(rapor_giris, rec["tv_open"]), 3)
    rec["giris_yf_fark_%"] = round(fark_pct(rapor_giris, rec["yf_open"]), 3) if rec.get("yf_open") else None

    sorun = []
    if rec.get("yf_open") is not None and not uyumlu(rec["tv_open"], rec["yf_open"]):
        sorun.append("OPEN")
    if rec.get("yf_high") is not None and not uyumlu(rec["tv_high"], rec["yf_high"]):
        sorun.append("HIGH")
    if rec.get("yf_low") is not None and not uyumlu(rec["tv_low"], rec["yf_low"]):
        sorun.append("LOW")
    if rec.get("yf_close") is not None and not uyumlu(rec["tv_close"], rec["yf_close"]):
        sorun.append("CLOSE")
    if rec.get("yf_prev_close") and rec.get("tv_prev_close"):
        if not uyumlu(rec["tv_prev_close"], rec["yf_prev_close"]):
            sorun.append("PREV_CLOSE")
    if not uyumlu(rapor_giris, rec["tv_open"]):
        sorun.append("RAPOR!=TV")
    if rec.get("yf_open") and not uyumlu(rapor_giris, rec["yf_open"]):
        sorun.append("RAPOR!=YF")

    rec["sorun"] = ",".join(sorun) if sorun else "OK"
    rec["durum"] = "UYUMSUZ" if sorun else "OK"
    return rec


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--csv", default="haziran_2026_dipkir.csv")
    p.add_argument("--onek", default="haziran")
    p.add_argument("--bekle", type=float, default=0.3, help="yfinance istek arasi sn")
    a = p.parse_args()

    df = pd.read_csv(a.csv)
    bas = str(df["tarih"].min())
    son = str((pd.Timestamp(df["tarih"].max()) + pd.Timedelta(days=2)).date())

    hisseler = sorted(df["hisse"].unique())
    yf_daily_cache: dict[str, pd.DataFrame] = {}
    yf_hourly_cache: dict[str, pd.DataFrame] = {}
    tv_cache: dict[str, pd.DataFrame] = {}

    print(f"YF cekiliyor: {len(hisseler)} hisse ({bas} -> {son})...", flush=True)
    for i, h in enumerate(hisseler, 1):
        try:
            yf_daily_cache[h] = _yf_daily(h, bas, son)
            time.sleep(a.bekle)
            yf_hourly_cache[h] = _yf_hourly(h, bas, son)
            tv_cache[h] = tv_gunluk(h)
        except Exception as e:
            print(f"  {h}: {e}", flush=True)
        if i % 10 == 0:
            print(f"  ... {i}/{len(hisseler)}", flush=True)
        time.sleep(a.bekle)

    rows = []
    for _, r in df.iterrows():
        h, t = r["hisse"], r["tarih"]
        rows.append(kontrol_satir(
            h, t, float(r["giris"]),
            tv_cache.get(h, pd.DataFrame()),
            yf_daily_cache.get(h, pd.DataFrame()),
            yf_hourly_cache.get(h, pd.DataFrame()),
        ))

    out = pd.DataFrame(rows)
    out.to_csv(f"{a.onek}_fiyat_double_check.csv", index=False)

    ok = (out["durum"] == "OK").sum()
    uyumsuz = out[out.get("sorun", pd.Series(dtype=str)) != "OK"] if "sorun" in out.columns else out[out["durum"] != "OK"]

    print("=" * 80)
    print(f"FIYAT DOUBLE-CHECK | TV cache (saatlik) vs yfinance | {a.onek}")
    print("=" * 80)
    print(f"Toplam: {len(out)} | OK: {ok} | Uyumsuz: {len(uyumsuz)} | Veri yok: {(out['durum']!='OK').sum() - len(uyumsuz)}")

    if len(uyumsuz):
        cols = ["tarih", "hisse", "rapor_giris", "tv_open", "yf_open", "yf_1h_open",
                "open_fark_%", "giris_tv_fark_%", "giris_yf_fark_%", "sorun"]
        print("\n## UYUMSUZ")
        print(uyumsuz[cols].to_string(index=False))

    # ozet istatistik
    if out["open_fark_%"].notna().any():
        print(f"\nOpen TV-YF ort fark: {out['open_fark_%'].mean():.3f}% | max: {out['open_fark_%'].max():.3f}%")
    print(f"\n-> {a.onek}_fiyat_double_check.csv")


if __name__ == "__main__":
    main()
