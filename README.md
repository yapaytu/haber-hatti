# Haber Hattı

Kendi kendine çalışan haber sitesi. [yapaytu.com](https://yapaytu.com)'un haberlerini yazan sistemin herkesin kurabileceği sürümü.

Günde üç kez uyanır ve şunları yapar:

1. **Tarar.** Seçtiğin kaynakların RSS beslemelerini okur, son 36 saatin haberlerini çıkarır, aynı olayı anlatan haberleri birleştirir ve daha önce yazdıklarını eler.
2. **Seçer ve yazar.** Claude Code adayları okur, önemli olanları seçer, kaynağı açıp okur ve haberi Türkçe, kendi cümleleriyle yazar.
3. **Denetler.** Her yazı bir denetimden geçer: kaynak linki var mı, tarih doğru mu, uzunluk yeterli mi, "devrim niteliğinde" gibi yapay zekâ kalıpları var mı. Geçemeyen yazı `ret/` klasörüne gider.
4. **Bekletir.** Geçen yazı `taslak/` klasörüne düşer. Sen 3 saat içinde bakmazsan kendisi yayınlar. İstersen hemen onaylarsın, istersen reddedersin.
5. **Siteyi kurar.** Yayınlanan haberlerden sade, hızlı, mobil uyumlu bir site ve RSS beslemesi üretir.

## Gerekenler

- Python 3.9 veya üstü (macOS'ta kurulu gelir)
- [Claude Code](https://claude.com/claude-code) ve aboneliğin. Codex kullanmak istersen `HAT_YAZAR=codex` ver.

Ek paket, API anahtarı ya da veritabanı yok.

## Kurulum

```bash
git clone https://github.com/yapaytu/haber-hatti.git
cd haber-hatti
claude
```

Claude Code açılınca şunu yaz:

```text
haber-hatti skill'ini kullan, benim için kur.
```

Claude sana site adını ve konusunu sorar, kaynakları ayarlar, ilk turu çalıştırır ve siteni gösterir. Konu yapay zekâ olmak zorunda değil: oyun, ekonomi, spor, kripto, ne istersen.

Elle yapmak istersen `ayar.json` dosyasını düzenle ve:

```bash
python3 hat.py tur       # bir tur çalıştır
python3 hat.py durum     # bekleyen taslaklar
python3 hat.py onayla <slug>
open site/index.html
```

## Komutlar

| Komut | Ne yapar |
|---|---|
| `python3 hat.py tur` | Tam tur: topla, yaz, denetle, taslağa al, süresi dolanları yayınla |
| `python3 hat.py topla` | Sadece adayları çıkarır (`durum/adaylar.json`) |
| `python3 hat.py durum` | Taslaklar ve yayına kalan süre |
| `python3 hat.py onayla <slug>` | Taslağı hemen yayınlar |
| `python3 hat.py reddet <slug>` | Taslağı çöpe atar |
| `python3 hat.py yayinla` | Süresi dolan taslakları yayınlar, siteyi kurar |
| `python3 hat.py site` | Siteyi yeniden kurar |
| `python3 hat.py denetle <dosya>` | Bir yazıyı denetler |

## Otomatik çalıştırma

`crontab -e` ile:

```
0 9,14,20 * * * cd /TAM/YOL/haber-hatti && /usr/bin/python3 hat.py tur >> durum/log.txt 2>&1
15 * * * * cd /TAM/YOL/haber-hatti && /usr/bin/python3 hat.py yayinla >> durum/log.txt 2>&1
```

Bilgisayarın kapalıyken çalışmaz. Sürekli çalışsın istiyorsan küçük bir sunucuya kur.

## Ayarlar (`ayar.json`)

| Alan | Varsayılan | Açıklama |
|---|---|---|
| `site_adi`, `slogan`, `adres` | | Sitede görünen bilgiler |
| `tur_basina` | 3 | Bir turda en fazla kaç haber |
| `gunluk` | 9 | 24 saatte en fazla kaç haber |
| `bekleme_saat` | 3 | Taslak kaç saat sonra kendiliğinden yayınlansın |
| `pencere_saat` | 36 | Kaç saatlik haberler aday olsun |
| `kaynaklar` | | RSS/Atom beslemeleri. `birincil: true` = şirketin kendi duyurusu, öncelikli. `filtre` = başlıkta aranacak düzenli ifade |

## Dikkat

- Haberleri yapay zekâ yazar. Denetim kalıpları yakalar ama her hatayı yakalamaz; taslakları ara ara oku.
- Kaynaktaki metni kopyalama; sistem haberi baştan yazdırır, uzun alıntı yapmaz. Yine de yayınladığın içerikten sen sorumlusun.
- Yazar, `taslak/` dışında bir dosyaya dokunursa tur iptal edilir. Projeyi git ile tutman önerilir.

MIT lisanslı. [YapayTU](https://yapaytu.com) tarafından hazırlandı.
