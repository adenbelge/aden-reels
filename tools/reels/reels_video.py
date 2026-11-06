# -*- coding: utf-8 -*-
"""Sınav oturumu Reels videosu: onaylı katman tasarımı (Claude Design tuvali AH5i3Gko6aVtUehDmsfPqZ, Katman.dc.html) şeffaf kareler
olarak işlenir (Playwright, Web Animations zamanı elle ilerletilir) ve mesleğin kaynak videosunun üstüne bindirilir (imageio-ffmpeg).
    python tools/reels/reels_video.py veri.json cikti.mp4
veri.json: {meslek, seviye, il, tarih (YYYY-AA-GG), gun_adi, saat, merkez, adres, ucret, ucret_not, basim, kaynak_video}
Sunucuda ffmpeg yok → yerel / GitHub Actions'ta koşar."""
import sys, os, json, re, datetime, subprocess, tempfile, shutil, html
from pathlib import Path
from playwright.sync_api import sync_playwright
import imageio_ffmpeg
sys.stdout.reconfigure(encoding='utf-8')
KOK = os.path.dirname(os.path.abspath(__file__))
AY = ['Ocak', 'Şubat', 'Mart', 'Nisan', 'Mayıs', 'Haziran', 'Temmuz', 'Ağustos', 'Eylül', 'Ekim', 'Kasım', 'Aralık']
FPS, SURE = 24, 8.0


def sayi(s):
    return int(str(s).replace('.', ''))


def katman_html(v):
    t = open(os.path.join(KOK, 'Katman.dc.html'), encoding='utf-8').read()
    govde = t[t.index('<x-dc>') + 6:t.index('</x-dc>')]
    govde = re.sub(r'<sc-if value="\{\{onizleme\}\}".*?</sc-if>', '', govde, flags=re.S)
    stil = re.search(r'<helmet>(.*?)</helmet>', govde, re.S).group(1)
    govde = re.sub(r'<helmet>.*?</helmet>', '', govde, flags=re.S)
    d = datetime.date.fromisoformat(v['tarih'])
    # bileşenin özellikleri (değerleri ve 16 renk paletini bileşenin KENDİ renderVals() kodu hesaplar — kural tek yerde)
    props = {'tasarim': int(v['renk']), 'meslek': v['meslek'], 'seviye': v['seviye'],
             'il': v['il'], 'gun': f'{d.day:02d}', 'ay': AY[d.month - 1], 'yil': str(d.year), 'gunAdi': v['gun_adi'], 'saat': v['saat'],
             'merkez': v['merkez'], 'adres': v['adres'], 'ucret': v['ucret'], 'ucretNot': v.get('ucret_not', 'KDV dahil'),
             'basim': v.get('basim', '1.500'), 'onizleme': False, 'hareket': True, 'logo': bool(v.get('logo', True)), 'platform': v.get('platform', 'ig'), 'renk': int(v['renk'])}
    kod = re.search(r'<script type="text/x-dc" data-dc-script[^>]*>(.*?)</script>', t, re.S).group(1)
    govde = govde.replace('/_blob/a9b17b44cea2936eb29ae63c9c2d9d93', Path(KOK, 'logo-beyaz.png').as_uri())
    calis = ('<script>class DCLogic{constructor(p){this.props=p}}\n' + kod +
             '\nconst v=new Component(' + json.dumps(props, ensure_ascii=False) + ').renderVals();'
             "const al=y=>y.split('.').reduce((o,k)=>o==null?o:o[k],v);"
             "const es=s=>String(s).replace(/[&<>\"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;'}[c]));"
             "document.body.innerHTML=document.getElementById('sablon').innerHTML.replace(/\\{\\{\\s*([\\w.]+)\\s*\\}\\}/g,(m,y)=>es(al(y)));</script>")
    return (f'<!doctype html><html lang="tr"><head><meta charset="utf-8">{stil}<style>html,body{{margin:0;background:transparent}}</style></head>'
            f'<body><template id="sablon">{govde}</template>{calis}</body></html>')


def main():
    v = json.load(open(sys.argv[1], encoding='utf-8')); cikti = sys.argv[2]
    gec = tempfile.mkdtemp(prefix='reels_')
    yol = os.path.join(gec, 'k.html'); open(yol, 'w', encoding='utf-8').write(katman_html(v))
    with sync_playwright() as p:
        # katman 1080×1920 tasarım ölçüsünde çizilir, 4/3 ölçekle 1440×2560 piksele basılır: YouTube 1440p ve üstüne daha kaliteli sıkıştırma (VP9) verir
        b = p.chromium.launch(); pg = b.new_page(viewport={'width': 1080, 'height': 1920}, device_scale_factor=4 / 3)
        pg.goto(Path(yol).as_uri()); pg.wait_for_load_state('load'); pg.evaluate('document.fonts.ready.then(() => document.fonts.size)')
        pg.evaluate("document.getAnimations().forEach(a => a.pause())")
        for i in range(int(FPS * SURE)):
            pg.evaluate(f"document.getAnimations().forEach(a => a.currentTime = {i * 1000 / FPS})")
            pg.screenshot(path=os.path.join(gec, f'k{i:04d}.png'), omit_background=True)
        b.close()
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    bilgi = subprocess.run([ff, '-i', v['kaynak_video']], capture_output=True, text=True, encoding='utf-8', errors='replace').stderr
    sesli = 'Audio:' in bilgi
    komut = [ff, '-loglevel', 'error', '-y', '-i', v['kaynak_video'], '-framerate', str(FPS), '-i', os.path.join(gec, 'k%04d.png'),
             '-f', 'lavfi', '-i', 'anullsrc=r=44100:cl=stereo',
             '-filter_complex', '[0:v]scale=1440:2560:force_original_aspect_ratio=increase:flags=lanczos,crop=1440:2560,fps=24[a];[a][1:v]overlay=0:0:format=auto[v]',
             # kaynak videonun KENDİ sesi; kaynakta ses yoksa sessiz kanal
             '-map', '[v]', '-map', '0:a' if sesli else '2:a', '-t', str(SURE), '-c:v', 'libx264', '-preset', 'slow', '-pix_fmt', 'yuv420p', '-profile:v', 'high', '-crf', '16', '-maxrate', '20M', '-bufsize', '40M',
             # YouTube/Meta 1080p için yüksek bit hızı: platform yeniden sıkıştırınca ayrıntı kaybolmasın (crf 20 ≈ 2,4 Mbps idi)
             '-c:a', 'aac', '-b:a', '128k', '-movflags', '+faststart', cikti]
    subprocess.run(komut, check=True)
    shutil.rmtree(gec, ignore_errors=True)
    print('tamam', cikti, os.path.getsize(cikti))


if __name__ == '__main__':
    main()
