# -*- coding: utf-8 -*-
"""SINAV OTURUMU REELS — YAYIN MOTORU (docs/meta-reels-plani.md Faz 4).
Plan: https://adenbelge.com.tr/api/sosyal/reels-plan (ReelsPlani, tek sahip). Defter: imzalı uç /api/sosyal/reels-defter (ReelsDefteri → global_veri_seti 'meta_reels_defter')
(anahtar "plaka:meslek" → imza, oturum, ig/fb/yt kimlikleri, zaman). Yaşam döngüsü: yeni → yayınla · imza değişti → eskisini sil + yayınla ·
planda yok → sil · aynı → dokunma. Kota tavan: IG 100 / FB 30 / YT ~6 günde; taşan kuyrukta kalır (sıra: sınavı en yakın, sonra nokta sırası).

    python tools/reels/reels_yayin.py --platform ig    # KURU: ne yapacağını yazar, hiçbir şey yayınlamaz/silmez
    python tools/reels/reels_yayin.py --uygula --tek 23:Sorumlu Emlak Danışmanı --platform ig
    python tools/reels/reels_yayin.py --uygula --platform fb [--en-cok 30] [--sure-dk 330]

Anahtarlar: ortam değişkeni (GitHub gizli değeri) ya da yerel .env — META_SOSYAL_TOKEN, REELS_ANAHTAR, YT_TOKEN_JSON (yoksa ADEN-Kampanya/api/youtube_token.json),
REELS_KAYNAK (kaynak klip klasörü). Yazdırılmaz. Her platform ayrı koşar (--platform ig|fb|yt) ve deftere yalnız kendi kaydını yazar (PATCH);
yayınlanamayan video deftere girmez, sonraki koşum yeniden dener."""
import argparse, datetime as dt, json, os, re, subprocess, sys, tempfile, time
import requests
sys.stdout.reconfigure(encoding='utf-8')
KOK = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PLAN_URL = 'https://adenbelge.com.tr/api/sosyal/reels-plan'
GRAPH = 'https://graph.facebook.com/v26.0'
def _ayar(k):
    """Ortam değişkeni (GitHub gizli değeri) ya da yerel .env — hesap kimlikleri herkese açık depoda yazılı durmaz (06.11.2026)."""
    if os.environ.get(k):
        return os.environ[k]
    yol = os.path.join(KOK, '.env')
    m = re.search(rf'^{k}=(.*)$', open(yol, encoding='utf-8').read(), re.M) if os.path.exists(yol) else None
    if not m:
        raise RuntimeError(f'{k} tanımlı değil (ortam değişkeni ya da .env)')
    return m.group(1).strip().strip('"')


IG_HESAP = _ayar('META_IG_HESAP')
FB_SAYFA = _ayar('META_FB_SAYFA')
YT_KLASOR = 'C:/Users/LENOVO/Desktop/ADEN-Kampanya/api'
KAYNAK = os.environ.get('REELS_KAYNAK') or 'C:/Users/LENOVO/Desktop/ADEN-Kampanya/video/ham'
DEFTER_URL = 'https://adenbelge.com.tr/api/sosyal/reels-defter'
TAKVIM = 'https://adenbelge.com.tr/tr/hizmetler/sinav-tarihleri'
# plan meslek adı → kaynak video (Makine Bakımcı seviyeye göre)
VIDEO = {'Sorumlu Emlak Danışmanı': 'sorumlu-emlak-danismani', 'Motorlu Kara Taşıtları Alım Satım Sorumlusu': 'motorlu-kara-tasitlari-alim-satim-sorumlusu',
         'Çelik Kaynakçısı': 'celik-kaynakcisi', 'İnşaat Boyacısı': 'insaat-boyacisi', 'İnşaat İşçisi': 'insaat-iscisi', 'Ahşap Kalıpçı': 'ahsap-kalipci',
         'Alçı Levha Uygulayıcısı': 'alci-levha', 'Alçı Sıva Uygulayıcısı': 'alci-siva', 'Betonarme Demircisi': 'betonarme-demircisi', 'Duvarcı': 'duvarci',
         'Isı Yalıtımcısı': 'isi-yalitimcisi', 'Seramik Karo Kaplamacısı': 'seramik-karo', 'Panel Kalıpçı': 'panel-kalipci', 'Sıvacı': 'sivaci'}


# kaynak klibinde ADEN markası (baret/yelek) olan meslekler — videoya ayrıca logo konmaz (kullanıcı 04.11.2026)
INSAAT = {'İnşaat Boyacısı', 'İnşaat İşçisi', 'Duvarcı', 'Sıvacı', 'Alçı Sıva Uygulayıcısı', 'Alçı Levha Uygulayıcısı', 'Ahşap Kalıpçı',
          'Panel Kalıpçı', 'Betonarme Demircisi', 'Seramik Karo Kaplamacısı', 'Isı Yalıtımcısı',
          'Makine Bakımcı'}   # makine bakımcı klibinde de ADEN baret üstünde (kullanıcı 04.11.2026)


