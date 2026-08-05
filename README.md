# BIST Açılış-Hacmi Anomali Takibi

"Paranın nereye gittiğini" takip eden sistematik backtest. Hipotez: bir payın
günün **ilk saatlik barındaki açılış hacmi**, son N günün ortalamasının belirli
bir katına fırlarsa, o gün o paya para girişi olduğunun erken işaretidir.

## Kurulum (Cursor / kendi makinende)

```bash
pip install -r requirements.txt
```

TradingView verisi için (önerilen, ~2 yıl saatlik geçmiş) hesabınla giriş
yapman daha stabil olur. Girişsiz de çalışır ama bazı semboller kısıtlı gelebilir.

## Çalıştırma

```bash
# Örnek evrenle hızlı test (14 hisse):
python calistir.py

# TradingView girişli:
python calistir.py --tv_user KULLANICI --tv_pass SIFRE

# Tüm XTUMY için: evren.csv hazırla ('hisse' kolonu, ~750 sembol), sonra:
python calistir.py --evren evren.csv

# Parametre denemesi:
python calistir.py --kat 4 --baseline 15 --min_ciro 300000 --stop 0.02
```

Çıktı: konsola %1/%3/%5 hedef kıyas tablosu + `islemler.csv` (tüm işlem detayı).

## Tasarım kararları (neden böyle)

- **Saatlik veri:** Dakikalık veride ücretsiz geçmiş ~10 gün; saatlik ~2 yıl.
  Günün ilk saatlik barı açılış seansının hacmini taşır.
- **Lookahead yok:** Sinyal, gün HARİÇ önceki günlerin ortalamasıyla üretilir
  (`baseline.shift(1)`). Giriş, ilk bar kapandıktan sonra **2. barın açılışında**
  yapılır (ilk barın tam hacmi ancak kapanınca bilinir).
- **Çıkış:** Gün içinde önce +%X hedefe ulaşırsa kâr al; önce -%2 stop'a değerse
  kes; ikisi de olmazsa gün sonu kapat. Aynı barda ikisi de görülürse stop önce
  (konservatif).
- **Maliyet:** Komisyon + slippage çift yönlü düşülür. **Düşük hacimli paylarda
  slippage komisyondan çok daha büyük** — `--slippage` değerini yüksek tut.

## Önemli uyarılar

- **Brüt takas / VBTS:** QUAGR gibi küçük paylar sık sık brüt takasa alınır;
  brüt takasta aynı gün al-sat YAPILAMAZ → bu stratejinin o günkü sinyali
  uygulanamaz. Bu filtre henüz eklenmedi (sonraki adım).
- **Survivorship bias:** Bugünkü evreni 2 yıl geriye uygularsan sonuç şişebilir.
- **İstatistiksel güç:** n<30 işlemle çıkan win-rate anlamsızdır. Asıl ölçü
  **beklenen değer** ve **profit factor**, toplam getiri değil.
- Bu bir analiz aracıdır, yatırım tavsiyesi değildir. Geçmiş performans geleceği
  garanti etmez.

## Dosyalar

- `veri.py` — saatlik veri çekme (tvdatafeed → yfinance)
- `sinyal.py` — açılış-hacmi anomali sinyali
- `backtest.py` — gün-içi hedef/stop simülasyonu + hedef taraması
- `evren.py` — hisse evreni yükleme
- `calistir.py` — ana çalıştırıcı + rapor
