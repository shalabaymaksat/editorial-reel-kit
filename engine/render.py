"""Editorial reel рендері: plan.json + keep.json + proxy.mp4 -> projects/JOB/render.mp4 (дыбыссыз).

python3 render.py JOB info                 # тайм-лайн, сегменттер, бас төбесінің y-і
python3 render.py JOB frame 12.3 20.5      # тексеру кадрлары (АУДИО секунды) -> check/f_12.3.jpg
python3 render.py JOB sheet [step]         # контакт-парақ -> check/sheet_N.jpg
python3 render.py JOB video                # толық рендер

Жоспардағы барлық уақыт — таза аудио секунды (stt.py words.json-дағыдай).
"""
import json, os, subprocess, sys
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from paths import FF, GROT, GROTX, SERB, SERI, MODEL, HOME, job_dir

W, H = 1080, 1920
COLORS = dict(white=(255, 255, 255), mint=(159, 255, 26), blue=(242, 32, 4), ink_blue=(211, 41, 20),
              pill=(217, 76, 37), red=(15, 0, 151), paper=(251, 251, 251), ink=(18, 18, 18), black=(0, 0, 0))
FONTS = dict(grot=GROT, grotx=GROTX, serif=SERB, serif_light=SERI)

JOB = sys.argv[1]
J = job_dir(JOB)
META = json.load(open(f'{J}/meta.json'))
PLAN = json.load(open(f'{J}/plan.json'))
KEEP = [tuple(k) for k in json.load(open(f'{J}/keep.json'))]
FPS = META['fps']
LAG = META.get('lag', 0.0)
FACE = META.get('face', dict(cx=.5, cy=.42, top=.3, chin=.55))
ZOOM_MODE = PLAN.get('zoom', 'cut')
ZMAX = PLAN.get('zoom_max', 1.2)
DELAY = PLAN.get('word_delay', .1)
SHADE = PLAN.get('shade', .18)
SUB_Y_HEAD = PLAN.get('sub_y', int(min(max((FACE['chin'] * H) + 110, 1150), 1450)))
SUB_Y_CLIP = PLAN.get('sub_y_clip', 1120)


def col(c):
    return COLORS[c] if isinstance(c, str) else tuple(c)


def smooth(x):
    x = np.clip(x, 0, 1)
    return x * x * (3 - 2 * x)


# ---------- тайм-лайн ----------
frames, ranges, rid = [], [], []
_st = 0
for _r, (a, b) in enumerate(KEEP):
    fa, n = round(a * FPS), round((b - a) * FPS)
    frames += [(fa + k) / FPS for k in range(n)]
    rid += [_r] * n
    ranges.append((a, n / FPS, _st / FPS))
    _st += n
N = len(frames)


def t2o(at):
    """аудио уақыты -> шығыс уақыты (қиылған жерге түссе, келесі аралықтың басына)."""
    for a, d, s in ranges:
        if at < a + d:
            return s + max(at - a, 0)
    return ranges[-1][2] + ranges[-1][1]


SC = sorted(PLAN['scenes'], key=lambda s: s['s'])
for s in SC:  # кесу шекарасына жақын сахна басын аралық басына тарту
    near = [r[0] for r in KEEP if abs(r[0] - s['s']) < .2]
    if near:
        s['s'] = min(near)
ST = np.array([s['s'] for s in SC])


def scene_of(at):
    return max(int(np.searchsorted(ST, at + .5 / FPS, side='right')) - 1, 0)


SEG = []
_prev = None
for i in range(N):
    key = (rid[i], scene_of(frames[i]))
    if key != _prev:
        SEG.append([i, i + 1, key[1]])
        _prev = key
    else:
        SEG[-1][1] = i + 1
SCSTART = {}
for i in range(N):
    SCSTART.setdefault(scene_of(frames[i]), i)