def env(k):
    if os.environ.get(k):
        return os.environ[k]
    yol = os.path.join(KOK, '.env')
    m = re.search(rf'^{k}=(.*)$', open(yol, encoding='utf-8').read(), re.M) if os.path.exists(yol) else None
    return m.group(1).strip().strip('"') if m else ''


def imzali_get(url):
    """Plan ucu da imzalı (14.11.2026, kullanıcı "AÇIK VERİ OLAMAZ"): defterle aynı imza, yöntem GET, gövde boş."""
    import hashlib, hmac
    ts = str(int(time.time()))
    imza = hmac.new(env('REELS_ANAHTAR').encode(), '\n'.join(['GET', ts, hashlib.sha256(b'').hexdigest()]).encode(), hashlib.sha256).hexdigest()
    r = requests.get(url, headers={'X-Reels-Zaman': ts, 'X-Reels-Imza': imza}, timeout=120)
    r.raise_for_status()
    return r.json()


def _defter_istek(yontem, govde=b''):
    import hashlib, hmac
    ts = str(int(time.time()))
    imza = hmac.new(env('REELS_ANAHTAR').encode(), '\n'.join([yontem, ts, hashlib.sha256(govde).hexdigest()]).encode(), hashlib.sha256).hexdigest()
    r = requests.request(yontem, DEFTER_URL, data=govde or None, timeout=60,
                         headers={'X-Reels-Zaman': ts, 'X-Reels-Imza': imza, 'Content-Type': 'application/json'})
    r.raise_for_status()
    return r.json()['defter']


def defter_oku():
    return dict(_defter_istek('GET'))


def defter_yama(anahtar, platform, kayit, kaynak):
    # sunucu satır kilidiyle birleştirir: IG / FB / YT işleri aynı anda yazsa da birbirinin kaydını ezmez
    _defter_istek('PATCH', json.dumps({'yama': {anahtar: {platform: kayit}}, 'kaynak': kaynak}, ensure_ascii=False).encode('utf-8'))


def anahtar(r):
    # defter anahtarı "plaka:meslek"; iki seviyesi ayrı meslek sayılan Makine Bakımcı seviyeyle ayrılır (16 meslek, kullanıcı 05.11.2026)
    v = r['video']
    return f"{r['plaka']}:{v['meslek']}" + (f" (Seviye {v['seviye']})" if v['meslek'] == 'Makine Bakımcı' else '')


def klip_adi(meslek, seviye):
    return f"makine-bakimci-{seviye}" if meslek == 'Makine Bakımcı' else VIDEO[meslek]


def gorsel(k):
    # GÖRSEL İÇERİK ANAHTARI (kullanıcı 08.11.2026 "NE OLURSA OLSUN AYNI GÖRSEL VİDEO İÇERİĞİ ARKA ARKAYA YAYINLANMAMALI · görsel içerik =
    # HAM VİDEO (kapak fotoğrafı); yazı, tarih, ücret sonradan eklenen katman"): anahtar KAYNAK KLİP dosyasıdır — iki meslek aynı klibi
    # kullansa da aynı içerik sayılır. Defter anahtarı "plaka:meslek" ya da "plaka:Makine Bakımcı (Seviye n)".
    m = re.match(r'^(.*) \(Seviye (\d+)\)$', k.split(':', 1)[1])
    return klip_adi(m.group(1), m.group(2)) if m else klip_adi(k.split(':', 1)[1], '')


def platform_kaydi(d, p):
    # defter biçimi: anahtar → {ig|fb|yt: {id, imza, oturum, ilk_satir, zaman}}; 04.11 öncesi biçim (üstte imza, platformda yalnız kimlik) aynı anlamda okunur
    x = (d or {}).get(p)
    if isinstance(x, dict):
        return x
    return {'id': x, 'imza': d.get('imza')} if x else None


KAYNAK_URL = 'https://adenbelge.com.tr/api/sosyal/reels-kaynak/'


def kaynak_video(meslek, seviye):
    """Kaynak klip yolu; yerelde yoksa sunucudan imzalı GET ile indirilir (06.11.2026: herkese açık depoda video tutulmaz)."""
    ad = klip_adi(meslek, seviye)
    yol = f'{KAYNAK}/{ad}.mp4'
    if not os.path.exists(yol):
        import hashlib, hmac
        ts = str(int(time.time()))
        imza = hmac.new(env('REELS_ANAHTAR').encode(), '\n'.join(['GET', ts, hashlib.sha256(b'').hexdigest()]).encode(), hashlib.sha256).hexdigest()
        r = requests.get(KAYNAK_URL + ad, headers={'X-Reels-Zaman': ts, 'X-Reels-Imza': imza}, timeout=300)
        if r.status_code != 200 or r.headers.get('Content-Type', '').split(';')[0] != 'video/mp4':
            raise RuntimeError(f'kaynak klip indirilemedi: {ad} ({r.status_code})')
        os.makedirs(KAYNAK, exist_ok=True)
        open(yol, 'wb').write(r.content)
    return yol


