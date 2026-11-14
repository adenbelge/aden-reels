# -*- coding: utf-8 -*-
"""FACEBOOK ETKİNLİKLERİ — GitHub tarafı (08.11.2026; sunucu App\\Services\\Sosyal\\FbEtkinlik, panel /yonetim/fb-etkinlikleri).
Meta API sayfa etkinliği açtırmaz (yalnız okur): etkinliği yetkili panelden kopyalayarak açar. Bu betik iki iş yapar:
    python tools/reels/etkinlik.py --esle      # sayfadaki etkinlikleri okur → sunucu eşler (yayınlanan iş kendiliğinden kapanır)
    python tools/reels/etkinlik.py --kapak     # kapağı eksik / değişmiş oturumların kapağını üretir (1920×1005) → imzalı PUT
    python tools/reels/etkinlik.py --gerek     # kapak gerekiyor mu (GITHUB_OUTPUT kapak=1|0) — Playwright yalnız gerekince kurulur
Anahtarlar reels_yayin ile aynı (META_SOSYAL_TOKEN, META_FB_SAYFA, REELS_ANAHTAR; ortam ya da .env)."""
import argparse, hashlib, hmac, json, os, subprocess, sys, tempfile, time
from pathlib import Path
import requests
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import reels_yayin as R   # kaynak_video, env, sayfa_jetonu, GRAPH, FB_SAYFA, INSAAT
from reels_video import JS_SABLON, AY

KOK = os.path.dirname(os.path.abspath(__file__))
SITE = 'https://adenbelge.com.tr'


def imzali(yontem, url, govde=b'', **kw):
    ts = str(int(time.time()))
    imza = hmac.new(R.env('REELS_ANAHTAR').encode(), '\n'.join([yontem, ts, hashlib.sha256(govde).hexdigest()]).encode(), hashlib.sha256).hexdigest()
    r = requests.request(yontem, url, data=govde or None, timeout=120, headers={'X-Reels-Zaman': ts, 'X-Reels-Imza': imza, **kw.pop('basliklar', {})}, **kw)
    r.raise_for_status()
    return r.json()


def plan():
    return imzali('GET', SITE + '/api/sosyal/etkinlik-plan')['plan']   # 14.11.2026: plan ucu imzalı


def esle():
    pt = R.sayfa_jetonu(R.env('META_SOSYAL_TOKEN'))
    url, prm, hepsi = f'{R.GRAPH}/{R.FB_SAYFA}/events', {'fields': 'id,name,start_time,is_canceled', 'time_filter': 'upcoming', 'limit': 100, 'access_token': pt}, []
    while url:
        j = requests.get(url, params=prm, timeout=60).json()
        if 'error' in j:
            raise SystemExit('FB etkinlik listesi okunamadı: ' + j['error'].get('message', ''))
        hepsi += j.get('data', [])
        url, prm = j.get('paging', {}).get('next'), None
    sonuc = imzali('POST', SITE + '/api/sosyal/etkinlik-esle', json.dumps({'etkinlikler': hepsi}, ensure_ascii=False).encode('utf-8'),
                   basliklar={'Content-Type': 'application/json'})
    print(f"sayfada {len(hepsi)} yaklaşan etkinlik · eşleşen {sonuc['eslesen']} · defterden düşen {sonuc['dusen']}")


def kapak_html(p, kare, logo, hareketli=False):
    t = open(os.path.join(KOK, 'EtkinlikKapak.dc.html'), encoding='utf-8').read()
    govde = t[t.index('<x-dc>') + 6:t.index('</x-dc>')]
    import re, datetime
    stil = re.search(r'<helmet>(.*?)</helmet>', govde, re.S).group(1)
    govde = re.sub(r'<helmet>.*?</helmet>', '', govde, flags=re.S)
    d = datetime.date.fromisoformat(p['tarih'])
    props = {'meslek': p['meslek_ad'], 'seviye': p['seviye'], 'il': p['sehir'], 'gun': f'{d.day:02d}', 'ay': AY[d.month - 1], 'gunAdi': p['gun_adi'],
             'saat': p['saat'], 'toplam': p['toplam_tl'] or '', 'ucretNot': 'sınav + belge basım · KDV dahil' + (' · başlangıç fiyatı' if p['baslangic'] else ''), 'kare': Path(kare).resolve().as_uri(), 'logoAdres': Path(logo).resolve().as_uri(), 'logo': p['meslek_ad'] not in R.INSAAT, 'hareketli': hareketli}
    kod = re.search(r'<script type="text/x-dc" data-dc-script[^>]*>(.*?)</script>', t, re.S).group(1)
    calis = ('<script>class DCLogic{constructor(p){this.props=p}}\n' + kod + '\nconst v=new Component(' + json.dumps(props, ensure_ascii=False)
             + ').renderVals();\n' + JS_SABLON + '</script>')
    return (f'<!doctype html><html lang="tr"><head><meta charset="utf-8">{stil}<style>html,body{{margin:0}}</style></head>'
            f'<body><template id="sablon">{govde}</template>{calis}</body></html>')