# Зум: cut — сегмент сайын 1,0 ↔ ZMAX таза кесумен; smooth — сегмент ішінде плавный 1,0 ↔ ZMAX.
ZOOM = np.ones(N)
_head_i, _zc, _dir = 0, ZMAX, -1
for a, b, sc in SEG:
    kind = SC[sc]['type']
    if kind != 'head':
        ZOOM[a:b] = SC[sc].get('zoom', 1.0)
        continue
    if ZOOM_MODE == 'cut':
        ZOOM[a:b] = 1.0 if _head_i % 2 == 0 else ZMAX
    elif ZOOM_MODE == 'smooth':
        dur = (b - a) / FPS
        z1 = float(np.clip(_zc + _dir * min(ZMAX - 1, (ZMAX - 1) * dur / .9), 1.0, ZMAX))
        u = np.arange(b - a) / max(b - a - 1, 1)
        ZOOM[a:b] = _zc + (z1 - _zc) * (.5 * u + .5 * smooth(u))
        _zc = z1
        if z1 in (1.0, ZMAX):
            _dir = 1 if z1 == 1.0 else -1
    _head_i += 1

# ---------- субтитр ----------
WORDS = [(t2o(w['at']) + DELAY, w['t'], w.get('style', ''), scene_of(max(w['at'], ST[scene_of(w['at'])])))
         for w in sorted(PLAN.get('words', []), key=lambda w: w['at'])]
WTS = np.array([w[0] for w in WORDS]) if WORDS else np.array([1e9])

# ---------- мәтін ----------
_fonts, _txt = {}, {}


def font(p, s):
    return _fonts.setdefault((p, s), ImageFont.truetype(p, s))


def text_alpha(s, path, size):
    """Әріп альфасы 1,5x суперсэмплмен; гротескте −2,2% трекинг."""
    key = (s, path, size)
    if key in _txt:
        return _txt[key]
    ss = 1.5
    f = font(path, int(size * ss))
    track = (-.022 if 'Inter' in path else 0) * size * ss
    xs, x = [], 0.
    for i, c in enumerate(s):
        xs.append(x)
        nxt = s[i + 1] if i + 1 < len(s) else ''
        x += (f.getlength(c + nxt) - f.getlength(nxt) if nxt else f.getlength(c)) + track
    pad = int(size * .5)
    asc, desc = f.getmetrics()
    im = Image.new('L', (int(x + 2 * pad), asc + desc + 2 * pad), 0)
    d = ImageDraw.Draw(im)
    for c, px in zip(s, xs):
        d.text((pad + px, pad), c, fill=255, font=f)
    a = np.asarray(im, np.float32) / 255
    ys, xs2 = np.where(a > .02)
    if len(ys):
        a = a[max(ys.min() - 4, 0):ys.max() + 5, max(xs2.min() - 4, 0):xs2.max() + 5]
    _txt[key] = a
    return a


def fit_size(s, path, size, maxw=1000):
    return int(size * min(1, maxw / (text_alpha(s, path, size).shape[1] / 1.5)))


def blit(fr, a, cx, cy, color, alpha=1.0, scale=1.0, shadow=0.):
    sc = scale / 1.5
    w, h = max(int(a.shape[1] * sc), 1), max(int(a.shape[0] * sc), 1)
    b = cv2.resize(a, (w, h), interpolation=cv2.INTER_AREA if sc < 1 else cv2.INTER_CUBIC)
    pad = 80 if shadow else 0
    x0, y0 = int(cx - w / 2) - pad, int(cy - h / 2) - pad
    if pad:
        b = cv2.copyMakeBorder(b, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=0)
    x1, y1 = x0 + b.shape[1], y0 + b.shape[0]
    cx0, cy0, cx1, cy1 = max(x0, 0), max(y0, 0), min(x1, W), min(y1, H)
    if cx0 >= cx1 or cy0 >= cy1:
        return
    b = b[cy0 - y0:cy1 - y0, cx0 - x0:cx1 - x0]
    roi = fr[cy0:cy1, cx0:cx1].astype(np.float32)
    if shadow:
        sh = np.clip(cv2.GaussianBlur(b, (0, 0), 30) * .9 + cv2.GaussianBlur(b, (0, 0), 12) * .8
                     + cv2.GaussianBlur(b, (0, 0), 3) * .45, 0, 1) * shadow
        roi *= (1 - sh)[..., None]
    A = (b * alpha)[..., None]
    roi = roi * (1 - A) + np.array(color, np.float32) * A
    fr[cy0:cy1, cx0:cx1] = roi.astype(np.uint8)


