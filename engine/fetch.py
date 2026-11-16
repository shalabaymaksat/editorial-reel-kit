"""Видео/активтерді жүктеу: Google Drive файл НЕМЕСЕ папка сілтемесі, Dropbox, тікелей URL, не жергілікті файл.

python3 fetch.py inbox  URL [URL…]      -> $ER_HOME/inbox/   (видеолар)
python3 fetch.py assets URL [URL…]      -> $ER_HOME/assets/  (логотип, скрин)
python3 fetch.py broll  URL [URL…]      -> $ER_HOME/broll/   (B-roll видеолар)
Drive сілтемесі «Anyone with the link» болуы керек.
"""
import os, re, sys, glob
from paths import HOME as PP_HOME

VID = ('.mov', '.mp4', '.m4v', '.webm')


def drive(url, out):
    import gdown
    if '/folders/' in url:
        gdown.download_folder(url=url, output=out, quiet=False, remaining_ok=True)
    else:
        m = re.search(r'(?:/file/d/|[?&]id=)([\w-]+)', url)
        gdown.download(id=m.group(1) if m else None, url=None if m else url, output=out + '/', quiet=False, fuzzy=True)


def plain(url, out):
    import requests
    if 'dropbox.com' in url:
        url = re.sub(r'dl=0', 'dl=1', url) + ('' if 'dl=' in url else ('&' if '?' in url else '?') + 'dl=1')
    r = requests.get(url, stream=True, timeout=600, allow_redirects=True); r.raise_for_status()
    m = re.search(r'filename="?([^";]+)', r.headers.get('content-disposition', ''))
    fn = m.group(1) if m else (url.split('?')[0].rstrip('/').split('/')[-1] or 'file.mp4')
    with open(os.path.join(out, fn), 'wb') as f:
        for ch in r.iter_content(1 << 20): f.write(ch)


def main():
    kind, urls = sys.argv[1], sys.argv[2:]
    out = os.path.join(PP_HOME, kind); os.makedirs(out, exist_ok=True)
    before = set(glob.glob(out + '/**/*', recursive=True))
    for u in urls:
        (drive if 'drive.google.com' in u else plain)(u, out)
    new = sorted(set(glob.glob(out + '/**/*', recursive=True)) - before)
    for f in new:
        if os.path.isfile(f):
            sz = os.path.getsize(f)
            bad = sz < 200_000 and f.lower().endswith(VID)
            print(('!! ЖАБЫҚ/HTML? ' if bad else '') + os.path.relpath(f, PP_HOME), f'{sz // 1024} KB')
    if not new:
        print('!! ештеңе жүктелмеді — сілтеме «Anyone with the link» ме?')


if __name__ == '__main__':
    main()