def etiket(s):
    # her sözcüğün ilk harfi Türkçe büyük, kalanı olduğu gibi (Danışmanı, Elazığ, İnşaat — 'i'.upper() = 'I' hatası yok)
    buyuk = lambda c: {'i': 'İ', 'ı': 'I'}.get(c, c.upper())
    return ''.join(buyuk(w[0]) + w[1:] for w in re.split(r'[^0-9A-Za-zÇĞİÖŞÜçğıöşü]+', s) if w)


def utm(url, kaynak, ortam, icerik):
    # 05.11.2026 ziyaret kaynağı sayacı (docs/ziyaret-kaynagi-plani.md Faz 4): kendi bağlantımız kaynağını söyler; sınıflandırıcı
    # App\Support\ZiyaretKaynagi utm_source'u okur. Değerler sayaç biçiminde (küçük harf, a-z0-9._-).
    from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
    kes = lambda x: re.sub(r'[^a-z0-9._-]+', '-', x.translate(str.maketrans('çğıİöşüÇĞÖŞÜ', 'cgiiosucgosu')).lower()).strip('-')[:64]
    u = urlsplit(url)
    q = [(k, v) for k, v in parse_qsl(u.query, keep_blank_values=True) if not k.startswith('utm_')]
    q += [('utm_source', kaynak), ('utm_medium', ortam), ('utm_campaign', 'reels'), ('utm_content', kes(icerik))]
    return urlunsplit((u.scheme, u.netloc, u.path, urlencode(q), u.fragment))


def metinler(r):
    """ÇOKLU OTURUM (08.11.2026): her satır (il · tarih · gün · saatler) kendi merkezi, başvuru ve harita bağlantısıyla; IG'de bağlantı yok (profil)."""
    v = r['video']
    icerik = v['meslek'] + '_' + r['video_il']
    fb_t, yt_t = utm(TAKVIM, 'facebook', 'reels', icerik), utm(TAKVIM, 'youtube', 'shorts', icerik)
    iller = [o['il'] for o in v['oturumlar']]
    hashtag = ['#MYKBelgesi', '#MYKSınavı', '#' + etiket(v['meslek'])] + ['#' + etiket(i) for i in iller] + ['#' + etiket(i) for i in r.get('iller', [r['video_il']])] + ['#MeslekiYeterlilik', '#AdenHR']
    hashtag = list(dict.fromkeys(hashtag))

    def bloklar(kaynak, ortam):
        satir = []
        for s in r['satirlar']:
            satir += [s['etiket'], f"Sınav merkezi: {s['merkez']}, {s['adres']}"]
            if kaynak:
                satir += [f"Başvuru: {utm(s['basvuru_url'], kaynak, ortam, icerik)}"] + ([f"Harita: {s['harita_url']}"] if s['harita_url'] else [])
            satir.append('')
        return satir
    fb = '\n'.join([r['ilk_satir'], ''] + bloklar('facebook', 'reels') + [f'Tüm sınav tarihleri: {fb_t}', '', ' '.join(hashtag)])
    ig = '\n'.join([r['ilk_satir'], ''] + bloklar(None, None) + ['Başvuru ve tüm sınav tarihleri: profildeki bağlantı', '', ' '.join(hashtag)])
    yt_baslik = r['yt_baslik']  # halk dili ifadesi + satırların il + tarihi (plan sunucuda üretir; resmî ad açıklamanın ilk satırında)
    yt_aciklama = '\n'.join([r['ilk_satir'], ''] + bloklar('youtube', 'shorts') + [f'Tüm sınav tarihleri: {yt_t}', '', ' '.join(hashtag)])
    return re.sub(r'\n{3,}', '\n\n', fb), re.sub(r'\n{3,}', '\n\n', ig), yt_baslik, re.sub(r'\n{3,}', '\n\n', yt_aciklama)


def metin_imzasi(r, p):
    """METİN İMZASI (08.11.2026): yalnız açıklama/başlık. Görüntü imzası (plan 'imza') videoya basılı bilgiden; ikisi ayrı tutulur —
    yalnız metin değişince video yeniden üretilmez, FB ve YT'de yerinde düzenlenir (IG API yayınlanmış Reels açıklamasını değiştirmez)."""
    import hashlib
    fb, ig, ytb, yta = metinler(r)
    return hashlib.sha256(json.dumps({'fb': [fb], 'ig': [ig], 'yt': [ytb, yta]}[p], ensure_ascii=False).encode()).hexdigest()[:16]