def ignite(fr, cx, cy, tw, th, color, k):
    """Сөз 2 кадр бойы артындағы фон реңкін алып шығады, сосын өз түсіне өтеді."""
    if k >= 2:
        return color, 1.0
    if color == COLORS['mint']:
        return tuple(int(c * (.45 if k == 0 else .8)) for c in color), (.55 if k == 0 else .9)
    x0, x1 = max(int(cx - tw / 2), 0), min(int(cx + tw / 2), W)
    y0, y1 = max(int(cy - th / 2), 0), min(int(cy + th / 2), H)
    m = fr[y0:y1, x0:x1].reshape(-1, 3).mean(0).astype(np.uint8)
    hsv = cv2.cvtColor(m[None, None], cv2.COLOR_BGR2HSV)[0, 0].astype(int)
    if hsv[1] < 25:
        return color, (.45 if k == 0 else .8)
    hsv[1], hsv[2] = max(hsv[1], 190), 225
    tint = cv2.cvtColor(np.uint8(hsv)[None, None], cv2.COLOR_HSV2BGR)[0, 0].astype(float)
    return tuple(int(v) for v in (tint if k == 0 else (tint + np.array(color)) / 2)), (.92 if k == 0 else 1.0)


def settle(tau, s0=.14, T=1.8):
    return 1 + s0 * (1 - min(tau / T, 1)) ** 3


def layout_top(top):
    """y берілмесе: соңғы жол бастың төбесін ~35% жабады, алдыңғылары үстіне жиналады."""
    out, y = [], None
    head_top = FACE['top'] * H
    items = []
    for e in top:
        path = FONTS[e.get('font', 'grotx')]
        size = fit_size(e['t'], path, e.get('size', 120))
        items.append((e, path, size))
    for e, path, size in reversed(items):
        h = text_alpha(e['t'], path, size).shape[0] / 1.5
        if 'y' in e:
            y = e['y']
        elif y is None:
            y = head_top + h * .15
        else:
            y = y - (out[-1][3] * .5 + h * .5) - 6
        out.append((e, path, size, h, y))
    return list(reversed(out))


_layout = {}


def draw_titles(fr, sc, t):
    if sc not in _layout:
        _layout[sc] = layout_top(SC[sc].get('top', []))
    for e, path, size, h, y in _layout[sc]:
        on = t2o(e['at']) + DELAY - .05
        if t < on:
            continue
        a = text_alpha(e['t'], path, size)
        c0 = col(e.get('color', 'white'))
        c, al = ignite(fr, 540, y, a.shape[1] / 1.5, h, c0, int((t - on) * FPS + .001))
        blit(fr, a, 540, y, c, alpha=al, scale=settle(t - on))


def draw_sub(fr, t, sc):
    j = int(np.searchsorted(WTS, t, side='right')) - 1
    if j < 0 or j >= len(WORDS) or WORDS[j][3] != sc:
        return
    _, s, st, _ = WORDS[j]
    y = SUB_Y_HEAD if SC[sc]['type'] == 'head' else SUB_Y_CLIP
    if st == 'm':
        blit(fr, text_alpha(s, SERB, fit_size(s, SERB, 150)), 540, y, COLORS['mint'], shadow=.95)
    else:
        blit(fr, text_alpha(s, GROT, fit_size(s, GROT, 96)), 540, y, COLORS['white'], shadow=.95)


# ---------- адам маскасы (тек бас артындағы тақырыпқа) ----------
_seg = None


