"""SAYFA HİKÂYELERİ — Facebook + Instagram (08.11.2026, kullanıcı "DENE" → FB deneme yayında; "ilk hafta günde 8"; "Instagram hikâyesi").
Reels planındaki satırın o platformun Reels videosu (aynı tasarım, aynı üretici, platform rengi/güvenli alanı) hikâye olarak yayınlanır:
  FB  /{sayfa}/video_stories (start → rupload → finish, sayfa jetonu)
  IG  /{ig}/media media_type=STORIES upload_type=resumable → rupload → hazır olunca media_publish (kullanıcı jetonu; Reels ile aynı yol)
Hikâye 24 saatte kendiliğinden kalkar → silme/defter yok. Günde bir koşum (11:30, reels.yml 'hikaye' işi).
SEÇİM: plan sırası (il önceliği, sonra tarih) üzerinde güne göre dönen pencere — her gün sıradaki N satır; durumsuz, iki platform AYNI satırlar.
Platform sınırı (Meta #4/#17/#32/#613, IG 2207042) o platform için normal duraktır; tek videodaki hata atlanır, üst üste 3 hata o platformu durdurur."""
import argparse
import datetime
import json
import os
import subprocess
import sys
import tempfile

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import reels_yayin as R   # noqa: E402


def sec(satirlar, adet, gun):
    if not satirlar:
        return []
    bas = (gun * adet) % len(satirlar)
    return [satirlar[(bas + i) % len(satirlar)] for i in range(min(adet, len(satirlar)))]


def fb_hikaye(pt, dosya):
    s = requests.post(f'{R.GRAPH}/{R.FB_SAYFA}/video_stories', data={'upload_phase': 'start', 'access_token': pt}, timeout=60).json()
    if 'video_id' not in s:
        raise RuntimeError(f'FB hikâye başlat: {s}')
    u = requests.post(s['upload_url'], data=open(dosya, 'rb').read(), timeout=600,
                      headers={'Authorization': 'OAuth ' + pt, 'offset': '0', 'file_size': str(os.path.getsize(dosya))}).json()
    if not u.get('success'):
        raise RuntimeError(f'FB hikâye yükleme: {u}')
    f = requests.post(f'{R.GRAPH}/{R.FB_SAYFA}/video_stories', data={'upload_phase': 'finish', 'video_id': s['video_id'], 'access_token': pt}, timeout=120).json()
    if not f.get('success'):
        raise RuntimeError(f'FB hikâye bitir: {f}')
    return f.get('post_id')


def ig_hikaye(tok, dosya):
    k = requests.post(f'{R.GRAPH}/{R.IG_HESAP}/media', data={'media_type': 'STORIES', 'upload_type': 'resumable', 'access_token': tok}, timeout=60).json()
    if 'id' not in k:
        raise RuntimeError(f'IG hikâye konteyner: {k}')
    u = requests.post(k['uri'], headers={'Authorization': f'OAuth {tok}', 'offset': '0', 'file_size': str(os.path.getsize(dosya))},
                      data=open(dosya, 'rb'), timeout=600).json()
    if not u.get('success'):
        raise RuntimeError(f'IG hikâye yükleme: {u}')
    R.bekle_ig(k['id'], tok)
    y = requests.post(f'{R.GRAPH}/{R.IG_HESAP}/media_publish', data={'creation_id': k['id'], 'access_token': tok}, timeout=120).json()
    if 'id' not in y:
        raise RuntimeError(f'IG hikâye yayın: {y}')
    return y['id']


def video(r, p):
    gec = tempfile.mkdtemp(prefix='hikaye_')
    v = dict(r['video']); v['kaynak_video'] = R.kaynak_video(v['meslek'], v['seviye']); v['logo'] = v['meslek'] not in R.INSAAT
    vj, dosya = os.path.join(gec, f'{p}.json'), os.path.join(gec, f'{p}.mp4')
    json.dump(dict(v, platform=p, renk=int(v['renk'][p])), open(vj, 'w', encoding='utf-8'), ensure_ascii=False)
    subprocess.run([sys.executable, os.path.join(R.KOK, 'tools', 'reels', 'reels_video.py'), vj, dosya], check=True)
    return dosya


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--adet', type=int, default=8)
    ap.add_argument('--platform', choices=['fb', 'ig', 'hepsi'], default='hepsi')
    ap.add_argument('--atla', type=int, default=0, help='günün listesinden baştaki N satırı atla (elle tamamlama)')
    ap.add_argument('--uygula', action='store_true')
    a = ap.parse_args()
    veri = R.imzali_get(R.PLAN_URL)
    secilen = sec(veri['satirlar'], a.adet, datetime.date.today().toordinal())[a.atla:]
    for r in secilen:
        print('seçildi', R.anahtar(r), r['ilk_satir'])
    if not a.uygula:
        print('kuru koşum (--uygula yok)'); return
    tok = R.env('META_SOSYAL_TOKEN')
    platformlar = ['fb', 'ig'] if a.platform == 'hepsi' else [a.platform]
    yayinla = {'fb': (lambda d, pt=R.sayfa_jetonu(tok) if 'fb' in platformlar else None: fb_hikaye(pt, d)), 'ig': lambda d: ig_hikaye(tok, d)}
    durdu, yapilan, hata, art_arda = set(), {p: 0 for p in platformlar}, {p: 0 for p in platformlar}, {p: 0 for p in platformlar}
    for r in secilen:
        for p in platformlar:
            if p in durdu:
                continue
            try:
                kimlik = yayinla[p](video(r, p))
            except Exception as x:
                if R.sinir_mi(x):
                    print(f'{p.upper()} HİKÂYE PLATFORM SINIRI ({str(x)[:160]}) — kalan iş yarın'); durdu.add(p); continue
                hata[p] += 1; art_arda[p] += 1
                print(f'::warning::{p.upper()} HİKÂYE YAYINLANAMADI, atlandı {R.anahtar(r)} — {str(x)[:300]}')
                if art_arda[p] >= 3:
                    print(f'::error::{p.upper()} hikâye: üst üste 3 hata — bu platform durdu'); durdu.add(p)
                continue
            art_arda[p] = 0; yapilan[p] += 1
            print(f'  {p.upper()} HİKÂYE {kimlik} YAYINLANDI {R.anahtar(r)} {r["ilk_satir"]}')
    for p in platformlar:
        print(f'{p.upper()} HİKÂYE özet: yayınlanan {yapilan[p]} · atlanan (hata) {hata[p]}')
    if any(art_arda[p] >= 3 for p in platformlar):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
