import pandas as pd
from portfoy_backtest import cek_1dk

for hisse, gun in [("INVEO", "2026-05-15"), ("KFEIN", "2026-05-20"), ("GSDHO", "2026-05-18")]:
    df = cek_1dk(hisse)
    print("=" * 60)
    if len(df) == 0:
        print(hisse, "VERI YOK"); continue
    print(hisse, "| index tz:", getattr(df.index, "tz", None), "| toplam bar:", len(df))
    g = df[df.index.strftime("%Y-%m-%d") == gun].sort_index()
    print(f"{gun} | o gune ait bar sayisi:", len(g))
    if len(g):
        print("Ilk 8 bar (zaman damgasiyla):")
        print(g.head(8)[["Open", "High", "Low", "Close", "Volume"]].to_string())
        print("ILK Open =", round(float(g.iloc[0]["Open"]), 4),
              "| min Low =", round(float(g["Low"].min()), 4),
              "| max High =", round(float(g["High"].max()), 4),
              "| son Close =", round(float(g.iloc[-1]["Close"]), 4))