def matte(fr):
    """Шаш + бет + тері (киімсіз): тақырып бастың артына кетеді."""
    global _seg
    import mediapipe as mp
    from mediapipe.tasks.python import vision, BaseOptions
    if _seg is None:
        _seg = vision.ImageSegmenter.create_from_options(vision.ImageSegmenterOptions(
            base_options=BaseOptions(model_asset_path=MODEL), output_confidence_masks=True))
    y0, y1 = 0, int(H * .75)
    crop = np.ascontiguousarray(fr[y0:y1])
    r = _seg.segment(mp.Image(image_format=mp.ImageFormat.SRGB, data=cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)))
    ms = [m.numpy_view().squeeze() for m in r.confidence_masks]
    p = (ms[1] + ms[2] + ms[3]).astype(np.float32)
    g = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255
    gs, ps = cv2.resize(g, None, fx=.5, fy=.5, interpolation=cv2.INTER_AREA), cv2.resize(p, None, fx=.5, fy=.5, interpolation=cv2.INTER_AREA)
    k = (21, 21)
    mg, mp_ = cv2.blur(gs, k), cv2.blur(ps, k)
    aa = (cv2.blur(gs * ps, k) - mg * mp_) / (cv2.blur(gs * gs, k) - mg * mg + 1e-3)
    q = cv2.blur(aa, k) * gs + cv2.blur(mp_ - aa * mg, k)
    q = smooth((cv2.resize(q, (crop.shape[1], crop.shape[0])) - .35) / .4).astype(np.float32)
    out = np.zeros(fr.shape[:2], np.float32)
    out[y0:y1] = q
    return out


# ---------- видео көздері ----------
class Clip:
    def __init__(self, p):
        self.c, self.pos, self.last = cv2.VideoCapture(p), -1, None
        if not self.c.isOpened():
            sys.exit(f'!! ашылмады: {p}')
        self.fps = self.c.get(cv2.CAP_PROP_FPS) or FPS
        self.n = int(self.c.get(cv2.CAP_PROP_FRAME_COUNT))

    def get(self, idx):
        idx = min(max(idx, 0), max(self.n - 1, 0))
        if idx == self.pos and self.last is not None:
            return self.last
        if idx != self.pos + 1:
            self.c.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ok, f = self.c.read()
        if ok:
            self.last = f
        self.pos = idx
        return self.last


_clips = {}


def clip(path):
    p = path if os.path.isabs(path) else os.path.join(HOME, path)
    if p not in _clips:
        _clips[p] = Clip(p)
    return _clips[p]


def head_frame(at, z):
    c = clip(f'{J}/proxy.mp4')
    f = c.get(int(round((at + LAG) * c.fps)))
    s = W / f.shape[1] * z
    px, py = FACE['cx'] * W, FACE['cy'] * H
    return cv2.warpAffine(f, np.float32([[s, 0, px - px * z], [0, s, py - py * z]]), (W, H), flags=cv2.INTER_CUBIC)


def fit_part(q, tau, z, tw, th):
    """Панельді жабу; 4K бір рет INTER_AREA-мен кішірейтіледі (алиасинг жоқ)."""
    c = clip(q['clip'])
    f = c.get(int((q.get('at', 0) + tau) * c.fps))
    h, w = f.shape[:2]
    s = max(tw / w, th / h) * z * q.get('base', 1.0)
    if s < .8:
        k = s / .95
        f = cv2.resize(f, None, fx=k, fy=k, interpolation=cv2.INTER_AREA)
        h, w = f.shape[:2]
        s /= k
    cw, ch = tw / s, th / s
    x0 = np.clip(q.get('cx', .5) * w - cw / 2, 0, w - cw)
    y0 = np.clip(q.get('cy', .5) * h - ch / 2, 0, h - ch)
    return cv2.warpAffine(f, np.float32([[s, 0, -x0 * s], [0, s, -y0 * s]]), (tw, th), flags=cv2.INTER_CUBIC)


# ---------- сахналар ----------
def paper():
    return np.full((H, W, 3), COLORS['paper'], np.uint8)


