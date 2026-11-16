# -*- coding: utf-8 -*-
"""KANAL İSTATİSTİK — SAATLİK TOPLAYICI (06.11.2026, kullanıcı "ELMA İLE ELMA, ARMUT İLE ARMUT").

Günde iki kez, Reels yayınından HEMEN ÖNCE çalışır (GitHub Actions adenbelge/aden-reels, reels.yml 'kanal' işi; 11.11.2026 kullanıcı
"HER SAAT GEREK VAR MI · GÜNDE 2 KEZ"). Kayıt GERÇEK ÖLÇÜM SAATİNE yazılır (15.11.2026, kullanıcı onayı): GitHub zamanlayıcısı sabah koşusunu
7 saate kadar geç başlatıyordu → eski "sabit dilim" (--dilim 11|18) akşam ölçümünü "11:00" diye yazıyor, gece yarısını geçen akşam koşusunu
"dilim henüz gelmedi" diye düşürüyordu. Panel dönem uçlarını gerçek ölçüm saatlerinden seçer (KanalIstatistik). Eski saatlik iş (kanal.yml) yalnız elle; sonuçları imzalı uçla PROD kur_kanal_saatlik tablosuna yazar
(POST /api/sosyal/kanal-saatlik; imza ReelsDefteri ile aynı, REELS_ANAHTAR). Panel /yonetim/kanal-istatistik okur.
  Google    Search Console saatlik (dimensions HOUR, dataState HOURLY_ALL) — YALNIZ tamamlanmış saatler (metadata.firstIncompleteHour öncesi);
            Pasifik saati → Türkiye saati; tamamlanmış ama satırı olmayan saat = 0 (Search Console boş saati döndürmez). Son 10 gün yeniden yazılır.
  Facebook  sayfanın TÜM videolarının 'views' toplamı (anlık, birikimli)
  Instagram hesabın TÜM gönderilerinin /insights 'views' toplamı (anlık, birikimli)
  YouTube   kanalın TÜM videolarının viewCount toplamı (anlık, birikimli)
Birikimli kayıtların dönem değeri = iki uçtaki ölçümün farkı (panel hesaplar). Hata yutulmaz: bir kanal okunamazsa o kanal yazılmaz, iş hata verir.
Kullanım: python tools/reels/kanal_saatlik.py [--kuru]
Anahtarlar: META_SOSYAL_TOKEN, REELS_ANAHTAR, YT_TOKEN_JSON, GSC_SA_JSON (ya da yerel tools/.gsc_anahtar.json) — ekrana basılmaz.
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
from zoneinfo import ZoneInfo

import requests

KOK = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import reels_yayin as R  # noqa: E402

URL = R.API_KOK + '/api/sosyal/kanal-saatlik'
TR = ZoneInfo('Europe/Istanbul')
GSC_SITE = 'sc-domain%3Aadenbelge.com.tr'


def saat_tr(t):
    return t.astimezone(TR).strftime('%Y-%m-%d %H:00:00')


def gsc_jeton():
    from google.oauth2 import service_account
    from google.auth.transport.requests import Request
    kapsam = ['https://www.googleapis.com/auth/webmasters.readonly']
    js = os.environ.get('GSC_SA_JSON')
    k = (service_account.Credentials.from_service_account_info(json.loads(js), scopes=kapsam) if js else
         service_account.Credentials.from_service_account_file(os.path.join(KOK, 'tools', '.gsc_anahtar.json'), scopes=kapsam))
    k.refresh(Request())
    return k.token


def google():
    t = gsc_jeton()
    bugun = dt.datetime.now(ZoneInfo('America/Los_Angeles')).date()
    j = requests.post(f'https://www.googleapis.com/webmasters/v3/sites/{GSC_SITE}/searchAnalytics/query', timeout=120,
                      headers={'Authorization': f'Bearer {t}'},
                      json={'startDate': str(bugun - dt.timedelta(days=10)), 'endDate': str(bugun), 'dimensions': ['HOUR'],
                            'dataState': 'HOURLY_ALL', 'rowLimit': 5000}).json()
    if 'rows' not in j or 'firstIncompleteHour' not in j.get('metadata', {}):
        raise RuntimeError(f'Search Console saatlik yanıtı beklenen biçimde değil: {str(j)[:300]}')
    eksik = dt.datetime.fromisoformat(j['metadata']['firstIncompleteHour'])
    satir = {dt.datetime.fromisoformat(x['keys'][0]): x for x in j['rows']}
    bas = min(satir)
    k = []
    s = bas
    while s < eksik:
        x = satir.get(s, {'impressions': 0, 'clicks': 0})
        for m, a in (('gosterim', 'impressions'), ('tik', 'clicks')):
            k.append({'saat': saat_tr(s), 'kanal': 'google', 'metrik': m, 'tip': 'aralik', 'deger': int(x[a])})
        s = (s.astimezone(dt.timezone.utc) + dt.timedelta(hours=1)).astimezone(s.tzinfo)
    return k


def sayfala(url, p):
    """Graph sayfalama 'after' imleciyle ve kendi limitimizle (paging.next adresi limiti sabit taşır).
    11.11.2026: Meta "Please reduce the amount of data you're asking for" (kod 1) yanıtında Meta'nın önerdiği yol
    uygulanır: aynı imleçten limit yarıya inerek yeniden istenir (en az 5); başka hata olduğu gibi yükselir."""
    out, p, limit = [], dict(p), int(p.get('limit', 100))
    while True:
        p['limit'] = limit
        j = requests.get(url, params=p, timeout=60).json()
        if 'error' in j:
            msg = j['error'].get('message', '')
            if 'reduce the amount of data' in msg and limit > 5:
                limit = max(5, limit // 2)
                continue
            raise RuntimeError(f'Graph: {msg}')
        out += j.get('data', [])
        sonraki = j.get('paging', {}).get('cursors', {}).get('after')
        if not j.get('paging', {}).get('next') or not sonraki:
            return out
        p['after'] = sonraki


def birikimli(saat, kanal, gonderiler):
    """11.11.2026: toplamın yanında gönderi başına değer — panel dönem artışını gönderi gönderi hesaplar (iki uçta duran gönderinin artışı +
    dönem içinde yayınlananın değeri); silinen gönderi toplamı düşürmez."""
    return {'saat': saat, 'kanal': kanal, 'metrik': 'izlenme', 'tip': 'birikimli', 'deger': sum(gonderiler.values()), 'adet': len(gonderiler),
            'gonderiler': {str(k): int(v) for k, v in gonderiler.items()}}


def facebook(tok, saat):
    ptok = R.sayfa_jetonu(tok)
    v = sayfala(f'{R.GRAPH}/{R.FB_SAYFA}/videos', {'fields': 'id,views', 'limit': 100, 'access_token': ptok})
    return [birikimli(saat, 'facebook', {x['id']: int(x.get('views', 0)) for x in v})]


def instagram(tok, saat):
    m = sayfala(f'{R.GRAPH}/{R.IG_HESAP}/media', {'fields': 'id', 'limit': 100, 'access_token': tok})

    def izl(i):
        j = requests.get(f'{R.GRAPH}/{i}/insights', params={'metric': 'views', 'access_token': tok}, timeout=60).json()
        if 'error' in j:
            raise RuntimeError(f"IG insights {i}: {j['error'].get('message')}")
        return int(j['data'][0]['values'][0]['value'])
    idler = [x['id'] for x in m]
    with ThreadPoolExecutor(8) as ex:
        return [birikimli(saat, 'instagram', dict(zip(idler, ex.map(izl, idler))))]


def youtube(saat):
    ys = R.yt_servis()
    yukleme = ys.channels().list(part='contentDetails', mine=True).execute()['items'][0]['contentDetails']['relatedPlaylists']['uploads']
    ids, sayfa = [], None
    while True:
        j = ys.playlistItems().list(part='contentDetails', playlistId=yukleme, maxResults=50, pageToken=sayfa).execute()
        ids += [x['contentDetails']['videoId'] for x in j['items']]
        sayfa = j.get('nextPageToken')
        if not sayfa:
            break
    g = {}
    for k in range(0, len(ids), 50):
        for it in ys.videos().list(part='statistics', id=','.join(ids[k:k + 50])).execute().get('items', []):
            g[it['id']] = int(it['statistics'].get('viewCount', 0))
    return [birikimli(saat, 'youtube', g)]


def gonder(kayitlar):
    govde = json.dumps({'kayitlar': kayitlar}, ensure_ascii=False).encode()
    return R.site_istek('POST', URL, govde)['yazildi']   # 10.11'deki JSON olmayan yanıt dahil ayrıntı + tek yeniden deneme: R.site_istek


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    ap = argparse.ArgumentParser()
    ap.add_argument('--kuru', action='store_true')
    a = ap.parse_args()
    saat = dt.datetime.now(TR).strftime('%Y-%m-%d %H:00:00')   # gerçek ölçüm saati (TSİ, saat başına yuvarlanmış)
    tok = R.env('META_SOSYAL_TOKEN')
    isler = {'google': google, 'facebook': lambda: facebook(tok, saat), 'instagram': lambda: instagram(tok, saat), 'youtube': lambda: youtube(saat)}
    hata = []
    for ad, f in isler.items():
        try:
            k = f()
        except Exception as ex:  # noqa: BLE001 — kanal kanal: biri okunamazsa öbürleri yazılır, iş sonunda hata verir
            hata.append(f'{ad}: {ex}')
            print(f'{ad}: OKUNAMADI {ex}')
            continue
        ozet = f'{len(k)} kayıt' if ad == 'google' else f"{k[0]['deger']} ({k[0]['adet']} gönderi)"
        print(f'{ad}: {ozet}' + ('' if a.kuru else f' · yazıldı {gonder(k)}'))
    if hata:
        sys.exit('HATA: ' + ' | '.join(hata))


if __name__ == '__main__':
    main()
