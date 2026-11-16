"""B-roll: сапасын тексеру, кадр таңдау, кесу.

python3 broll.py check FILE...              # толық экранға / жарты сплитке жарамдылығы
python3 broll.py sheet FILE [--step 1.5]    # НАҚТЫ уақыт белгісімен кадр парағы -> check/
python3 broll.py cut FILE START NAME [--dur 5]   # 4K-ны сақтап кесу -> broll/cut/NAME.mp4

Ереже: тік 1080x1920 рилсте толық экран үшін көлденең дереккөздің биіктігі ≥ 2160 (4K) не тік ≥ 1920 болуы
керек. Көлденең 1080p-дан тік кадр қиғанда нақты ені ~608 px қалады да, 1,8–2,5 есе созылып, пиксель
көрінеді. 1080/1440p көлденең клипті тек жарты экран сплитке (stack) қой.
Кілтфрейм тәсілімен (skip_frame) жасалған парақтың уақыты дәл емес — кадрды осы `sheet` арқылы таңда.
"""
import argparse, os, subprocess
import numpy as np
import cv2
from paths import FF, HOME, probe, run


def verdict(w, h, zoom=1.2):
    """(толық экранда созылу, жарты сплитте созылу)."""
    full = max(1080 / w, 1920 / h) * zoom
    half = max(1080 / w, 960 / h) * zoom
    return full, half


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd'); ap.add_argument('args', nargs='+')
    ap.add_argument('--step', type=float, default=1.5); ap.add_argument('--dur', type=float, default=5)
    a = ap.parse_args()
    if a.cmd == 'check':
        for f in a.args:
            w, h, fps, dur, _ = probe(f)
            full, half = verdict(w, h)
            tag = 'толық экран OK' if full <= 1.1 else ('тек сплит' if half <= 1.15 else 'ЖАРАМАЙДЫ (пиксель)')
            print(f'{os.path.basename(f):32s} {w}x{h} {fps:.0f}fps {dur:5.1f}с | созылу: толық x{full:.2f}, сплит x{half:.2f} -> {tag}')
    elif a.cmd == 'sheet':
        f = a.args[0]
        w, h, fps, dur, _ = probe(f)
        cells = []
        t = 0.
        while t < dur and len(cells) < 64:
            out = subprocess.run([FF, '-v', 'error', '-ss', f'{t:.2f}', '-i', f, '-frames:v', '1', '-vf', 'scale=240:-2,format=bgr24',
                                  '-f', 'rawvideo', '-'], capture_output=True).stdout
            hh = len(out) // (240 * 3)
            if hh:
                c = np.frombuffer(out, np.uint8)[:240 * hh * 3].reshape(hh, 240, 3).copy()
                cv2.putText(c, f'{t:.1f}', (3, 16), 0, .5, (0, 255, 255), 1, cv2.LINE_AA)
                cells.append(c)
            t += a.step
        hh = cells[0].shape[0]
        cells = [cv2.resize(c, (240, hh)) for c in cells]
        C = 8
        cells += [np.zeros_like(cells[0])] * ((C - len(cells) % C) % C)
        os.makedirs(f'{HOME}/broll/check', exist_ok=True)
        p = f'{HOME}/broll/check/{os.path.splitext(os.path.basename(f))[0]}.jpg'
        cv2.imwrite(p, np.vstack([np.hstack(cells[i:i + C]) for i in range(0, len(cells), C)]))
        print(p)
    elif a.cmd == 'cut':
        f, start, name = a.args[0], float(a.args[1]), a.args[2]
        os.makedirs(f'{HOME}/broll/cut', exist_ok=True)
        out = f'{HOME}/broll/cut/{name}.mp4'
        run([FF, '-v', 'error', '-y', '-ss', str(start), '-t', str(a.dur), '-i', f, '-an', '-vf', 'format=yuv420p',
             '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '14', '-g', '24', out])
        print(out)


if __name__ == '__main__':
    main()