def decay(tau, s0, half=.4):
    return 1 + (s0 - 1) * .5 ** (tau / half)


_gx, _gy = np.meshgrid(np.arange(W, dtype=np.float32), np.arange(H, dtype=np.float32))


def pincushion(fr, k, cy=960):
    if k < .002:
        return fr
    dx, dy = (_gx - 540) / 540, (_gy - cy) / 540
    r2 = dx * dx + dy * dy
    return cv2.remap(fr, 540 + dx * 540 * (1 - k * r2), cy + dy * 540 * (1 - k * r2), cv2.INTER_LINEAR,
                     borderMode=cv2.BORDER_REPLICATE)


def rrect(w, h, r, fill, line=None, lw=2):
    ss = 3
    im = Image.new('RGBA', (w * ss, h * ss), (0, 0, 0, 0))
    ImageDraw.Draw(im).rounded_rectangle((lw, lw, w * ss - 1 - lw, h * ss - 1 - lw), r * ss, fill=fill,
                                         outline=line, width=lw * ss)
    return im


def paste_rgba(fr, arr, cx, cy, scale=1.0, alpha=1.0):
    """arr — 2x өлшемде сызылған RGBA."""
    w, h = int(arr.shape[1] * scale / 2), int(arr.shape[0] * scale / 2)
    b = cv2.resize(arr, (w, h), interpolation=cv2.INTER_AREA)
    x0, y0 = int(cx - w / 2), int(cy - h / 2)
    cx0, cy0, cx1, cy1 = max(x0, 0), max(y0, 0), min(x0 + w, W), min(y0 + h, H)
    b = b[cy0 - y0:cy1 - y0, cx0 - x0:cx1 - x0]
    A = b[..., 3:] / 255 * alpha
    roi = fr[cy0:cy1, cx0:cx1].astype(np.float32)
    fr[cy0:cy1, cx0:cx1] = (roi * (1 - A) + b[..., 2::-1] * A).astype(np.uint8)


_cache = {}


def card(title, rows, ticks):
    key = ('card', title, tuple(rows), ticks)
    if key in _cache:
        return _cache[key]
    w, h, ss = 800, 220 + 104 * len(rows), 3
    im = rrect(w, h, 46, (255, 255, 255, 255), (205, 205, 205, 255), 2)
    d = ImageDraw.Draw(im)
    tf = font(GROTX, 66 * ss)
    tsz = min(66, int(66 * (w - 120) / (d.textlength(title, font=tf) / ss)))
    d.text((60 * ss, 56 * ss), title, font=font(GROTX, tsz * ss), fill=(18, 18, 18, 255))
    for i, s in enumerate(rows):
        y = (196 + i * 104) * ss
        box = (62 * ss, y, 118 * ss, y + 56 * ss)
        if i < ticks:
            d.rounded_rectangle(box, 12 * ss, fill=(37, 99, 235, 255))
            d.line([(74 * ss, y + 29 * ss), (86 * ss, y + 41 * ss), (106 * ss, y + 16 * ss)], fill=(255, 255, 255, 255),
                   width=7 * ss, joint='curve')
        else:
            d.rounded_rectangle(box, 12 * ss, outline=(70, 70, 70, 255), width=3 * ss)
        d.text((146 * ss, y - 4 * ss), s, font=font(GROT, 54 * ss), fill=(18, 18, 18, 255))
    arr = np.asarray(im.resize((w * 2, h * 2), Image.LANCZOS), np.float32)
    _cache[key] = arr
    return arr


def star(d, cx, cy, r, fill):
    pts = []
    for i in range(10):
        a = -np.pi / 2 + i * np.pi / 5
        rr = r if i % 2 == 0 else r * .45
        pts.append((cx + rr * np.cos(a), cy + rr * np.sin(a)))
    d.polygon(pts, fill=fill)


