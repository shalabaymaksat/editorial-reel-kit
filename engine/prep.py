"""Дайындық.

python3 prep.py ingest VIDEO --job NAME [--audio clean.mp3] [--log auto|none|slog3]
    Әдепкі: қалыпты (log емес) видео. S-Log3 тек айқын сұр/күңгірт болса анықталады не --log slog3 деп беріледі.
    meta.json (камера, аудио, lag, log), voice.wav (48k), voice16k.wav (Whisper үшін)
    Бөлек жазылған таза аудио берілсе — камера дыбысымен waveform арқылы синхрон:
    видео уақыты = аудио уақыты + lag. Барлық жоспар уақыты — АУДИО секундымен.
python3 prep.py proxy JOB
    grade.cube жағылған 1440x2560 тік прокси (proxy.mp4) + бет орны (meta.json: face)
"""
import argparse, json, os, subprocess, sys
import numpy as np
import cv2
from paths import FF, MODEL, job_dir, probe, run

PW, PH = 1440, 2560


def pcm(path, sr, start=None, dur=None):
    cmd = [FF, '-v', 'error']
    if start is not None:
        cmd += ['-ss', str(start)]
    cmd += ['-i', path]
    if dur is not None:
        cmd += ['-t', str(dur)]
    cmd += ['-vn', '-ac', '1', '-ar', str(sr), '-f', 'f32le', '-']
    return np.frombuffer(subprocess.run(cmd, capture_output=True, check=True).stdout, np.float32)


def find_lag(camera, audio):
    """Таза аудиодан бірнеше 8 с терезені камера дыбысынан іздейді. lag = видео_t - аудио_t."""
    from scipy.signal import correlate
    sr = 8000
    c, a = pcm(camera, sr), pcm(audio, sr)
    lags = []
    for frac in (.2, .45, .7):
        s0 = int(len(a) * frac)
        seg = a[s0:s0 + 8 * sr]
        if len(seg) < 4 * sr:
            continue
        x = correlate(c, seg - seg.mean(), 'valid', method='fft')
        k = int(np.argmax(np.abs(x)))
        lags.append(k / sr - s0 / sr)
    lags = np.array(lags)
    spread = float(lags.max() - lags.min()) if len(lags) else 99
    return float(np.median(lags)), spread


def detect_log(video, dur):
    out = subprocess.run([FF, '-v', 'error', '-ss', str(dur / 2), '-i', video, '-frames:v', '1', '-vf', 'scale=320:-2,format=gray',
                          '-f', 'rawvideo', '-'], capture_output=True, check=True).stdout
    g = np.frombuffer(out, np.uint8) / 255.
    lo, hi = np.percentile(g, 1), np.percentile(g, 99)
    # Әдепкі — қалыпты видео. S-Log3 тек айқын болса: қара нүкте көтерілген және ақ 0,8-ге жетпейді.
    return 'slog3' if (lo > .09 and hi < .8 and hi - lo < .6) else 'none', round(float(lo), 3), round(float(hi), 3)


def ingest(a):
    J = job_dir(a.job)
    os.makedirs(f'{J}/check', exist_ok=True)
    w, h, fps, dur, rot = probe(a.video)
    log, lo, hi = (a.log, None, None) if a.log != 'auto' else detect_log(a.video, dur)
    meta = dict(camera=os.path.abspath(a.video), w=w, h=h, fps=fps, duration=dur, log=log, lag=0.0)
    src_audio = a.video
    if a.audio:
        lag, spread = find_lag(a.video, a.audio)
        meta.update(audio=os.path.abspath(a.audio), lag=round(lag, 4), lag_spread=round(spread, 4))
        src_audio = a.audio
        print(f'синхрон: видео = аудио {lag:+.4f} с (терезелер айырмасы {spread * 1000:.1f} мс)')
        if spread > .05:
            print('!! терезелер сәйкес емес: аудио басқа дубль болуы мүмкін — тексер')
    run([FF, '-v', 'error', '-y', '-i', src_audio, '-vn', '-ac', '1', '-ar', '48000', f'{J}/voice.wav'])
    run([FF, '-v', 'error', '-y', '-i', src_audio, '-vn', '-ac', '1', '-ar', '16000', f'{J}/voice16k.wav'])
    json.dump(meta, open(f'{J}/meta.json', 'w'), ensure_ascii=False, indent=1)
    print(f'{w}x{h} {fps:.3f} fps {dur:.1f} с | log: {log}' + (f' (жарықтық {lo}–{hi})' if lo is not None else ''))
    if log == 'slog3' and a.log == 'auto':
        print('!! видео S-Log3 сияқты (сұр, күңгірт). Дұрыс емес болса: --log none')
    print('келесі: stt.py, grade.py fit, prep.py proxy')