def metin_guncelle(p, kimlik, r, ptok, ys):
    fb, ig, ytb, yta = metinler(r)
    if p == 'fb':
        x = requests.post(f'{GRAPH}/{kimlik}', data={'description': fb, 'access_token': ptok}, timeout=60).json()
        if not x.get('success'):
            raise RuntimeError(f'FB metin: {x}')
    elif p == 'yt':
        v = r['video']
        ys.videos().update(part='snippet', body={'id': kimlik, 'snippet': {'title': ytb, 'description': yta, 'categoryId': '27', 'defaultLanguage': 'tr',
                                                                           'tags': yt_etiketler(r)}}).execute()


def yt_etiketler(r):
    v = r['video']
    return list(dict.fromkeys([r['halk_ifade'], 'MYK belgesi', 'MYK sınavı', v['meslek']] + [o['il'] for o in v['oturumlar']] + [r['video_il']]))


def sinir_mi(x):
    """Platformun günlük/anlık sınırı mı (hata değil, normal durak): YouTube kanal yükleme sınırı ve kota, Meta istek ve yayın sınırları."""
    m = str(x)
    return any(i in m for i in ['uploadLimitExceeded', 'quotaExceeded', 'rateLimitExceeded', 'dailyLimitExceeded',
                                "'code': 4,", "'code': 17,", "'code': 32,", "'code': 613,", '2207042', 'request limit reached'])


def eski_gecersiz(kayit, pencere):
    """Eski videoda artık penceredeki açık oturumlar arasında olmayan oturum var mı (sınavı geçti / başvuru kapandı / iptal) — varsa video yanlış bilgi taşır."""
    eski = kayit.get('oturumlar') or ([kayit['oturum']] if kayit.get('oturum') else [])
    return any(o not in pencere for o in eski)


def bekle_ig(kap, tok):
    for _ in range(90):
        s = requests.get(f'{GRAPH}/{kap}', params={'fields': 'status_code,status', 'access_token': tok}, timeout=60).json()
        if s.get('status_code') == 'FINISHED':
            return
        if s.get('status_code') in ('ERROR', 'EXPIRED'):
            raise RuntimeError(f'IG işleme hatası: {s}')
        time.sleep(10)
    raise RuntimeError('IG işleme bitmedi')


KAPAK_URL = 'https://adenbelge.com.tr/api/sosyal/reels-kapak/'


def kapak_yukle(dosya):
    """Instagram kapağı (08.11.2026, kullanıcı): IG API kapak dosyası almaz, yalnız herkese açık adres (cover_url) okur → kapak
    (kaynak klibin ilk karesi + katmanın tam hâli; reels_video.py <video>_kapak.jpg) imzalı PUT ile sunucuya, Instagram GET ile okur (2 gün yaşar)."""
    import hashlib, hmac, secrets
    kap = os.path.splitext(dosya)[0] + '_kapak.jpg'
    if not os.path.exists(kap):
        raise RuntimeError(f'IG kapak dosyası yok: {kap}')
    govde = open(kap, 'rb').read(); ts = str(int(time.time()))
    imza = hmac.new(env('REELS_ANAHTAR').encode(), '\n'.join(['PUT', ts, hashlib.sha256(govde).hexdigest()]).encode(), hashlib.sha256).hexdigest()
    y = requests.put(KAPAK_URL + secrets.token_hex(16), data=govde, timeout=120,
                     headers={'X-Reels-Zaman': ts, 'X-Reels-Imza': imza, 'Content-Type': 'image/jpeg'})
    y.raise_for_status()
    url = y.json()['url']
    g = requests.get(url, timeout=60)   # Instagram okumadan önce adres gerçekten açılıyor mu
    if g.status_code != 200 or g.content != govde:
        raise RuntimeError(f'IG kapak adresi okunamadı: {g.status_code}')
    return url


def ig_yayinla(r, dosya, aciklama, tok):
    veri = {'media_type': 'REELS', 'upload_type': 'resumable', 'caption': aciklama, 'share_to_feed': 'true',
            'cover_url': kapak_yukle(dosya), 'access_token': tok}
    if r.get('konum_id'):
        veri['location_id'] = r['konum_id']
    k = requests.post(f'{GRAPH}/{IG_HESAP}/media', data=veri, timeout=60).json()
    if 'id' not in k:
        raise RuntimeError(f'IG konteyner: {k}')
    boyut = os.path.getsize(dosya)
    u = requests.post(k['uri'], headers={'Authorization': f'OAuth {tok}', 'offset': '0', 'file_size': str(boyut)}, data=open(dosya, 'rb'), timeout=600).json()
    if not u.get('success'):
        raise RuntimeError(f'IG yükleme: {u}')
    bekle_ig(k['id'], tok)
    y = requests.post(f'{GRAPH}/{IG_HESAP}/media_publish', data={'creation_id': k['id'], 'access_token': tok}, timeout=120).json()
    if 'id' not in y:
        raise RuntimeError(f'IG yayın: {y}')
    return y['id']