def pill(label, stars):
    key = ('pill', label, stars)
    if key in _cache:
        return _cache[key]
    w, h, ss = 860, 124, 3
    im = rrect(w, h, 34, (37, 76, 217, 255))
    d = ImageDraw.Draw(im)
    d.text((46 * ss, 24 * ss), label, font=font(GROTX, 58 * ss), fill=(255, 255, 255, 255))
    if stars is not None:
        for i in range(5):
            star(d, (w - 260 + i * 48) * ss, h / 2 * ss, 22 * ss, (255, 255, 255, 255) if i < stars else (20, 45, 140, 255))
    arr = np.asarray(im.resize((w * 2, h * 2), Image.LANCZOS), np.float32)
    _cache[key] = arr
    return arr


def caption_at(caps, t):
    s = [c for at, c in caps if t >= t2o(at) + DELAY - .04]
    return s[-1] if s else None


def stage_push(p, t, t0):
    """Ақ фон: үлкен көк курсив, сосын келесі сөз оңнан итеріп кіреді."""
    fr = paper()
    tau = t - t0
    a1 = text_alpha(p['a'], SERB, fit_size(p['a'], SERB, 170, 960))
    dx = 0
    if p.get('b'):
        push = t2o(p['at']) + DELAY - t0
        dx = 1100 * smooth((tau - push) / .34)
        a2 = text_alpha(p['b'], SERB, fit_size(p['b'], SERB, 130, 960))
        if tau > push:
            blit(fr, a2, 540 + 1100 - dx, 960, COLORS['blue'], scale=decay(max(tau - push - .2, 0), 1.18, .3))
    if dx < 1100:
        blit(fr, a1, 540 - dx, 960, COLORS['blue'], scale=decay(tau, 1.45, .28))
    return fr


def stage_check(p, t, t0):
    fr = paper()
    tau = t - t0
    ticks = sum(t >= t2o(x) + DELAY - .04 for x in p['ticks'])
    paste_rgba(fr, card(p['title'], p['rows'], ticks), 540, 960, scale=decay(tau, 1.32, .38))
    return pincushion(fr, .13 * max(1 - tau / .55, 0) ** 2)


def stage_compare(p, t, t0):
    fr = paper()
    tau = t - t0
    gs = decay(tau, 1.28, .5)
    cap = caption_at(p.get('caps', []), t)
    rows = p['rows']
    top = 960 - (len(rows) - 1) * 75 * gs
    if cap:
        blit(fr, text_alpha(cap, SERI, fit_size(cap, SERI, 92)), 540, top - 140 * gs, COLORS['ink_blue'], scale=gs)
    for i, r in enumerate(rows):
        on = t2o(r['at']) + DELAY - .05
        if t >= on:
            k = (t - on) * FPS
            paste_rgba(fr, pill(r['t'], r.get('stars')), 540, top + i * 150 * gs, scale=gs * (1 + .1 * max(1 - k / 4, 0)),
                       alpha=min(1, .35 + k * .3))
    return fr


def stage_number(p, t, t0):
    fr = np.full((H, W, 3), col(p.get('bg', 'red')), np.uint8)
    tau = t - t0
    blit(fr, text_alpha(p.get('n', '1'), SERI, 900), 540, 960, COLORS['white'], alpha=.58, scale=1 + 1.6 * .5 ** (tau / .3))
    cap = caption_at(p.get('caps', []), t)
    if cap:
        blit(fr, text_alpha(cap, SERI, fit_size(cap, SERI, 128)), 540, 960, COLORS['white'])
    return fr


STAGE = dict(push=stage_push, check=stage_check, compare=stage_compare, number=stage_number)
SHADE_V = (1 - SHADE * smooth((np.arange(H, dtype=np.float32) - (SUB_Y_HEAD - 265)) / 280))[:, None, None]


