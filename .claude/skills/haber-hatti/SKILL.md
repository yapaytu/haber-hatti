---
name: haber-hatti
description: Kendi kendine çalışan haber sitesi kurar ve yönetir. Kaynakları tarar, Claude ile Türkçe haber yazdırır, denetler, taslağı bekletip süre dolunca yayınlar, siteyi kurar. "haber hattı", "haber sitesi kur", "otomatik haber", "/haber-hatti" denince kullan.
---

# Haber Hattı

Bu klasördeki `hat.py` her şeyi yapar. Python 3.9+ ve Claude Code yeter; ek paket yok.

## İlk kurulum (kullanıcıyla birlikte)
1. Kullanıcıya sor: site adı, slogan, konu (yapay zekâ, oyun, ekonomi, spor…), alan adı (yoksa sonra).
2. `ayar.json` dosyasını buna göre düzenle. Konu yapay zekâ değilse `kaynaklar` listesini o konunun **RSS/Atom** beslemeleriyle değiştir:
   - Önce şirketlerin/kurumların kendi duyuru beslemeleri (`"birincil": true`), sonra güvenilir medya.
   - Her beslemeyi `curl -sL <url> | head -c 400` ile dene; XML dönmüyorsa listeye ekleme.
   - Genel bir besleme konudışı içerik de veriyorsa `filtre` (düzenli ifade) ekle.
3. `python3 hat.py topla` çalıştır; aday çıkmıyorsa kaynakları düzelt.
4. `python3 hat.py tur` ile ilk turu çalıştır. Taslaklar `taslak/` klasörüne düşer.
5. `python3 hat.py durum` ile taslakları göster. Kullanıcı birini okuyup onaylamak isterse `python3 hat.py onayla <slug>`.
6. Site `site/` klasöründe. `open site/index.html` ile göster.

## Otomatik çalıştırma
Günde 3 tur önerilir (09:00, 14:00, 20:00) ve süresi dolan taslakları yayınlamak için saatlik kontrol:
```
crontab -e
0 9,14,20 * * * cd /TAM/YOL/haber-hatti && /usr/bin/python3 hat.py tur >> durum/log.txt 2>&1
15 * * * * cd /TAM/YOL/haber-hatti && /usr/bin/python3 hat.py yayinla >> durum/log.txt 2>&1
```
`/TAM/YOL` yerine `pwd` çıktısını yaz. Bilgisayar kapalıyken çalışmaz; sürekli çalışsın isteyen için bir sunucuya (ör. ücretsiz Oracle Cloud makinesi) kurulumu anlat. Cron ortamında `claude` komutu bulunmuyorsa satırın başına `PATH=...` ekle (`which claude`).

## Yayına alma
`site/` klasörü düz HTML'dir. Ücretsiz seçenekler: Cloudflare Pages, Netlify (klasörü sürükle bırak), GitHub Pages. Kullanıcının seçtiğini adım adım kur; `ayar.json` içindeki `adres` alanını gerçek adresle güncelle ve `python3 hat.py site` çalıştır.

## Kurallar
- Haberlerde kaynakta olmayan bilgi olmaz; `GOREV.md` bunu yazara söyler, `hat.py denetle` kalıpları yakalar. Denetimi gevşetme.
- Yazar, `taslak/` ve `durum/son-calisma.json` dışında dosyaya dokunursa tur iptal edilir. Bu kontrolü kaldırma.
- Kullanıcı isterse bekleme süresini (`bekleme_saat`) değiştir; 0 yaparsa taslaklar beklemeden yayınlanır, bunun riskini söyle.
