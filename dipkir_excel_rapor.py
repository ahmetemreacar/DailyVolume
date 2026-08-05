"""DIP+KIRILIM 5x/8x tum islemler ve portfoy degisimi -> Excel."""
from __future__ import annotations
import datetime as dt
import sys
from collections import defaultdict

import pandas as pd
from evren import evren_yukle
from portfoy_compound import topla, KURALLAR

KURALLAR_MAP = dict(KURALLAR)
STOP = 0.03
SERMAYE = 100_000
RT = 2 * (0.00009 + 0.000075)  # slip yok


class P:
    evren = "evren_kucuk.csv"
    tv_user = tv_pass = None
    stop = STOP
    baseline = 20
    hafta52 = 252
    dip_esik = 0.20
    ust_esik = 0.80
    min_ciro = 200_000
    min_bar = 200
    son_gun = 90
    komisyon = 0.00009
    bsmv = 0.000075
    acilis_son = "10:05"


def simule_detay(sinyaller, bar_veri, target, stop, rt, sermaye):
  """simule + gunluk portfoy ve olay logu."""
  by_day = defaultdict(list)
  for s in sinyaller:
    by_day[s["tarih"]].append(s)
  gunler = sorted({d for h in bar_veri for d in bar_veri[h]})
  cash = float(sermaye)
  acik = []
  kapali = []
  portfoy = []
  olaylar = []

  def acik_deger(D):
    t = 0.0
    for q in acik:
      bd = bar_veri.get(q["hisse"], {}).get(D)
      sc = bd[2] if bd else q["gf"]
      t += q["poz"] * (sc / q["gf"])
    return t

  onceki_toplam = sermaye
  for D in gunler:
    todays = by_day.get(D, [])
    if todays and cash > 1:
      n = len(todays)
      poz = cash / n
      for s in todays:
        acik.append({
          "hisse": s["hisse"], "gt": D, "gf": s["giris"], "poz": poz,
          "grup": s["grup"], "kat": s["kat"], "pos52": s["pos52"], "mh": s["giris"],
        })
        olaylar.append({
          "tarih": D, "olay": "GIRIS", "hisse": s["hisse"], "grup": s["grup"],
          "kat": s["kat"], "pos52": s["pos52"], "giris": s["giris"],
          "poz_tl": round(poz, 0), "nakit": 0, "acik_deger": round(acik_deger(D), 0),
          "toplam": round(acik_deger(D), 0), "detay": f"{n} hisse, {poz:,.0f} TL/hisse",
        })
      cash = 0.0

    yeni = []
    for q in acik:
      bd = bar_veri.get(q["hisse"], {}).get(D)
      if bd is None:
        yeni.append(q)
        continue
      lows, highs, _ = bd
      ust = q["gf"] * (1 + target)
      alt = q["gf"] * (1 - stop)
      basla = 1 if D == q["gt"] else 0
      cikti = False
      cf = sb = None
      for k in range(basla, len(highs)):
        hi = float(highs[k])
        lo = float(lows[k])
        if hi > q["mh"]:
          q["mh"] = hi
        hed = hi >= ust
        stp = lo <= alt
        if stp and hed:
          cf, sb = alt, "stop"
          cikti = True
          break
        if hed:
          cf, sb = ust, "hedef"
          cikti = True
          break
        if stp:
          cf, sb = alt, "stop"
          cikti = True
          break
      if cikti:
        brut = cf / q["gf"] - 1
        net = brut - rt
        donen = q["poz"] * (1 + net)
        cash += donen
        row = {
          "giris_tarih": q["gt"], "hisse": q["hisse"], "grup": q["grup"],
          "kat": q["kat"], "pos52": q["pos52"], "giris": round(q["gf"], 4),
          "poz_tl": round(q["poz"], 0), "cikis_tarih": D, "cikis": round(cf, 4),
          "sebep": sb, "getiri_%": round(net * 100, 2),
          "tl_kar": round(q["poz"] * net, 0),
          "max_gordugu_%": round((q["mh"] / q["gf"] - 1) * 100, 2),
          "gun_sayisi": (pd.Timestamp(D) - pd.Timestamp(q["gt"])).days,
        }
        kapali.append(row)
        olaylar.append({
          "tarih": D, "olay": "CIKIS", "hisse": q["hisse"], "grup": q["grup"],
          "kat": q["kat"], "pos52": q["pos52"], "giris": q["gf"],
          "poz_tl": round(q["poz"], 0), "nakit": round(cash, 0),
          "acik_deger": round(acik_deger(D), 0), "toplam": round(cash + acik_deger(D), 0),
          "detay": f"{sb} @ {cf:.4f} | getiri %{net*100:.2f} | +{donen:,.0f} TL",
        })
      else:
        yeni.append(q)
    acik = yeni

    acik_v = acik_deger(D)
    toplam = cash + acik_v
    deg = toplam - onceki_toplam
    portfoy.append({
      "tarih": D,
      "nakit": round(cash, 0),
      "acik_deger": round(acik_v, 0),
      "acik_adet": len(acik),
      "toplam": round(toplam, 0),
      "gunluk_tl": round(deg, 0),
      "gunluk_%": round(deg / onceki_toplam * 100, 2) if onceki_toplam else 0,
      "kumulatif_%": round((toplam / sermaye - 1) * 100, 2),
    })
    onceki_toplam = toplam

  for q in acik:
    gunlist = sorted(bar_veri.get(q["hisse"], {}).keys())
    sonD = [g for g in gunlist if g >= q["gt"]]
    sc = bar_veri[q["hisse"]][sonD[-1]][2] if sonD else q["gf"]
    net = (sc / q["gf"] - 1) - rt
    donen = q["poz"] * (1 + net)
    cash += donen
    D = sonD[-1] if sonD else q["gt"]
    kapali.append({
      "giris_tarih": q["gt"], "hisse": q["hisse"], "grup": q["grup"],
      "kat": q["kat"], "pos52": q["pos52"], "giris": round(q["gf"], 4),
      "poz_tl": round(q["poz"], 0), "cikis_tarih": D, "cikis": round(sc, 4),
      "sebep": "acik_kaldi", "getiri_%": round(net * 100, 2),
      "tl_kar": round(q["poz"] * net, 0),
      "max_gordugu_%": round((q["mh"] / q["gf"] - 1) * 100, 2),
      "gun_sayisi": (pd.Timestamp(D) - pd.Timestamp(q["gt"])).days,
    })
    olaylar.append({
      "tarih": D, "olay": "CIKIS", "hisse": q["hisse"], "grup": q["grup"],
      "kat": q["kat"], "pos52": q["pos52"], "giris": q["gf"],
      "poz_tl": round(q["poz"], 0), "nakit": round(cash, 0),
      "acik_deger": 0, "toplam": round(cash, 0),
      "detay": f"acik_kaldi @ {sc:.4f} | getiri %{net*100:.2f}",
    })

  return kapali, cash, pd.DataFrame(portfoy), pd.DataFrame(olaylar)


