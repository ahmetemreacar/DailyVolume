import re
import pandas as pd

def kod(s):
    m = re.findall(r"[A-Z0-9]+", str(s).upper())
    return m[0] if m else None

evren = pd.read_csv("evren.csv")
b100 = pd.read_csv("bist100.csv")
b100_set = set(filter(None, (kod(x) for x in b100.iloc[:, 0])))

evren["hisse"] = evren["hisse"].astype(str).str.upper().str.strip()
kucuk = evren[~evren["hisse"].isin(b100_set)]
kucuk.to_csv("evren_kucuk.csv", index=False)
print(f"evren: {len(evren)} -> evren_kucuk: {len(kucuk)} (cikarilan: {len(evren)-len(kucuk)})")
