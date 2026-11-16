"""Ортақ жолдар. Kit кез келген жерде жатады; жұмыс папкасы ER_HOME (env.sh орнатады)."""
import os, shutil, subprocess

K = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
E = os.path.join(K, 'engine')
FONTS = os.path.join(K, 'fonts')
LUTS = os.path.join(K, 'luts')
MODEL = os.path.join(K, 'models', 'selfie_multiclass.tflite')

GROT = os.path.join(FONTS, 'InterTight-Bold.ttf')
GROTX = os.path.join(FONTS, 'InterTight-ExtraBold.ttf')
SERB = os.path.join(FONTS, 'PlayfairDisplay-BoldItalic.ttf')
SERI = os.path.join(FONTS, 'PlayfairDisplay-Italic.ttf')


def _home():
    if os.environ.get('ER_HOME'):
        return os.environ['ER_HOME']
    try:
        r = subprocess.run(['git', 'rev-parse', '--show-toplevel'], capture_output=True, text=True, check=True).stdout.strip()
        return K if os.path.realpath(r) == os.path.realpath(K) else os.path.join(r, 'editorial')
    except Exception:
        return K


HOME = _home()
FF = shutil.which('ffmpeg') or 'ffmpeg'
FP = shutil.which('ffprobe') or 'ffprobe'


def job_dir(name):
    return os.path.join(HOME, 'projects', name)


def run(cmd, **kw):
    return subprocess.run(cmd, check=True, **kw)


def probe(path):
    """(w, h, fps, duration, rotation) — бұрылыс ескеріліп, көрсетілетін өлшем қайтады."""
    import json
    out = subprocess.run([FP, '-v', 'error', '-select_streams', 'v:0', '-show_entries',
                          'stream=width,height,r_frame_rate:stream_side_data=rotation:format=duration', '-of', 'json', path],
                         capture_output=True, text=True).stdout
    d = json.loads(out)
    s = d['streams'][0]
    rot = 0
    for sd in s.get('side_data_list', []) or []:
        rot = int(sd.get('rotation', 0) or 0)
    w, h = s['width'], s['height']
    if abs(rot) in (90, 270):
        w, h = h, w
    n, dd = s['r_frame_rate'].split('/')
    return w, h, float(n) / float(dd), float(d['format']['duration']), rot
