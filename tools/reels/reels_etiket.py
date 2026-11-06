# -*- coding: utf-8 -*-
"""ZİYARET KAYNAĞI ETİKETİ — YouTube + Facebook video açıklamalarındaki etiketsiz adenbelge bağlantıları (06.11.2026; docs/ziyaret-kaynagi-plani.md Faz 4).

Kullanıcı: "BİZ Mİ TETİKLEYECEĞİZ · GITHUB ACTIONS YAPAMIYOR MUSUN" → aden-reels iş akışı her gün yayından SONRA koşar ('etiket' işi).
İdempotent: yalnız utm_source TAŞIMAYAN adenbelge bağlantısına etiket eklenir, metnin geri kalanı değişmez; her yazım geri okunur.
Sonunda yeniden tarar ve KALAN etiketsiz sayısını yazar (0 = bitti). Kota/sınır (YouTube 403 quota, Meta #4) → durur, ertesi koşu tamamlar.
  YouTube: utm_source=youtube&utm_medium=shorts|video&utm_content=<video kimliği>   (Shorts = süre ≤ 3 dk)
  Facebook: utm_source=facebook&utm_medium=reels&utm_content=fb<kimliğin son 12 hanesi>
Anahtarlar: reels_yayin.env (GitHub gizli değeri ya da yerel .env) — META_SOSYAL_TOKEN, YT_TOKEN_JSON.
Kullanım: python tools/reels/reels_etiket.py            # kuru koşum (sayım)
          python tools/reels/reels_etiket.py --uygula   # yazar + geri okur + yeniden tarar
"""
import os
import re
import sys
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import requests

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import reels_yayin as RY  # noqa: E402

G = 'https://graph.facebook.com/v23.0'
RE = re.compile(r'https?://(?:www\.)?adenbelge\.com\.tr[^\s]*')
UYGULA = '--uygula' in sys.argv


def etiketle(url, kaynak, ortam, icerik):
    sonek = ''
    while url and url[-1] in '.,;:!?)]»"\'':
        sonek = url[-1] + sonek; url = url[:-1]
    if 'utm_source=' in url:
        return url + sonek
    p = urlsplit(url)
    q = parse_qsl(p.query, keep_blank_values=True) + [('utm_source', kaynak), ('utm_medium', ortam), ('utm_content', icerik)]
    return urlunsplit((p.scheme, p.netloc, p.path or '/tr', urlencode(q), p.fragment)) + sonek


def etiketsiz(metin):
    return [u for u in RE.findall(metin or '') if 'utm_source=' not in u]


# ── YouTube ──
def yt_videolar(ys):
    up = ys.channels().list(part='contentDetails', mine=True).execute()['items'][0]['contentDetails']['relatedPlaylists']['uploads']
    ids, tok = [], None
    while True:
        r = ys.playlistItems().list(part='contentDetails', playlistId=up, maxResults=50, pageToken=tok).execute()
        ids += [i['contentDetails']['videoId'] for i in r['items']]; tok = r.get('nextPageToken')
        if not tok:
            break
    out = []
    for i in range(0, len(ids), 50):
        out += ys.videos().list(part='snippet,contentDetails', id=','.join(ids[i:i + 50])).execute()['items']
    return out


def youtube():
    ys = RY.yt_servis()
    vids = yt_videolar(ys)
    hedef = [v for v in vids if etiketsiz(v['snippet']['description'])]
    yazilan, durdu = 0, ''
    if UYGULA:
        for v in hedef:
            sn, vid = v['snippet'], v['id']
            ortam = 'shorts' if re.fullmatch(r'PT(\d+S|[0-2]M(\d+S)?|3M)', v['contentDetails']['duration']) else 'video'
            yeni = RE.sub(lambda m: etiketle(m.group(0), 'youtube', ortam, vid.lower().replace('_', '-')), sn['description'])
            govde = {'id': vid, 'snippet': {'title': sn['title'], 'description': yeni, 'categoryId': sn['categoryId'],
                                           **({'tags': sn['tags']} if sn.get('tags') else {}),
                                           **({'defaultLanguage': sn['defaultLanguage']} if sn.get('defaultLanguage') else {})}}
            try:
                ys.videos().update(part='snippet', body=govde).execute()
                yazilan += 1
            except Exception as x:  # noqa: BLE001
                durdu = 'kota doldu' if 'quota' in str(x).lower() else str(x)[:120]
                break
        vids = yt_videolar(ys) if yazilan else vids   # geri okuma = yeniden tarama
    kalan = sum(1 for v in vids if etiketsiz(v['snippet']['description']))
    print(f"YouTube: video {len(vids)} · etiketsiz {len(hedef)} · {'yazıldı ' + str(yazilan) if UYGULA else 'KURU'} · KALAN {kalan}" + (f' · durdu: {durdu}' if durdu else ''))
    return kalan


# ── Facebook ──
def fb_videolar(pid, pt):
    out, url, par = [], f'{G}/{pid}/videos', {'fields': 'id,description', 'limit': 100, 'access_token': pt}
    while url:
        r = requests.get(url, params=par, timeout=60).json()
        if 'error' in r:
            raise RuntimeError(r['error'].get('message', 'hata'))
        out += r.get('data', []); url = r.get('paging', {}).get('next'); par = None
    return out


def facebook():
    r = requests.get(f'{G}/me/accounts', params={'fields': 'id,access_token', 'access_token': RY.env('META_SOSYAL_TOKEN')}, timeout=30).json()
    if 'error' in r:
        print(f"Facebook: okunamadı ({r['error'].get('message')}) · ertesi koşu dener")
        return None
    pid, pt = r['data'][0]['id'], r['data'][0]['access_token']
    vids = fb_videolar(pid, pt)
    hedef = [v for v in vids if etiketsiz(v.get('description'))]
    yazilan, durdu = 0, ''
    if UYGULA:
        for v in hedef:
            yeni = RE.sub(lambda m: etiketle(m.group(0), 'facebook', 'reels', 'fb' + v['id'][-12:]), v['description'])
            s = requests.post(f"{G}/{v['id']}", data={'description': yeni, 'access_token': pt}, timeout=60).json()
            if not s.get('success'):
                durdu = s.get('error', {}).get('message', str(s))[:120]
                break
            geri = requests.get(f"{G}/{v['id']}", params={'fields': 'description', 'access_token': pt}, timeout=30).json().get('description')
            if geri != yeni:
                durdu = f"geri okuma farklı {v['id']}"
                break
            yazilan += 1
        try:
            vids = fb_videolar(pid, pt) if yazilan else vids
        except RuntimeError as x:
            durdu = durdu or f'yeniden tarama: {x}'
    kalan = sum(1 for v in vids if etiketsiz(v.get('description')))
    print(f"Facebook: video {len(vids)} · etiketsiz {len(hedef)} · {'yazıldı ve geri okundu ' + str(yazilan) if UYGULA else 'KURU'} · KALAN {kalan}" + (f' · durdu: {durdu}' if durdu else ''))
    return kalan


if __name__ == '__main__':
    for ad, f in (('YouTube', youtube), ('Facebook', facebook)):
        try:
            f()
        except Exception as x:  # noqa: BLE001
            print(f'{ad}: hata — {str(x)[:160]} · ertesi koşu dener')