def sayfa_jetonu(tok):
    s = requests.get(f'{GRAPH}/{FB_SAYFA}', params={'fields': 'access_token', 'access_token': tok}, timeout=60).json()
    if 'access_token' not in s:
        raise RuntimeError(f'Sayfa jetonu: {s}')
    return s['access_token']


def fb_yayinla(r, dosya, aciklama, ptok):
    b = requests.post(f'{GRAPH}/{FB_SAYFA}/video_reels', data={'upload_phase': 'start', 'access_token': ptok}, timeout=60).json()
    if 'video_id' not in b:
        raise RuntimeError(f'FB başlat: {b}')
    boyut = os.path.getsize(dosya)
    u = requests.post(b['upload_url'], headers={'Authorization': f'OAuth {ptok}', 'offset': '0', 'file_size': str(boyut)}, data=open(dosya, 'rb'), timeout=600).json()
    if not u.get('success'):
        raise RuntimeError(f'FB yükleme: {u}')
    # kaynak videolar yapay zekâyla üretildi → Meta etiketi (kullanıcı 04.11.2026)
    veri = {'upload_phase': 'finish', 'video_id': b['video_id'], 'video_state': 'PUBLISHED', 'description': aciklama, 'is_ai_generated': 'true', 'access_token': ptok}
    if r.get('konum_id'):
        veri['place'] = r['konum_id']
    f = requests.post(f'{GRAPH}/{FB_SAYFA}/video_reels', data=veri, timeout=120).json()
    if not f.get('success'):
        raise RuntimeError(f'FB yayın: {f}')
    fb_kapak(b['video_id'], dosya, ptok)
    return b['video_id']


def fb_kapak(video_id, dosya, ptok):
    # kapak = kaynak klibin İLK karesi + katmanın tam hâli (08.11.2026, kullanıcı): reels_video.py videoyla birlikte <video>_kapak.jpg üretir
    kap = os.path.splitext(dosya)[0] + '_kapak.jpg'
    if not os.path.exists(kap):
        raise RuntimeError(f'FB kapak dosyası yok: {kap}')
    for _ in range(30):   # video işlenmeden kapak yüklenirse yok sayılabilir → hazır olana dek bekle (en çok ~10 dk)
        if requests.get(f'{GRAPH}/{video_id}', params={'fields': 'status', 'access_token': ptok}, timeout=60).json().get('status', {}).get('video_status') == 'ready':
            break
        time.sleep(20)
    y = requests.post(f'{GRAPH}/{video_id}/thumbnails', data={'is_preferred': 'true', 'access_token': ptok},
                      files={'source': ('kapak.jpg', open(kap, 'rb'), 'image/jpeg')}, timeout=120).json()
    if not y.get('success'):
        raise RuntimeError(f'FB kapak: {y}')


def yt_servis():
    if os.environ.get('YT_TOKEN_JSON'):
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build
        c = Credentials.from_authorized_user_info(json.loads(os.environ['YT_TOKEN_JSON']))
        if not c.valid:
            c.refresh(Request())
        return build('youtube', 'v3', credentials=c, cache_discovery=False)
    sys.path.insert(0, YT_KLASOR)
    import yt  # ADEN-Kampanya/api/yt.py (youtube_token.json)
    return yt.servis()


def yt_yayinla(r, dosya, baslik, aciklama, ys):
    from googleapiclient.http import MediaFileUpload
    v = r['video']
    govde = {'snippet': {'title': baslik, 'description': aciklama, 'tags': yt_etiketler(r),
                         'categoryId': '27', 'defaultLanguage': 'tr', 'defaultAudioLanguage': 'tr'},
             'status': {'privacyStatus': 'public', 'selfDeclaredMadeForKids': False, 'containsSyntheticMedia': True}}
    parca = 'snippet,status'
    if r.get('lat'):
        govde['recordingDetails'] = {'location': {'latitude': float(r['lat']), 'longitude': float(r['lng'])}, 'locationDescription': r['merkez']}
        parca += ',recordingDetails'
    y = ys.videos().insert(part=parca, body=govde, media_body=MediaFileUpload(dosya, mimetype='video/mp4', resumable=True)).execute()
    # kapak = kaynak klibin İLK karesi + katmanın tam hâli (08.11.2026, kullanıcı; FB ile aynı dosya) — reels_video.py üretir
    kap = os.path.splitext(dosya)[0] + '_kapak.jpg'
    if not os.path.exists(kap):
        raise RuntimeError(f'YT kapak dosyası yok: {kap}')
    ys.thumbnails().set(videoId=y['id'], media_body=MediaFileUpload(kap, mimetype='image/jpeg')).execute()
    return y['id']


