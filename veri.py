"""
veri.py - Saatlik BIST verisi cekme (TradingView oncelikli, yfinance yedek).

Stratejimiz gunun ILK saatlik barini "acilis hacmi" olarak kullanir. Saatlik
veride ucretsiz olarak ~2 yil geriye gidilebilir, bu da backtest icin yeterli.

Kaynaklar:
  1) tvdatafeed (TradingView)  -> istek basina 5000 bar (~2 yil saatlik)
  2) yfinance (.IS)            -> 1h icin ~730 gun

Kullanim:
    from veri import cek_saatlik
    df = cek_saatlik("QUAGR")          # otomatik kaynak secimi
    df = cek_saatlik("QUAGR", tv_user="x", tv_pass="y")  # TV girisli (daha stabil)

Cikti standart sema: Open, High, Low, Close, Volume  (DatetimeIndex, Istanbul TZ)
"""
from __future__ import annotations
import sys
import pandas as pd

STD = ["Open", "High", "Low", "Close", "Volume"]


def _normalize(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or len(df) == 0:
        return pd.DataFrame(columns=STD)
    ren = {}
    for c in df.columns:
        lc = str(c).strip().lower()
        if lc.startswith("open"):
            ren[c] = "Open"
        elif lc.startswith("high"):
            ren[c] = "High"
        elif lc.startswith("low"):
            ren[c] = "Low"
        elif lc.startswith("close") or lc.startswith("adj"):
            ren[c] = "Close"
        elif lc.startswith("vol") or "hacim" in lc:
            ren[c] = "Volume"
    df = df.rename(columns=ren)
    df = df[[c for c in STD if c in df.columns]].copy()
    if not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index, errors="coerce")
    df = df[~df.index.isna()].sort_index()
    for c in df.columns:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    # Istanbul saatine cevir (TZ varsa). Acilis barini dogru yakalamak icin sart.
    try:
        if df.index.tz is None:
            df.index = df.index.tz_localize("Europe/Istanbul")
        else:
            df.index = df.index.tz_convert("Europe/Istanbul")
    except Exception:
        pass
    return df.dropna(how="all")


def _via_tvdatafeed(hisse, n_bars, tv_user, tv_pass):
    from tvDatafeed import TvDatafeed, Interval
    tv = TvDatafeed(tv_user, tv_pass) if tv_user else TvDatafeed()
    df = tv.get_hist(symbol=hisse, exchange="BIST",
                     interval=Interval.in_1_hour, n_bars=n_bars)
    return _normalize(pd.DataFrame(df))


def _via_yfinance(hisse, n_bars):
    import yfinance as yf
    sym = hisse if hisse.endswith(".IS") else f"{hisse}.IS"
    df = yf.download(sym, period="730d", interval="1h",
                     auto_adjust=False, progress=False)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return _normalize(df)


def cek_saatlik(hisse: str, n_bars: int = 5000,
                tv_user: str | None = None, tv_pass: str | None = None,
                sessiz: bool = False) -> pd.DataFrame:
    """Saatlik OHLCV cek. Once tvdatafeed, olmazsa yfinance.

    DIKKAT: Acilis hacmi stratejisi icin auto_adjust=False kullaniyoruz; ham
    hacim ve ham fiyat istiyoruz (bolunme-temettu duzeltmesi hacmi bozar)."""
    kod = hisse.replace(".IS", "")
    hatalar = []
    for ad, fn in (("tvdatafeed", lambda: _via_tvdatafeed(kod, n_bars, tv_user, tv_pass)),
                   ("yfinance", lambda: _via_yfinance(kod, n_bars))):
        try:
            df = fn()
            if df is not None and len(df) > 0 and "Close" in df.columns:
                if not sessiz:
                    print(f"[veri] {kod}: kaynak={ad} satir={len(df)}", file=sys.stderr)
                df.attrs.update(kaynak=ad, hisse=kod)
                return df
            hatalar.append(f"{ad}: bos veri")
        except ImportError:
            hatalar.append(f"{ad}: kurulu degil")
        except Exception as e:
            hatalar.append(f"{ad}: {type(e).__name__}: {e}")
    raise RuntimeError(f"{kod} verisi cekilemedi:\n  " + "\n  ".join(hatalar))


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("hisse")
    p.add_argument("--tv_user", default=None)
    p.add_argument("--tv_pass", default=None)
    a = p.parse_args()
    df = cek_saatlik(a.hisse, tv_user=a.tv_user, tv_pass=a.tv_pass)
    print(df.tail(8))
