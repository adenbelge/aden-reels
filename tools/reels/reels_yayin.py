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


def platform_kaydi(d, p):
    # defter biçimi: anahtar → {ig|fb|yt: {id, imza, oturum, ilk_satir, zaman}}; 04.11 öncesi biçim (üstte imza, platformda yalnız kimlik) aynı anlamda okunur
    x = (d or {}).get(p)
    if isinstance(x, dict):
        return x
    return {'id': x, 'imza': d.get('imza')} if x else None


KAYNAK_URL = 'https://adenbelge.com.tr/api/sosyal/reels-kaynak/'


def kaynak_video(meslek, seviye):
    """Kaynak klip yolu; yerelde yoksa sunucudan imzalı GET ile indirilir (06.11.2026: herkese açık depoda video tutulmaz)."""
    ad = f"makine-bakimci-{seviye}" if meslek == 'Makine Bakımcı' else VIDEO[meslek]
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
    v = r['video']
    icerik = v['meslek'] + '_' + r['video_il']
    fb_b, yt_b = utm(r['basvuru_url'], 'facebook', 'reels', icerik), utm(r['basvuru_url'], 'youtube', 'shorts', icerik)
    fb_t, yt_t = utm(TAKVIM, 'facebook', 'reels', icerik), utm(TAKVIM, 'youtube', 'shorts', icerik)
    merkez = f"Sınav merkezi: {v['merkez']}, {v['adres']}"
    hashtag = ['#MYKBelgesi', '#MYKSınavı', '#' + etiket(v['meslek']), '#' + etiket(v['il']), '#' + etiket(r['video_il']), '#MeslekiYeterlilik', '#AdenHR']
    hashtag = list(dict.fromkeys(hashtag))
    fb = '\n'.join([r['ilk_satir'], '', merkez, f"Harita: {r['harita_url']}" if r['harita_url'] else '', f"Başvuru: {fb_b}",
                    f'Tüm sınav tarihleri: {fb_t}', '', ' '.join(hashtag)])
    ig = '\n'.join([r['ilk_satir'], '', merkez, 'Başvuru ve tüm sınav tarihleri: profildeki bağlantı', '', ' '.join(hashtag)])
    yt_baslik = r['yt_baslik']  # halk dili ifadesi + il + tarih (plan sunucuda üretir; resmî ad açıklamanın ilk satırında)
    yt_aciklama = '\n'.join([r['ilk_satir'], '', merkez, f"Başvuru: {yt_b}", f"Harita: {r['harita_url']}" if r['harita_url'] else '',
                             f'Tüm sınav tarihleri: {yt_t}', '', ' '.join(hashtag)])   # 06.11.2026 kullanıcı "EKLE": IG/FB ile aynı 7 etiket → YouTube etiket sayfaları
    return re.sub(r'\n{3,}', '\n\n', fb), re.sub(r'\n{3,}', '\n\n', ig), yt_baslik, re.sub(r'\n{3,}', '\n\n', yt_aciklama)


def bekle_ig(kap, tok):
    for _ in range(90):
        s = requests.get(f'{GRAPH}/{kap}', params={'fields': 'status_code,status', 'access_token': tok}, timeout=60).json()
        if s.get('status_code') == 'FINISHED':
            return
        if s.get('status_code') in ('ERROR', 'EXPIRED'):
            raise RuntimeError(f'IG işleme hatası: {s}')
        time.sleep(10)
    raise RuntimeError('IG işleme bitmedi')


def kapak_ms(dosya):
    # vitrin kapağı = son kareye yakın an (06.11.2026): varsayılan ilk kare giriş hareketinin ortası → yazı bloğu kayık, ücret bandı yok
    import imageio_ffmpeg
    _, sn = imageio_ffmpeg.count_frames_and_secs(dosya)
    return max(0, int(sn * 1000) - 500)


