#!/usr/bin/env python3
"""Haber Hattı: kendi kendine çalışan haber sitesi.

Kaynakları tarar, önemli haberleri seçer, Claude Code ile Türkçe yazdırır, denetler,
taslağı bekletir ve süre dolunca (ya da sen onaylayınca) yayınlayıp siteyi kurar.
Sadece Python 3.9+ standart kütüphanesi. Yazar olarak Claude Code (`claude`) gerekir.

  python3 hat.py tur            # tam tur: topla → yaz → denetle → taslak → yayınla → site
  python3 hat.py topla          # sadece adayları çıkar (durum/adaylar.json)
  python3 hat.py durum          # taslaklar ve kalan süreleri
  python3 hat.py onayla <slug>  # taslağı hemen yayınla
  python3 hat.py reddet <slug>  # taslağı çöpe at
  python3 hat.py yayinla        # süresi dolan taslakları yayınla + siteyi kur
  python3 hat.py site           # siteyi yeniden kur (site/)
  python3 hat.py denetle <dosya.md>
"""
import difflib
import hashlib
import html
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime, parsedate_to_datetime
from pathlib import Path

KOK = Path(__file__).resolve().parent
DURUM = KOK / "durum"
TASLAK = KOK / "taslak"
YAZILAR = KOK / "yazilar"
RET = KOK / "ret"
SITE = KOK / "site"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0 Safari/537.36"
SIMDI = datetime.now(timezone.utc)
DUR = {"a", "an", "the", "and", "or", "for", "to", "of", "in", "on", "with", "its", "is", "now", "new", "how", "at", "by", "from"}


def ayar() -> dict:
    return json.loads((KOK / "ayar.json").read_text(encoding="utf-8"))


def oku_json(p: Path, varsayilan):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return varsayilan


def yaz_json(p: Path, veri):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(veri, ensure_ascii=False, indent=1), encoding="utf-8")


# ───────────────────────── 1. TOPLA ─────────────────────────