def to_bw(fr):
    g = cv2.cvtColor(fr, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255
    return cv2.cvtColor((np.clip(g ** 1.15, 0, 1) * 255).astype(np.uint8), cv2.COLOR_GRAY2BGR)


def render(i):
    at, t = frames[i], i / FPS
    sc = scene_of(at)
    p = SC[sc]
    t0 = SCSTART[sc] / FPS
    kind = p['type']
    if kind in STAGE:
        return STAGE[kind](p, t, t0)
    z = ZOOM[i]
    if kind == 'clip':
        fr = fit_part(p, t - t0, z, W, H)
    elif kind == 'stack':
        fr = np.vstack([fit_part(q, t - t0, z, W, H // 2) for q in p['parts']])
    else:
        fr = head_frame(at, z)
    if p.get('bw'):
        fr = to_bw(fr)
    if kind == 'head':
        if SHADE:
            fr = (fr * SHADE_V).astype(np.uint8)
        if p.get('top'):
            m = matte(fr)[..., None]
            base = fr.copy()
            draw_titles(fr, sc, t)
            fr = (fr * (1 - m) + base * m).astype(np.uint8)
    elif p.get('top'):
        draw_titles(fr, sc, t)
    draw_sub(fr, t, sc)
    return fr


def video():
    out = f'{J}/render.mp4'
    num, den = (24000, 1001) if abs(FPS - 23.976) < .01 else ((30000, 1001) if abs(FPS - 29.97) < .01 else (round(FPS), 1))
    p = subprocess.Popen([FF, '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'bgr24', '-s', f'{W}x{H}', '-r', f'{num}/{den}',
                          '-i', '-', '-vf', 'scale=out_color_matrix=bt709:flags=accurate_rnd+full_chroma_int+lanczos,format=yuv420p',
                          '-c:v', 'libx264', '-preset', 'medium', '-crf', '16', '-colorspace', 'bt709', '-color_primaries', 'bt709',
                          '-color_trc', 'bt709', '-color_range', 'tv', out], stdin=subprocess.PIPE)
    for i in range(N):
        p.stdin.write(render(i).tobytes())
        if i % 120 == 0:
            print(f'{i}/{N}', flush=True)
    p.stdin.close()
    p.wait()
    json.dump(dict(duration=N / FPS, fps=FPS, ranges=ranges), open(f'{J}/timeline.json', 'w'))
    print('render.mp4', N / FPS, 'с')


if __name__ == '__main__':
    cmd = sys.argv[2] if len(sys.argv) > 2 else 'info'
    os.makedirs(f'{J}/check', exist_ok=True)
    if cmd == 'info':
        print(f'{N} кадр, {N / FPS:.2f} с, {len(KEEP)} аралық, зум={ZOOM_MODE}, бас төбесі y={FACE["top"] * H:.0f}, иек y={FACE["chin"] * H:.0f}, субтитр y={SUB_Y_HEAD}')
        for a, b, sc in SEG:
            print(f'  {frames[a]:7.2f}  {(b - a) / FPS:5.2f} с  {SC[sc]["type"]:8s} зум {ZOOM[a]:.2f}')
        json.dump(dict(duration=N / FPS, fps=FPS, ranges=ranges), open(f'{J}/timeline.json', 'w'))
    elif cmd == 'frame':
        for a in sys.argv[3:]:
            i = int(np.argmin(np.abs(np.array(frames) - float(a))))
            cv2.imwrite(f'{J}/check/f_{a}.jpg', render(i), [cv2.IMWRITE_JPEG_QUALITY, 90])
        print('check/f_*.jpg')
    elif cmd == 'sheet':
        step = int(sys.argv[3]) if len(sys.argv) > 3 else 12
        cells = [cv2.resize(render(i), (180, 320), interpolation=cv2.INTER_AREA) for i in range(0, N, step)]
        C = 14
        rows = [np.hstack(cells[j:j + C] + [np.zeros((320, 180, 3), np.uint8)] * (C - len(cells[j:j + C]))) for j in range(0, len(cells), C)]
        for k in range(0, len(rows), 3):
            cv2.imwrite(f'{J}/check/sheet_{k // 3}.jpg', np.vstack(rows[k:k + 3]), [cv2.IMWRITE_JPEG_QUALITY, 84])
        print(f'check/sheet_*.jpg ({len(cells)} кадр)')
    elif cmd == 'video':
        video()