def ig_yayinla(r, dosya, aciklama, tok):
    veri = {'media_type': 'REELS', 'upload_type': 'resumable', 'caption': aciklama, 'share_to_feed': 'true',
            'thumb_offset': str(kapak_ms(dosya)), 'access_token': tok}
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
    # kapak = son kare (06.11.2026, kullanıcı "KARE SEÇİMİ FB'DE YAPMIYOR MUSUN"): tüm yazılar + ücret + adenbelge.com.tr; API ile ölçüldü (is_preferred)
    import imageio_ffmpeg, tempfile
    kap = os.path.join(tempfile.mkdtemp(prefix='fbkapak_'), 'kapak.jpg')
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), '-y', '-loglevel', 'error', '-sseof', '-0.5', '-i', dosya, '-frames:v', '1', '-q:v', '2', kap], check=True)
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
    govde = {'snippet': {'title': baslik, 'description': aciklama, 'tags': [r['halk_ifade'], 'MYK belgesi', 'MYK sınavı', v['meslek'], v['il'], r['video_il']],
                         'categoryId': '27', 'defaultLanguage': 'tr', 'defaultAudioLanguage': 'tr'},
             'status': {'privacyStatus': 'public', 'selfDeclaredMadeForKids': False, 'containsSyntheticMedia': True}}
    parca = 'snippet,status'
    if r.get('lat'):
        govde['recordingDetails'] = {'location': {'latitude': float(r['lat']), 'longitude': float(r['lng'])}, 'locationDescription': v['merkez']}
        parca += ',recordingDetails'
    y = ys.videos().insert(part=parca, body=govde, media_body=MediaFileUpload(dosya, mimetype='video/mp4', resumable=True)).execute()
    # kapak = son kare (06.11.2026 kullanıcı; FB/IG ile aynı kural) — thumbnails.set kanalda ölçüldü (iDBUfWFwb38)
    import imageio_ffmpeg
    kap = os.path.join(tempfile.mkdtemp(prefix='ytkapak_'), 'kapak.jpg')
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), '-y', '-loglevel', 'error', '-sseof', '-0.5', '-i', dosya, '-frames:v', '1', '-q:v', '2', kap], check=True)
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
    ap.add_argument('--sure-dk', type=int, default=330, help='koşum süresi tavanı (iş akışı 350 dk): dolunca kalan iş sonraki koşuma')
    a = ap.parse_args(); p = a.platform; bas = time.time()
    plan = requests.get(PLAN_URL, timeout=120).json()['satirlar']
    plan = {anahtar(r): r for r in plan}
    defter = defter_oku()
    tok = env('META_SOSYAL_TOKEN') if p in ('ig', 'fb') else ''; ptok = sayfa_jetonu(tok) if p == 'fb' else ''
    ys = yt_servis() if p == 'yt' else None
    canli = canli_kimlikler(p, tok, ys)   # defter değil platformun kendisi: kayıtlı ama yayında olmayan = eksik
    isler = []
    for k, r in plan.items():
        e = platform_kaydi(defter.get(k), p)
        if not e or str(e.get('id')) not in canli:
            isler.append(('yayinla', k, r))
        elif e.get('imza') != r['imza']:
            isler.append(('degistir', k, r))
    for k in defter:
        e = platform_kaydi(defter[k], p)
        if k not in plan and e:
            isler.append(('kaldir', k, None) if str(e.get('id')) in canli else ('unut', k, None))
    sira = {'unut': 0, 'kaldir': 0, 'degistir': 1, 'yayinla': 2}
    # aynı oturumun il kopyaları art arda gitmesin (Meta kopya içerik dağıtımını kısar): önce ilk ilin bütün meslekleri, sonra sıradaki il
    il_sira = {}
    for r in plan.values():
        il_sira.setdefault(r['plaka'], len(il_sira))
    isler.sort(key=lambda x: (sira[x[0]], il_sira.get(x[2]['plaka'], 99) if x[2] else 0, x[2]['video']['tarih'] if x[2] else ''))
    if a.tek:
        isler = [i for i in isler if i[1] == a.tek]
    say = {t: sum(i[0] == t for i in isler) for t in sira}
    print(f"{p.upper()} · plan {len(plan)} · defter {len(defter)} · iş {len(isler)} {say}")
    if not a.uygula:
        for t, k, r in isler[:80]:
            print(f"  KURU {t:9} {k:45} {r['ilk_satir'] if r else ''}")
        return
    yapilan = 0
    for t, k, r in isler:
        if yapilan >= a.en_cok:
            print(f'{p.upper()} günlük sınır {a.en_cok} doldu; kalan iş kuyrukta'); break
        if time.time() - bas > a.sure_dk * 60:
            print(f'{p.upper()} süre tavanı {a.sure_dk} dk doldu; kalan iş sonraki koşumda'); break
        if t == 'unut':   # planda yok, platformda da yok: yalnız defter kaydı düşer
            defter_yama(k, p, None, f'reels {p} unut ' + k); print('  defterden düştü (platformda yoktu)', p, k); continue
        if t in ('degistir', 'kaldir'):
            try:
                sil({p: platform_kaydi(defter[k], p)['id']}, tok, ptok, ys, [p])
            except Exception as e:   # 06.11.2026: Instagram günlük silme sınırı (kod 9 / 2207074) işi durdurmaz — satır olduğu gibi kalır, sonraki koşu yeniden dener
                print(f'  {p.upper()} SİLİNEMEDİ, sonraki koşuma kaldı {k} — {str(e)[:160]}'); continue
            defter_yama(k, p, None, f'reels {p} sil ' + k)
            if t == 'kaldir':
                print('  kaldırıldı', p, k); continue
        gec = tempfile.mkdtemp(prefix='reels_yayin_')
        v = dict(r['video']); v['kaynak_video'] = kaynak_video(v['meslek'], v['seviye'])
        v['logo'] = v['meslek'] not in INSAAT   # ADEN markası baret/yelekte olan kliplerde logo yok; emlak, oto, kaynakçıda logo görselde
        # her platformun kendi güvenli alanı ve rengi (ReelsPlani::renkler): aynı ilin üç platformu ve kümedeki iller farklı renk
        vj = os.path.join(gec, f'{p}.json'); dosya = os.path.join(gec, f'{p}.mp4')
        json.dump(dict(v, platform=p, renk=int(v['renk'][p])), open(vj, 'w', encoding='utf-8'), ensure_ascii=False)
        subprocess.run([sys.executable, os.path.join(KOK, 'tools', 'reels', 'reels_video.py'), vj, dosya], check=True)
        fb_metin, ig_metin, yt_baslik, yt_metin = metinler(r)
        try:
            kimlik = {'ig': lambda: ig_yayinla(r, dosya, ig_metin, tok), 'fb': lambda: fb_yayinla(r, dosya, fb_metin, ptok),
                      'yt': lambda: yt_yayinla(r, dosya, yt_baslik, yt_metin, ys)}[p]()
        except Exception as e:  # yayınlanamayan kayıt deftere yazılmaz: sonraki koşum yeniden dener (ör. platform günlük sınırı)
            raise SystemExit(f'{p.upper()} YAYINLANAMADI {k} — {e}')
        defter_yama(k, p, {'id': kimlik, 'imza': r['imza'], 'oturum': r['oturum'], 'ilk_satir': r['ilk_satir'],
                           'zaman': dt.datetime.now().isoformat(timespec='seconds')}, f'reels {p} yayın ' + k)
        print(f'  {p.upper()} {kimlik} YAYINLANDI {k} {r["ilk_satir"]}'); yapilan += 1


if __name__ == '__main__':
    main()
