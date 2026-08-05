"""veri_cache.py - saatlik ve 1dk veriyi YEREL DISKE onbellekler."""
import os
import pandas as pd
from veri import cek_saatlik as _saatlik_net, _normalize

CACHE = "cache"
os.makedirs(CACHE, exist_ok=True)


def _1dk_net(hisse, n_bars=5000, tv_user=None, tv_pass=None):
    kod = hisse.replace(".IS", "")
    try:
        from tvDatafeed import TvDatafeed, Interval
        tv = TvDatafeed(tv_user, tv_pass) if tv_user else TvDatafeed()
        df = _normalize(pd.DataFrame(tv.get_hist(symbol=kod, exchange="BIST",
                        interval=Interval.in_1_minute, n_bars=n_bars)))
        if len(df):
            return df
    except Exception:
        pass
    try:
        import yfinance as yf
        sym = kod if kod.endswith(".IS") else kod + ".IS"
        df = yf.download(sym, period="7d", interval="1m", auto_adjust=False, progress=False)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        return _normalize(df)
    except Exception:
        return pd.DataFrame()


def cek_saatlik(hisse, tv_user=None, tv_pass=None, sessiz=True, yenile=False):
    """yenile=True -> agdan cek, cache guncelle."""
    yol = os.path.join(CACHE, f"{hisse.replace('.IS','')}_saatlik.pkl")
    if (not yenile) and os.path.exists(yol):
        try:
            return pd.read_pickle(yol)
        except Exception:
            pass
    df = _saatlik_net(hisse, tv_user=tv_user, tv_pass=tv_pass, sessiz=sessiz)
    if len(df):
        try:
            df.to_pickle(yol)
        except Exception:
            pass
    return df


def _15dk_net(hisse, n_bars=5000, tv_user=None, tv_pass=None):
    kod = hisse.replace(".IS", "")
    try:
        from tvDatafeed import TvDatafeed, Interval
        tv = TvDatafeed(tv_user, tv_pass) if tv_user else TvDatafeed()
        return _normalize(pd.DataFrame(tv.get_hist(symbol=kod, exchange="BIST",
                        interval=Interval.in_15_minute, n_bars=n_bars)))
    except Exception:
        return pd.DataFrame()


def cek_15dk(hisse, n_bars=5000, tv_user=None, tv_pass=None, yenile=False):
    yol = os.path.join(CACHE, f"{hisse.replace('.IS', '')}_15dk.pkl")
    if (not yenile) and os.path.exists(yol):
        try:
            return pd.read_pickle(yol)
        except Exception:
            pass
    df = _15dk_net(hisse, n_bars, tv_user, tv_pass)
    if len(df):
        try:
            df.to_pickle(yol)
        except Exception:
            pass
    return df


def cek_1dk(hisse, n_bars=5000, tv_user=None, tv_pass=None, yenile=False):
    yol = os.path.join(CACHE, f"{hisse.replace('.IS','')}_1dk.pkl")
    if (not yenile) and os.path.exists(yol):
        try:
            return pd.read_pickle(yol)
        except Exception:
            pass
    df = _1dk_net(hisse, n_bars, tv_user, tv_pass)
    if len(df):
        try:
            df.to_pickle(yol)
        except Exception:
            pass
    return df