def main():
  hh, mm = map(int, P.acilis_son.split(":"))
  acilis_son = dt.time(hh, mm)
  hisseler = evren_yukle(P.evren)

  veri = {}
  for mk in [8.0, 5.0]:
    print(f"min_kat={mk}x...", file=sys.stderr)
    p = P()
    p.min_kat = mk
    sinyaller, bar_veri = topla(hisseler, p, acilis_son)
    veri[mk] = (
      [s for s in sinyaller if s["grup"] in ("dip", "kirilim")],
      bar_veri,
    )

  xlsx = "dipkir_karsilastirma.xlsx"
  ozet = []
  islem_kol = [
    "min_kat", "hedef_%", "sira", "giris_tarih", "cikis_tarih", "hisse", "grup",
    "kat", "pos52", "giris", "cikis", "sebep", "poz_tl", "getiri_%", "tl_kar",
    "max_gordugu_%", "gun_sayisi",
  ]

  with pd.ExcelWriter(xlsx, engine="openpyxl") as w:
    tum_islem = []

    for mk in [8.0, 5.0]:
      sub, bar_veri = veri[mk]
      for ad, hedef in KURALLAR:
        kapali, son_cash, pf, olay = simule_detay(sub, bar_veri, hedef, STOP, RT, SERMAYE)
        df = pd.DataFrame(kapali).sort_values(["giris_tarih", "hisse"]).reset_index(drop=True)
        df.insert(0, "hedef_%", int(ad))
        df.insert(0, "min_kat", int(mk))
        df.insert(0, "sira", range(1, len(df) + 1))
        tum_islem.append(df)

        sheet_i = f"IS_{int(mk)}x_H{ad}"[:31]
        df[islem_kol].to_excel(w, sheet_name=sheet_i, index=False)

        sheet_p = f"PF_{int(mk)}x_H{ad}"[:31]
        pf.to_excel(w, sheet_name=sheet_p, index=False)

        sheet_o = f"OLAY_{int(mk)}x_H{ad}"[:31]
        olay.to_excel(w, sheet_name=sheet_o, index=False)

        win = (df["getiri_%"] > 0).mean() * 100 if len(df) else 0
        ozet.append({
          "min_kat": f"{int(mk)}x",
          "hedef_%": int(ad),
          "baslangic_tl": SERMAYE,
          "son_tl": round(son_cash, 0),
          "getiri_%": round((son_cash / SERMAYE - 1) * 100, 2),
          "islem": len(df),
          "win_%": round(win, 1),
          "hedef": (df["sebep"] == "hedef").sum(),
          "stop": (df["sebep"] == "stop").sum(),
          "acik_kaldi": (df["sebep"] == "acik_kaldi").sum(),
          "dip": (df["grup"] == "dip").sum(),
          "kirilim": (df["grup"] == "kirilim").sum(),
        })

    pd.DataFrame(ozet).to_excel(w, sheet_name="OZET", index=False)
    tum = pd.concat(tum_islem, ignore_index=True)
    tum[islem_kol].to_excel(w, sheet_name="TUM_ISLEMLER", index=False)

  tum.to_csv("dipkir_tum_islemler.csv", index=False)
  pd.DataFrame(ozet).to_csv("dipkir_ozet.csv", index=False)
  print(f"-> {xlsx}")
  print(f"-> dipkir_tum_islemler.csv ({len(tum)} satir)")
  print(f"-> dipkir_ozet.csv")
  print("\nOZET:")
  print(pd.DataFrame(ozet).to_string(index=False))


if __name__ == "__main__":
  main()