def getir(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def norm_url(u: str) -> str:
    p = urllib.parse.urlsplit(u.strip())
    q = [(k, v) for k, v in urllib.parse.parse_qsl(p.query) if not k.startswith("utm_")]
    return urllib.parse.urlunsplit((p.scheme, p.netloc.lower().removeprefix("www."), p.path.rstrip("/"), urllib.parse.urlencode(q), ""))


def norm_baslik(t: str) -> str:
    t = re.sub(r"[^\w\s]", " ", t.lower())
    return " ".join(w for w in t.split() if w not in DUR)


def benzer(a: str, b: str) -> bool:
    a, b = norm_baslik(a), norm_baslik(b)
    if not a or not b:
        return False
    if difflib.SequenceMatcher(None, a, b).ratio() > 0.6:
        return True
    sa, sb = set(a.split()), set(b.split())
    return len(sa & sb) / max(1, len(sa | sb)) > 0.5


def temiz(metin: str, n=600) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", metin or "")).strip()[:n]


def zaman_coz(s: str):
    s = (s or "").strip()
    if not s:
        return None
    try:
        z = parsedate_to_datetime(s)
    except Exception:
        try:
            z = datetime.fromisoformat(s.replace("Z", "+00:00"))
        except Exception:
            return None
    return z if z.tzinfo else z.replace(tzinfo=timezone.utc)


def besleme(url: str) -> list:
    """RSS 2.0 ve Atom beslemelerini okur."""
    kok = ET.fromstring(getir(url))
    ad = lambda e: e.tag.split("}")[-1]
    out = []
    for e in kok.iter():
        if ad(e) not in ("item", "entry"):
            continue
        d = {ad(c): c for c in e}
        baslik = (d["title"].text or "").strip() if "title" in d else ""
        link = ""
        if "link" in d:
            link = d["link"].get("href") or (d["link"].text or "")
        zaman = None
        for k in ("pubDate", "published", "updated", "date"):
            if k in d:
                zaman = zaman_coz(d[k].text)
                if zaman:
                    break
        ozet = ""
        for k in ("description", "summary", "content"):
            if k in d and d[k].text:
                ozet = temiz(d[k].text)
                break
        if baslik and link and zaman:
            out.append({"baslik": baslik, "url": link.strip(), "zaman": zaman, "ozet": ozet})
    return out


def topla() -> list:
    a = ayar()
    pencere = timedelta(hours=a.get("pencere_saat", 36))
    gorulen = oku_json(DURUM / "gorulen.json", {})
    yazilan = oku_json(DURUM / "yazilan.json", [])
    eski = [y.get("kaynak_baslik", "") for y in yazilan]
    adaylar, hatalar = [], []
    for k in a["kaynaklar"]:
        try:
            ogeler = besleme(k["url"])
        except Exception as e:
            hatalar.append(f"{k['ad']}: {e}")
            continue
        for o in ogeler:
            if SIMDI - o["zaman"] > pencere:
                continue
            if k.get("filtre") and not re.search(k["filtre"], o["baslik"] + " " + o["ozet"], re.I):
                continue
            u = norm_url(o["url"])
            if u in gorulen or any(benzer(o["baslik"], b) for b in eski):
                continue
            o.update(kaynak=k["ad"], birincil=bool(k.get("birincil")))
            adaylar.append(o)
    # aynı olayı birleştir: birincil kaynak ana, diğerleri ek bağlam
    adaylar.sort(key=lambda o: (not o["birincil"], -o["zaman"].timestamp()))
    kumeler = []
    for o in adaylar:
        for km in kumeler:
            if benzer(o["baslik"], km["baslik"]):
                km["ek_kaynaklar"].append({"ad": o["kaynak"], "url": o["url"], "baslik": o["baslik"]})
                break
        else:
            kumeler.append({**o, "ek_kaynaklar": []})
    # öncelik: birincil + birden çok kaynakta geçen (önemli) + yeni
    kumeler.sort(key=lambda o: (-(2 if o["birincil"] else 0) - len(o["ek_kaynaklar"]), -o["zaman"].timestamp()))
    secim = kumeler[:15]
    for o in secim:
        o["zaman"] = o["zaman"].isoformat()
    yaz_json(DURUM / "adaylar.json", secim)
    for o in kumeler:
        gorulen[norm_url(o["url"])] = SIMDI.isoformat()
        for e in o["ek_kaynaklar"]:
            gorulen[norm_url(e["url"])] = SIMDI.isoformat()
    sinir = (SIMDI - timedelta(days=10)).isoformat()
    yaz_json(DURUM / "gorulen.json", {u: t for u, t in gorulen.items() if t > sinir})
    print(f"{len(secim)} aday ({len(adaylar)} öğe, {len(kumeler)} olay); kaynak hatası: {len(hatalar)}")
    for h in hatalar:
        print("  !", h, file=sys.stderr)
    return secim


# ───────────────────────── 2. YAZ (Claude Code) ─────────────────────────

def iz() -> dict:
    """taslak/ ve durum/ dışındaki her dosyanın parmak izi: yazar başka dosyaya dokunmasın."""
    out = {}
    for p in KOK.rglob("*"):
        if p.is_file() and not any(x in p.parts for x in ("taslak", "durum", "site", "ret", ".git", "__pycache__")):
            out[str(p.relative_to(KOK))] = hashlib.md5(p.read_bytes()).hexdigest()
    return out


def yaz(kac: int) -> list:
    TASLAK.mkdir(exist_ok=True)
    (DURUM / "son-calisma.json").unlink(missing_ok=True)
    son = []
    for p in sorted(YAZILAR.glob("*.md"))[-60:]:
        fm, _ = ayristir(p.read_text(encoding="utf-8"))
        son.append(fm.get("baslik", ""))
    (DURUM / "son-haberler.txt").write_text("\n".join(son), encoding="utf-8")
    simdi = datetime.now().astimezone().strftime("%Y-%m-%dT%H:%M:00%z")
    simdi = simdi[:-2] + ":" + simdi[-2:]
    gorev = (KOK / "GOREV.md").read_text(encoding="utf-8") + f"\n\n---\nBu tur: ŞU ANKİ ZAMAN = {simdi}. En fazla {kac} haber yaz (daha azı da olur). Başla."
    once = iz()
    yazar = os.environ.get("HAT_YAZAR", "claude")
    if yazar == "claude":
        komut = ["claude", "-p", gorev, "--permission-mode", "acceptEdits",
                 "--allowedTools", "Read,Write,Edit,Glob,Grep,WebFetch,WebSearch,Bash(python3 hat.py denetle:*),Bash(curl:*)"]
    else:  # HAT_YAZAR=codex
        komut = ["codex", "exec", "--skip-git-repo-check", "-C", str(KOK), "-s", "workspace-write",
                 "-c", "sandbox_workspace_write.network_access=true", gorev]
    with open(DURUM / "yazar-son.txt", "w", encoding="utf-8") as log:
        r = subprocess.run(komut, cwd=KOK, stdout=log, stderr=subprocess.STDOUT, timeout=2400)
    print(f"yazar çıkışı: {r.returncode}")
    sonra = iz()
    degisen = [k for k in set(once) | set(sonra) if once.get(k) != sonra.get(k)]
    if degisen:
        print("!! yazar izin verilmeyen dosyalara dokundu, bu turun taslakları iptal:", degisen)
        print("   git kullanıyorsan `git checkout -- .` ile geri al.")
        for x in oku_json(DURUM / "son-calisma.json", []):
            (TASLAK / f"{x.get('slug', '')}.md").unlink(missing_ok=True)
        return []
    return oku_json(DURUM / "son-calisma.json", [])


# ───────────────────────── 3. DENETLE ─────────────────────────

YASAK_KALIP = [
    "—", "sadece .{1,40} değil, aynı zamanda", "değil, aynı zamanda", "önemli bir rol", "kilit rol",
    "sonuç olarak", r"(^|\. )özetle[,:]", "umarım faydalı", "gelin birlikte", "hadi başlayalım", "işte bilmeniz gerekenler",
    "günümüzde", "devrim niteliğinde", "çığır açan", "oyunun kurallarını", "kritik öneme sahip",
    "vazgeçilmez", "muazzam", "büyüleyici", "kusursuz", "eşsiz", "benzersiz", "dönüştürücü", "yolculuk",
    "heyecan verici", "dikkat çekici bir şekilde", "bu noktada belirtmek gerekir",
    "iyi haber şu ki", "işin aslı", "asıl soru şu", "peki ama", "merak etme", "lafı uzatmadan",
]
DEGIL_Y = re.compile(r"\b\w+ değil, (?!mi\b)\w+")


def ayristir(ham: str):
    """Basit ön bilgi: `anahtar: değer` satırları, `etiketler: a, b`, `kaynaklar:` altında `- ad | url`."""
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", ham, re.S)
    if not m:
        return {}, ham
    fm, son = {}, None
    for satir in m.group(1).splitlines():
        if re.match(r"^\s+-\s", satir) and son:
            fm.setdefault(son, []).append(satir.strip()[2:].strip())
            continue
        k, _, v = satir.partition(":")
        if not _:
            continue
        k, v = k.strip(), v.strip().strip('"')
        son = k
        if v:
            fm[k] = [x.strip() for x in v.split(",")] if k == "etiketler" else v
    return fm, m.group(2)


def denetle(p: Path) -> list:
    h = []
    fm, govde = ayristir(p.read_text(encoding="utf-8"))
    if not fm:
        return ["ön bilgi (--- blok) yok"]
    duz = re.sub(r"```.*?```", "", govde, flags=re.S)
    if not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", p.stem) or len(p.stem) > 80:
        h.append(f"dosya adı geçersiz: {p.stem} (küçük harf, ASCII, tire)")
    for alan in ["baslik", "ozet", "tarih", "etiketler", "kaynaklar"]:
        if not fm.get(alan):
            h.append(f"zorunlu alan eksik: {alan}")
    if len(fm.get("baslik", "")) > 75:
        h.append("baslik 75 karakteri aşıyor")
    if not 90 <= len(fm.get("ozet", "")) <= 170:
        h.append(f"ozet 90-170 karakter olmalı ({len(fm.get('ozet', ''))})")
    try:
        t = datetime.fromisoformat(fm.get("tarih", ""))
        if t.tzinfo is None:
            h.append("tarih saat dilimi içermeli (+03:00)")
        elif t > datetime.now(timezone.utc) + timedelta(minutes=5):
            h.append("tarih gelecekte")
    except Exception:
        h.append(f"tarih ISO değil: {fm.get('tarih')}")
    urller = []
    for k in fm.get("kaynaklar", []):
        ad, _, url = k.partition("|")
        if not url.strip().startswith("https://"):
            h.append(f"kaynak hatalı (ad | https://...): {k}")
        urller.append(url.strip())
    if urller and not any(u and u in govde for u in urller):
        h.append("metin içinde kaynaklardan en az birine link verilmeli")
    kelime = len(re.findall(r"\w+", re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", govde)))
    if not 350 <= kelime <= 1400:
        h.append(f"gövde 350-1400 kelime olmalı ({kelime})")
    if len(re.findall(r"^## ", govde, re.M)) < 2:
        h.append("en az 2 adet ## başlık olmalı")
    if not re.search(r"^## (Bizim yorumumuz|Bizce)", govde, re.M):
        h.append("'## Bizim yorumumuz' bölümü eksik")
    if len(DEGIL_Y.findall(duz)) > 1:
        h.append("'X değil, Y' kalıbı birden fazla")
    tum = duz.lower()
    for k in YASAK_KALIP:
        if re.search(k, tum):
            h.append(f"yapay zekâ kalıbı: {k!r}")
    return h


# ───────────────────────── 4. TASLAK → YAYIN ─────────────────────────

def taslaklar() -> list:
    out = []
    bekle = ayar().get("bekleme_saat", 3)
    for p in sorted(TASLAK.glob("*.md")):
        kalan = bekle * 3600 - (time.time() - p.stat().st_mtime)
        out.append((p, kalan))
    return out


def yayinla(zorla: str = "") -> int:
    YAZILAR.mkdir(exist_ok=True)
    n = 0
    for p, kalan in taslaklar():
        if p.stem == zorla or kalan <= 0:
            if denetle(p):
                shutil.move(str(p), RET / p.name)
                print(f"ret (denetim): {p.name}")
                continue
            shutil.move(str(p), YAZILAR / p.name)
            print(f"yayında: {p.stem}")
            n += 1
    if n:
        site()
    return n


# ───────────────────────── 5. SİTE ─────────────────────────

def md_html(md: str) -> str:
    """Haber için yeterli Markdown: ## başlık, paragraf, liste, **kalın**, *italik*, [link](url), `kod`."""
    def satir_ici(t: str) -> str:
        t = html.escape(t, quote=False)
        t = re.sub(r"`([^`]+)`", r"<code>\1</code>", t)
        t = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", t)
        t = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", t)
        return re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", lambda m: f'<a href="{html.escape(m.group(2))}">{m.group(1)}</a>', t)
    out, liste = [], None
    for blok in re.split(r"\n\s*\n", md.strip()):
        satirlar = blok.strip().splitlines()
        if satirlar[0].startswith("## "):
            out.append(f"<h2>{satir_ici(satirlar[0][3:])}</h2>")
            satirlar = satirlar[1:]
            if not satirlar:
                continue
        if all(re.match(r"^\s*([-*]|\d+\.)\s", s) for s in satirlar):
            tag = "ol" if re.match(r"^\s*\d+\.", satirlar[0]) else "ul"
            maddeler = [satir_ici(re.sub(r"^\s*([-*]|\d+\.)\s", "", s)) for s in satirlar]
            out.append(f"<{tag}>" + "".join(f"<li>{m}</li>" for m in maddeler) + f"</{tag}>")
        else:
            out.append(f"<p>{satir_ici(' '.join(satirlar))}</p>")
    return "\n".join(out)


AYLAR = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]


def tarih_tr(t: datetime) -> str:
    return f"{t.day} {AYLAR[t.month - 1]} {t.year}"


def site():
    a = ayar()
    sablon = (KOK / "sablon" / "sayfa.html").read_text(encoding="utf-8")
    SITE.mkdir(exist_ok=True)
    shutil.copy(KOK / "sablon" / "stil.css", SITE / "stil.css")
    yazilar = []
    for p in YAZILAR.glob("*.md"):
        fm, govde = ayristir(p.read_text(encoding="utf-8"))
        try:
            t = datetime.fromisoformat(fm["tarih"])
        except Exception:
            continue
        yazilar.append((t, p.stem, fm, govde))
    yazilar.sort(key=lambda x: x[0], reverse=True)

    def sayfa(baslik, aciklama, icerik, yol):
        return (sablon.replace("{{SITE}}", html.escape(a["site_adi"])).replace("{{SLOGAN}}", html.escape(a.get("slogan", "")))
                .replace("{{BASLIK}}", html.escape(baslik)).replace("{{ACIKLAMA}}", html.escape(aciklama))
                .replace("{{ICERIK}}", icerik).replace("{{KOK}}", "../" if yol else "").replace("{{YIL}}", str(SIMDI.year)))

    kartlar = []
    for i, (t, slug, fm, govde) in enumerate(yazilar):
        kaynak = "".join(f'<li><a href="{html.escape(k.partition("|")[2].strip())}" rel="nofollow">{html.escape(k.partition("|")[0].strip())}</a></li>' for k in fm.get("kaynaklar", []))
        icerik = (f'<article class="yazi"><div class="ust">{tarih_tr(t)} · {html.escape(", ".join(fm.get("etiketler", [])))}</div>'
                  f'<h1>{html.escape(fm.get("baslik", ""))}</h1><p class="giris">{html.escape(fm.get("ozet", ""))}</p>'
                  f'{md_html(govde)}<div class="kaynaklar"><h3>Kaynaklar</h3><ul>{kaynak}</ul></div>'
                  f'<p class="not">Bu haber yapay zekâ ile yazıldı, otomatik denetimden geçti ve yayından önce editör onayına sunuldu.</p></article>')
        (SITE / slug).mkdir(exist_ok=True)
        (SITE / slug / "index.html").write_text(sayfa(fm.get("baslik", ""), fm.get("ozet", ""), icerik, True), encoding="utf-8")
        kartlar.append(f'<a class="kart{" buyuk" if i == 0 else ""}" href="{slug}/"><span class="ust">{tarih_tr(t)}</span>'
                       f'<h2>{html.escape(fm.get("baslik", ""))}</h2><p>{html.escape(fm.get("ozet", ""))}</p></a>')
    ana = f'<div class="liste">{"".join(kartlar) or "<p>Henüz haber yok. İlk tur çalışınca burada görünecek.</p>"}</div>'
    (SITE / "index.html").write_text(sayfa(a["site_adi"], a.get("slogan", ""), ana, False), encoding="utf-8")
    # RSS
    adres = a.get("adres", "").rstrip("/")
    ogeler = "".join(f"<item><title>{html.escape(fm.get('baslik', ''))}</title><link>{adres}/{slug}/</link><guid>{adres}/{slug}/</guid>"
                     f"<pubDate>{format_datetime(t)}</pubDate><description>{html.escape(fm.get('ozet', ''))}</description></item>"
                     for t, slug, fm, _ in yazilar[:30])
    (SITE / "rss.xml").write_text(f'<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>{html.escape(a["site_adi"])}</title>'
                                  f"<link>{adres}/</link><description>{html.escape(a.get('slogan', ''))}</description>{ogeler}</channel></rss>", encoding="utf-8")
    print(f"site kuruldu: {len(yazilar)} haber → {SITE}/index.html")


# ───────────────────────── TUR ─────────────────────────

def tur():
    a = ayar()
    for d in (DURUM, TASLAK, YAZILAR, RET):
        d.mkdir(exist_ok=True)
    print(f"=== {datetime.now():%Y-%m-%d %H:%M} tur başladı")
    yayinla()  # önce süresi dolanlar
    yazilan = oku_json(DURUM / "yazilan.json", [])
    gun = sum(1 for x in yazilan if datetime.fromisoformat(x["zaman"]) > SIMDI - timedelta(hours=24))
    kac = max(0, min(a.get("tur_basina", 3), a.get("gunluk", 9) - gun))
    if not kac:
        print("günlük kota dolu")
        return
    if not topla():
        print("yeni aday yok")
        return
    yeni = yaz(kac)
    for x in yeni:
        p = TASLAK / f"{x.get('slug', '')}.md"
        if not p.exists():
            continue
        h = denetle(p)
        if h:
            shutil.move(str(p), RET / p.name)
            print(f"ret: {p.name} → {h[:3]}")
            continue
        yazilan.append({**x, "zaman": SIMDI.isoformat()})
        print(f"taslak: {p.stem} ({a.get('bekleme_saat', 3)} saat içinde onaylamazsan kendisi yayınlanır)")
    yaz_json(DURUM / "yazilan.json", yazilan[-500:])
    print(f"=== tur bitti")


def main():
    k = sys.argv[1:] or ["yardim"]
    if k[0] == "tur":
        tur()
    elif k[0] == "topla":
        DURUM.mkdir(exist_ok=True)
        topla()
    elif k[0] == "durum":
        t = taslaklar()
        if not t:
            print("bekleyen taslak yok")
        for p, kalan in t:
            fm, _ = ayristir(p.read_text(encoding="utf-8"))
            s = max(0, int(kalan))
            print(f"{p.stem}  ·  {s // 3600}:{s % 3600 // 60:02d} kaldı  ·  {fm.get('baslik', '')}")
    elif k[0] == "onayla" and len(k) > 1:
        print("yayınlandı" if yayinla(k[1]) else "taslak bulunamadı ya da denetimden geçmedi")
    elif k[0] == "reddet" and len(k) > 1:
        p = TASLAK / f"{k[1]}.md"
        if p.exists():
            RET.mkdir(exist_ok=True)
            shutil.move(str(p), RET / p.name)
            print("reddedildi")
        else:
            print("taslak bulunamadı")
    elif k[0] == "yayinla":
        RET.mkdir(exist_ok=True)
        print(f"{yayinla()} haber yayınlandı")
    elif k[0] == "site":
        site()
    elif k[0] == "denetle" and len(k) > 1:
        kotu = False
        for a in k[1:]:
            h = denetle(Path(a))
            print(("✗ " if h else "✓ ") + Path(a).name)
            for x in h:
                print("   -", x)
            kotu |= bool(h)
        sys.exit(1 if kotu else 0)
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