def sil(kayit, tok, ptok, ys, platformlar):
    if 'ig' in platformlar and kayit.get('ig'):
        x = requests.delete(f"{GRAPH}/{kayit['ig']}", params={'access_token': tok}, timeout=60).json()
        if not x.get('success'):
            raise RuntimeError(f'IG silme: {x}')
    if 'fb' in platformlar and kayit.get('fb'):
        x = requests.delete(f"{GRAPH}/{kayit['fb']}", params={'access_token': ptok}, timeout=60).json()
        if not x.get('success'):
            raise RuntimeError(f'FB silme: {x}')
    if 'yt' in platformlar and kayit.get('yt'):
        ys.videos().delete(id=kayit['yt']).execute()


def canli_kimlikler(p, tok, ys):
    """Platformda ŞU AN yayında olan gönderi kimlikleri (06.11.2026, kullanıcı "otomatik yayın hangi il × meslek yayını var/yok tespit edemiyor mu?"):
    defterde kayıtlı ama platformda olmayan (silinmiş, kaldırılmış) gönderi yeniden yayınlanır. Liste okunamazsa iş DURUR — boş liste
    "hiçbiri yayında değil" sayılıp her şey yeniden yayınlanmasın."""
    ids = set()
    if p in ('ig', 'fb'):
        url = f'{GRAPH}/{IG_HESAP}/media' if p == 'ig' else f'{GRAPH}/{FB_SAYFA}/videos'
        jt = tok if p == 'ig' else sayfa_jetonu(tok)
        prm = {'fields': 'id', 'limit': 100, 'access_token': jt}
        while url:
            j = requests.get(url, params=prm, timeout=60).json()
            if 'error' in j:
                raise SystemExit(f"{p.upper()} canlı gönderi listesi okunamadı: {j['error'].get('message')}")
            ids |= {x['id'] for x in j.get('data', [])}
            url, prm = j.get('paging', {}).get('next'), None
    else:
        yukleme = ys.channels().list(part='contentDetails', mine=True).execute()['items'][0]['contentDetails']['relatedPlaylists']['uploads']
        sayfa = None
        while True:
            j = ys.playlistItems().list(part='contentDetails', playlistId=yukleme, maxResults=50, pageToken=sayfa).execute()
            ids |= {x['contentDetails']['videoId'] for x in j['items']}
            sayfa = j.get('nextPageToken')
            if not sayfa:
                break
    if not ids:
        raise SystemExit(f'{p.upper()} canlı gönderi listesi BOŞ geldi — güvenlik için durdu')
    return ids


