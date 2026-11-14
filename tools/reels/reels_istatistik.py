# -*- coding: utf-8 -*-
"""REELS GÜNLÜK TOPLAM İSTATİSTİK (05.11.2026, kullanıcı: günlük satırlar her gün kendiliğinden dolsun).

Yayın defterindeki Reels/Shorts için toplamları ölçer ve sunucuya yazar (tek kaynak PROD global_veri_seti 'reels_istatistik',
imzalı uç /api/sosyal/reels-istatistik). Günlük artış = ardışık iki günün toplam farkı (tools/istatistik_durum.py hesaplar).
  FB  video nesnesinin 'views' alanı (izinsiz okunur)
  IG  like_count + /insights views, reach (instagram_manage_insights izni açık — 06.11.2026 ölçüldü)
  YT  videos.list statistics (viewCount, likeCount)
GitHub Actions (adenbelge/aden-reels) her yayın koşusundan sonra çalıştırır; yerelde de koşulabilir.
Kullanım: python tools/reels/reels_istatistik.py [--kuru]
"""
import argparse
import datetime as dt
import hashlib
import hmac
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import reels_yayin as R  # noqa: E402

URL = 'https://adenbelge.com.tr/api/sosyal/reels-istatistik'


def istek(yontem, govde=b''):
    ts = str(int(time.time()))
    imza = hmac.new(R.env('REELS_ANAHTAR').encode(), '\n'.join([yontem, ts, hashlib.sha256(govde).hexdigest()]).encode(), hashlib.sha256).hexdigest()
    r = requests.request(yontem, URL, data=govde or None, timeout=60,
                         headers={'X-Reels-Zaman': ts, 'X-Reels-Imza': imza, 'Content-Type': 'application/json'})
    r.raise_for_status()
    return r.json()['istatistik']


def ig_ozet(i, tok):
    """IG gönderisinin (izlenme, erişim) değeri — /insights; hata yutulmaz."""
    j = requests.get(f'{R.GRAPH}/{i}/insights', params={'metric': 'views,reach', 'access_token': tok}, timeout=30).json()
    if 'error' in j:
        raise RuntimeError(f"IG insights {i}: {j['error'].get('message')}")
    v = {e['name']: e['values'][0]['value'] for e in j['data']}
    return v.get('views', 0), v.get('reach', 0)


def topla():
    tok = R.env('META_SOSYAL_TOKEN')
    ptok = R.sayfa_jetonu(tok)
    d = R.defter_oku()
    fb = [v['fb']['id'] for v in d.values() if 'fb' in v]
    # IG: hesabın GERÇEK gönderi listesi (06.11.2026 — silinen gönderiler defterde durur, sorgulanınca hata verirdi)
    ig, url, p = [], f'{R.GRAPH}/{R.IG_HESAP}/media', {'fields': 'id', 'limit': 100, 'access_token': tok}
    while url:
        j = requests.get(url, params=p, timeout=60).json()
        if 'error' in j:
            raise RuntimeError(f"IG gönderi listesi: {j['error'].get('message')}")
        ig += [x['id'] for x in j.get('data', [])]
        url, p = j.get('paging', {}).get('next'), None
    yt = [v['yt']['id'] for v in d.values() if 'yt' in v]
    al = lambda i, alan, jt: int(requests.get(f'{R.GRAPH}/{i}', params={'fields': alan, 'access_token': jt}, timeout=30).json().get(alan, 0))
    with ThreadPoolExecutor(8) as ex:
        fbv = sum(ex.map(lambda i: al(i, 'views', ptok), fb))
        igb = sum(ex.map(lambda i: al(i, 'like_count', tok), ig))
        igi = list(ex.map(lambda i: ig_ozet(i, tok), ig))
    ys = R.yt_servis()
    ytv = ytb = 0
    for k in range(0, len(yt), 50):
        for it in ys.videos().list(part='statistics', id=','.join(yt[k:k + 50])).execute().get('items', []):
            ytv += int(it['statistics'].get('viewCount', 0))
            ytb += int(it['statistics'].get('likeCount', 0))
    return {'fb_adet': len(fb), 'fb_izlenme': fbv, 'ig_adet': len(ig), 'ig_begeni': igb, 'ig_izlenme': sum(x[0] for x in igi),
            'ig_erisim': sum(x[1] for x in igi), 'yt_adet': len(yt), 'yt_izlenme': ytv, 'yt_begeni': ytb}


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    ap = argparse.ArgumentParser()
    ap.add_argument('--kuru', action='store_true')
    a = ap.parse_args()
    deger = topla()
    tarih = dt.datetime.now(dt.timezone(dt.timedelta(hours=3))).date().isoformat()  # TSİ günü
    print(tarih, deger)
    if a.kuru:
        return
    hepsi = istek('PATCH', json.dumps({'tarih': tarih, 'deger': deger, 'kaynak': 'reels_istatistik.py'}, ensure_ascii=False).encode())
    print('yazıldı; kayıtlı gün sayısı', len(hepsi))


if __name__ == '__main__':
    main()