def head_box(frames):
    """MediaPipe multiclass: шаш+бет орталығы мен бас төбесі (нормаланған)."""
    import mediapipe as mp
    from mediapipe.tasks.python import vision, BaseOptions
    seg = vision.ImageSegmenter.create_from_options(vision.ImageSegmenterOptions(
        base_options=BaseOptions(model_asset_path=MODEL), output_confidence_masks=True))
    pts = []
    for f in frames:
        r = seg.segment(mp.Image(image_format=mp.ImageFormat.SRGB, data=cv2.cvtColor(f, cv2.COLOR_BGR2RGB)))
        m = [x.numpy_view().squeeze() for x in r.confidence_masks]
        head = (m[1] + m[3]) > .5
        ys, xs = np.nonzero(head)
        if len(xs) > head.size * .01:  # тек беті анық көрінетін кадр
            pts.append((xs.mean() / f.shape[1], ys.mean() / f.shape[0], np.percentile(ys, 2) / f.shape[0],
                        np.percentile(ys, 98) / f.shape[0]))
    if not pts:
        return dict(cx=.5, cy=.42, top=.3, chin=.55)
    p = np.median(np.array(pts), 0)
    if len(pts) < 3:
        print('!! бет аз кадрда табылды: meta.json face мәнін тексер')
    return dict(cx=round(p[0], 4), cy=round(p[1], 4), top=round(p[2], 4), chin=round(p[3], 4))


def grab(video, t, vf):
    w, h = 360, 640
    out = subprocess.run([FF, '-v', 'error', '-ss', str(t), '-i', video, '-frames:v', '1', '-vf', vf + f',scale={w}:{h},format=bgr24',
                          '-f', 'rawvideo', '-'], capture_output=True, check=True).stdout
    return np.frombuffer(out, np.uint8).reshape(h, w, 3)


def proxy(a):
    J = job_dir(a.job)
    meta = json.load(open(f'{J}/meta.json'))
    lut = f'{J}/grade.cube'
    if not os.path.exists(lut):
        sys.exit('!! grade.cube жоқ: алдымен grade.py fit JOB')
    w, h = meta['w'], meta['h']
    crop = ''
    if w / h > 9 / 16 + .01:
        # көлденең камера: бетке қарай 9:16 қию
        cw = int(h * 9 / 16) // 2 * 2
        full = []
        for k in (.25, .5, .75):
            out = subprocess.run([FF, '-v', 'error', '-ss', str(meta['duration'] * k), '-i', meta['camera'], '-frames:v', '1',
                                  '-vf', f'lut3d={lut},scale=640:-2,format=bgr24', '-f', 'rawvideo', '-'], capture_output=True).stdout
            hh = int(640 * h / w) // 2 * 2
            full.append(np.frombuffer(out, np.uint8)[:640 * hh * 3].reshape(hh, 640, 3))
        cx = head_box(full)['cx']
        x0 = int(np.clip(cx * w - cw / 2, 0, w - cw))
        crop = f'crop={cw}:{h}:{x0}:0,'
        meta['crop_x'] = x0
    run([FF, '-v', 'error', '-y', '-i', meta['camera'], '-an', '-sws_flags', 'lanczos+accurate_rnd+full_chroma_int',
         '-vf', f'lut3d={lut},{crop}scale={PW}:{PH}:flags=lanczos+accurate_rnd+full_chroma_int,format=yuv420p',
         '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '14', '-g', '24', f'{J}/proxy.mp4'])
    fr = [grab(f'{J}/proxy.mp4', meta['duration'] * k, 'null') for k in np.linspace(.05, .95, 15)]
    meta['face'] = head_box(fr)
    json.dump(meta, open(f'{J}/meta.json', 'w'), ensure_ascii=False, indent=1)
    print('proxy.mp4 дайын, бет:', meta['face'])


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd', choices=['ingest', 'proxy'])
    ap.add_argument('arg', help='ingest: VIDEO, proxy: JOB')
    ap.add_argument('--job'); ap.add_argument('--audio'); ap.add_argument('--log', default='auto', help='auto (әдепкі: қалыпты видео, тек айқын S-Log3 анықталады) | none | slog3')
    a = ap.parse_args()
    if a.cmd == 'ingest':
        a.video = a.arg
        if not a.job:
            sys.exit('--job керек')
        ingest(a)
    else:
        a.job = a.arg
        proxy(a)