def main():
    # TEK PLATFORM (kullanıcı 04.11.2026 "darboğaza sokmasın"): her platform kendi işinde, kendi sınırıyla, aynı anda koşar; biri takılırsa öbürü sürer
    ap = argparse.ArgumentParser()
    ap.add_argument('--uygula', action='store_true'); ap.add_argument('--tek', default='')
    ap.add_argument('--platform', required=True, choices=['ig', 'fb', 'yt']); ap.add_argument('--en-cok', type=int, default=6)
    ap.add_argument('--sil-ara-sn', type=int, default=90, help='iki silme arası bekleme (sn)')
    ap.add_argument('--yalniz-temizlik', action='store_true', help='yalnız silme / defter temizliği; yeni yayın ve metin güncelleme YOK')
    ap.add_argument('--sure-dk', type=int, default=330, help='koşum süresi tavanı (iş akışı 350 dk): dolunca kalan iş sonraki koşuma')
    a = ap.parse_args(); p = a.platform; bas = time.time()
    veri = imzali_get(PLAN_URL)
    plan = {anahtar(r): r for r in veri['satirlar']}
    pencere = set(veri['pencere'])   # penceredeki tüm açık oturumlar: eski videodaki oturum burada yoksa video yanlış bilgi taşır
    defter = defter_oku()
    tok = env('META_SOSYAL_TOKEN') if p in ('ig', 'fb') else ''; ptok = sayfa_jetonu(tok) if p == 'fb' else ''
    ys = yt_servis() if p == 'yt' else None
    canli = canli_kimlikler(p, tok, ys)   # defter değil platformun kendisi: kayıtlı ama yayında olmayan = eksik
    # İŞLER (08.11.2026, kullanıcı onaylı yayın döngüsü):
    #  bayat    — görüntü değişti VE eski videoda artık geçerli olmayan oturum var → eski hemen silinir (yeni yayınlanamasa da), sonra yayinla
    #  degistir — görüntü değişti, eski hâlâ doğru → ÖNCE yeni yayınlanır, başarılıysa eski silinir (yayınlanamazsa eski yerinde kalır)
    #  metin    — görüntü aynı, yalnız açıklama/başlık değişti → FB ve YT'de yerinde düzenlenir (IG API izin vermez)
    #  eskisil  — önceki koşumda yeni yayınlanmış ama eskisi silinememiş video
    #  kaldir / unut — planda olmayan video (sınavı pencereden çıktı)
    isler = []
    for k, r in plan.items():
        e = platform_kaydi(defter.get(k), p)
        if not e or str(e.get('id')) not in canli:
            isler.append(('yayinla', k, r))
        elif e.get('imza') != r['imza']:
            if eski_gecersiz(e, pencere):
                isler += [('bayat', k, r), ('yayinla', k, r)]
            else:
                isler.append(('degistir', k, r))
        elif p in ('fb', 'yt') and e.get('metin_imza') != metin_imzasi(r, p):
            isler.append(('metin', k, r))
    for k in defter:
        e = platform_kaydi(defter[k], p)
        if e and e.get('eski_id'):
            isler.append(('eskisil', k, None))
        if k not in plan and e:
            isler.append(('kaldir', k, None) if str(e.get('id')) in canli else ('unut', k, None))
    sira = {'unut': 0, 'kaldir': 0, 'bayat': 0, 'eskisil': 0, 'metin': 1, 'degistir': 2, 'yayinla': 3}
    # aynı oturumun il kopyaları art arda gitmesin (Meta kopya içerik dağıtımını kısar): önce ilk ilin bütün meslekleri, sonra sıradaki il
    il_sira = {}
    for r in plan.values():
        il_sira.setdefault(r['plaka'], len(il_sira))
    isler.sort(key=lambda x: (sira[x[0]], il_sira.get(x[2]['plaka'], 99) if x[2] else 0, x[2]['video']['tarih'] if x[2] else ''))
    if a.tek:
        isler = [i for i in isler if i[1] == a.tek]
    if a.yalniz_temizlik:
        isler = [i for i in isler if i[0] in ('unut', 'kaldir', 'bayat', 'eskisil')]
    # platformda EN SON yayınlanan videonun görsel içeriği (defter zamanı; yalnız hâlâ yayında olan)
    son = max(((x.get('zaman') or '', gorsel(k)) for k in defter if (x := platform_kaydi(defter[k], p)) and str(x.get('id')) in canli), default=('', None))[1]
    # yayın işleri açgözlü sıralanır: her video bir öncekinden FARKLI görsel içerikte (silme/metin işleri önde, sıraları değişmez)
    on = [i for i in isler if i[0] not in ('degistir', 'yayinla')]
    kalan = [i for i in isler if i[0] in ('degistir', 'yayinla')]
    yayin, onceki = [], son
    while kalan:
        j = next((n for n, i in enumerate(kalan) if gorsel(i[1]) != onceki), 0)
        yayin.append(kalan.pop(j)); onceki = gorsel(yayin[-1][1])
    isler = on + yayin
    say = {t: sum(i[0] == t for i in isler) for t in sira}
    print(f"{p.upper()} · plan {len(plan)} · defter {len(defter)} · iş {len(isler)} {say}")
    if not a.uygula:
        for t, k, r in isler[:80]:
            print(f"  KURU {t:9} {k:45} {r['ilk_satir'] if r else ''}")
        return

    def kayit(r, kimlik):
        return {'id': kimlik, 'imza': r['imza'], 'metin_imza': metin_imzasi(r, p), 'oturumlar': r['oturumlar'], 'ilk_satir': r['ilk_satir'],
                'zaman': dt.datetime.now().isoformat(timespec='seconds')}

    silme_engel = []

    def silmeyi_dene(kimlik, k):
        if silme_engel:   # 08.11.2026: ilk silme hatasından sonra o koşumda başka silme DENENMEZ (sınırdaki hesabı zorlamaz; 07.11'de 28 deneme)
            return False
        try:
            sil({p: kimlik}, tok, ptok, ys, [p])
            time.sleep(a.sil_ara_sn)   # silmeler aralıklı (kullanıcı 08.11.2026 "sınıra takılmadan, aralıklı")
            return True
        except Exception as x:   # 06.11.2026: Instagram günlük silme sınırı (kod 9 / 2207074) işi durdurmaz — sonraki koşu yeniden dener
            print(f'  {p.upper()} SİLİNEMEDİ, sonraki koşuma kaldı {k} — {str(x)[:160]}')
            silme_engel.append(k)
            return False

    yapilan = hata = art_arda = 0
    for t, k, r in isler:
        e = platform_kaydi(defter.get(k), p)
        if t == 'unut':   # planda yok, platformda da yok: yalnız defter kaydı düşer
            defter_yama(k, p, None, f'reels {p} unut ' + k); print('  defterden düştü (platformda yoktu)', p, k); continue
        if t == 'eskisil':
            if str(e['eski_id']) not in canli or silmeyi_dene(e['eski_id'], k):
                yeni = dict(e); yeni.pop('eski_id', None)
                defter_yama(k, p, yeni, f'reels {p} eski sil ' + k); defter.setdefault(k, {})[p] = yeni
                print('  eski video silindi', p, k)
            continue
        if t in ('kaldir', 'bayat'):
            if silmeyi_dene(e['id'], k):
                defter_yama(k, p, None, f'reels {p} sil ' + k); defter.setdefault(k, {})[p] = None
                print('  kaldırıldı' if t == 'kaldir' else '  geçersiz oturumlu eski video silindi', p, k)
            continue
        if t == 'metin':
            try:
                metin_guncelle(p, e['id'], r, ptok, ys)
                yeni = dict(e, metin_imza=metin_imzasi(r, p))
                defter_yama(k, p, yeni, f'reels {p} metin ' + k); defter.setdefault(k, {})[p] = yeni
                print('  metin güncellendi', p, k)
            except Exception as x:
                print(f'  {p.upper()} METİN GÜNCELLENEMEDİ {k} — {str(x)[:160]}')
            continue
        if t == 'yayinla' and e and str(e.get('id')) in canli:   # 'bayat' silinemediyse eski yerinde: yeniyi yayınlamak çift video olur
            continue
        # 08.11.2026 (kullanıcı "aynı içerik defalarca yayınlanmış — MANTIKSIZ"): bu koşumda bir silme bile başarısızsa YENİ VİDEO YAYINLANMAZ —
        # eski kopyalar duruyorken yenisi eklenirse profilde aynı içerik birikir (07–08.11: silme sınırı varken 'degistir' 30 kopya bıraktı).
        if silme_engel:
            print(f'{p.upper()} silinemeyen eski video var ({len(silme_engel)}); bu koşumda yeni yayın YOK'); break
        if gorsel(k) == son:   # son kapı: aynı görsel içerik arka arkaya ASLA (sıralamada kaçan olursa atlanır, sonraki koşum)
            print(f'  {p.upper()} ATLANDI — bir önceki yayınla aynı görsel içerik: {k}'); continue
        if yapilan >= a.en_cok:
            print(f'{p.upper()} günlük sınır {a.en_cok} doldu; kalan iş kuyrukta'); break
        if time.time() - bas > a.sure_dk * 60:
            print(f'{p.upper()} süre tavanı {a.sure_dk} dk doldu; kalan iş sonraki koşumda'); break
        # 08.11.2026 (kullanıcı "UYGULA"): platform SINIRI hata değil normal duraktır (iş yeşil biter, kalan sonraki koşuma);
        # tek videodaki hata koşumu durdurmaz — video atlanır, sonraki koşum yeniden dener; üst üste 5 hata = geçici değil → dur, iş kırmızı.
        # Yayınlanamayan kayıt deftere yazılmaz; 'degistir'de eski video yerinde kalır.
        try:
            gec = tempfile.mkdtemp(prefix='reels_yayin_')
            v = dict(r['video']); v['kaynak_video'] = kaynak_video(v['meslek'], v['seviye'])
            v['logo'] = v['meslek'] not in INSAAT   # ADEN markası baret/yelekte olan kliplerde logo yok; emlak, oto, kaynakçıda logo görselde
            # her platformun kendi güvenli alanı ve rengi (ReelsPlani::renkler): aynı ilin üç platformu ve kümedeki iller farklı renk
            vj = os.path.join(gec, f'{p}.json'); dosya = os.path.join(gec, f'{p}.mp4')
            json.dump(dict(v, platform=p, renk=int(v['renk'][p])), open(vj, 'w', encoding='utf-8'), ensure_ascii=False)
            subprocess.run([sys.executable, os.path.join(KOK, 'tools', 'reels', 'reels_video.py'), vj, dosya], check=True)
            fb_metin, ig_metin, yt_baslik, yt_metin = metinler(r)
            kimlik = {'ig': lambda: ig_yayinla(r, dosya, ig_metin, tok), 'fb': lambda: fb_yayinla(r, dosya, fb_metin, ptok),
                      'yt': lambda: yt_yayinla(r, dosya, yt_baslik, yt_metin, ys)}[p]()
        except Exception as x:
            if sinir_mi(x):
                print(f'{p.upper()} PLATFORM SINIRI ({str(x)[:160]}) — kalan iş sonraki koşumda'); break
            hata += 1; art_arda += 1
            print(f'::warning::{p.upper()} YAYINLANAMADI, atlandı (sonraki koşum yeniden dener) {k} — {str(x)[:300]}')
            if art_arda >= 5:
                raise SystemExit(f'{p.upper()} üst üste 5 video yayınlanamadı — sorun geçici değil, koşum durdu')
            continue
        art_arda = 0
        yeni = kayit(r, kimlik)
        if t == 'degistir' and not silmeyi_dene(e['id'], k):   # önce yeni yayınlandı; eski silinemezse sonraki koşumda 'eskisil'
            yeni['eski_id'] = e['id']
        defter_yama(k, p, yeni, f'reels {p} yayın ' + k); defter.setdefault(k, {})[p] = yeni
        print(f'  {p.upper()} {kimlik} YAYINLANDI {k} {r["ilk_satir"]}'); yapilan += 1; son = gorsel(k)
    print(f'{p.upper()} özet: yayınlanan {yapilan} · atlanan (hata) {hata}')

if __name__ == '__main__':
    main()