def kapak(sadece_gerek=False):
    eksik = [p for p in plan() if not p['kapak_var']]
    if sadece_gerek:
        out = os.environ.get('GITHUB_OUTPUT')
        if out:
            open(out, 'a').write(f"kapak={1 if eksik else 0}\n")
        print(f'kapak gereken {len(eksik)}'); return
    if not eksik:
        print('kapak gereken yok'); return
    from playwright.sync_api import sync_playwright
    import imageio_ffmpeg
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    gec = tempfile.mkdtemp(prefix='etk_')
    with sync_playwright() as pw:
        b = pw.chromium.launch(); sayfa = b.new_page(viewport={'width': 1920, 'height': 1005})
        for p in eksik:
            kaynak = R.kaynak_video(p['meslek_ad'], p['seviye'])
            kare = os.path.join(gec, 'kare.jpg')   # kaynak klibin ilk karesi, dikey 1080×1920
            subprocess.run([ff, '-loglevel', 'error', '-y', '-i', kaynak, '-vf', 'scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920',
                            '-frames:v', '1', '-q:v', '2', kare], check=True)
            logo = os.path.join(KOK, 'logo-beyaz.png')
            jpg, katman, mp4 = (os.path.join(gec, a) for a in ('kapak.jpg', 'katman.png', 'kapak.mp4'))
            for hareketli, cikti in ((False, jpg), (True, katman)):
                yol = os.path.join(gec, 'k.html'); open(yol, 'w', encoding='utf-8').write(kapak_html(p, kare, logo, hareketli))
                sayfa.goto(Path(yol).as_uri()); sayfa.wait_for_load_state('load'); sayfa.evaluate('document.fonts.ready.then(() => document.fonts.size)')
                if hareketli:
                    sayfa.screenshot(path=cikti, omit_background=True)   # zemin + fotoğraf yeri saydam katman
                else:
                    sayfa.screenshot(path=cikti, type='jpeg', quality=90)
            # HAREKETLİ KAPAK (08.11.2026, kullanıcı "8 saniyelik hareketli video · sessiz"; Facebook etkinliğinde yüklenen fotoğraf kapağı kaydedilmiyor,
            # video kaydediliyor — ölçüldü): yazılar sabit; fotoğraf yerinde (x 1070, 380×1005, object-position 50% 25%) mesleğin klibi, kenarlarda aynı
            # klip bulanık + koyu (durağan kapağın zemini gibi). İlk kare = durağan kapak (Facebook oynatmazsa da bilgi okunur). Ses kanalı YOK.
            fc = ('[0:v]fps=30,split=2[a][b];'
                  '[a]scale=2000:-2,crop=2000:1085,gblur=sigma=28,eq=brightness=-0.25,crop=1920:1005,drawbox=x=0:y=0:w=iw:h=ih:color=0x14213D@0.55:t=fill[zem];'
                  '[b]scale=-2:1005,crop=380:1005:(iw-380)/2:0[foto];'
                  '[zem][foto]overlay=1070:0[z2];[z2][1:v]overlay=0:0,crop=1920:1004:0:0,format=yuv420p[v]')
            subprocess.run([ff, '-loglevel', 'error', '-y', '-i', kaynak, '-i', katman, '-filter_complex', fc, '-map', '[v]', '-an', '-t', '8',
                            '-c:v', 'libx264', '-crf', '20', '-preset', 'medium', '-movflags', '+faststart', mp4], check=True)
            # önce video (yalnız dosya), sonra görsel (dosya + imza kaydı) → imza ancak ikisi de yüklenince yazılır
            imzali('PUT', f"{SITE}/api/sosyal/etkinlik-kapak/{p['uuid']}", open(mp4, 'rb').read(), params={'imza': p['kapak_imza']},
                   basliklar={'Content-Type': 'video/mp4'})
            imzali('PUT', f"{SITE}/api/sosyal/etkinlik-kapak/{p['uuid']}", open(jpg, 'rb').read(), params={'imza': p['kapak_imza']},
                   basliklar={'Content-Type': 'image/jpeg'})
            print('kapak yüklendi', p['ad'], p['tarih_str'], p['saat'])
        b.close()


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--esle', action='store_true'); ap.add_argument('--kapak', action='store_true'); ap.add_argument('--gerek', action='store_true')
    a = ap.parse_args()
    if a.esle:
        esle()
    if a.gerek:
        kapak(sadece_gerek=True)
    if a.kapak:
        kapak()
