"""Кідіріс пен ыңылдауды қию -> keep.json (сақталатын аудио аралықтары).

python3 cuts.py JOB [--start 10.3] [--end 70.9] [--min-pause 0.2] [--drop 19.6-20.4 25.1-25.3]

- Сөйлеу бар жер Whisper сөздерінен алынады; «ыы/эээ/ммм» сияқты ыңылдау сөздері алынып тасталады.
- Әр аралық энергия бойынша тазартылады: басы/соңы тыныштықтан кесіледі, ішіндегі ≥ min-pause
  тыныштық қиылады (90–130 мс «п/т/к» жабылуы қалады, сондықтан сөз бұзылмайды).
- --drop: қайта бастаған/қате дубль сияқты қолмен алынатын аралықтар (аудио секунды).
"""
import argparse, json, re
import numpy as np
import soundfile as sf
from paths import job_dir

FILLER = re.compile(r'^(ы+|э+|м+|а+|ее+|эм+|мм+|хм+|uh+|um+|hmm+)[.,!?…]*$', re.I)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('job'); ap.add_argument('--start', type=float); ap.add_argument('--end', type=float)
    ap.add_argument('--min-pause', type=float, default=.2); ap.add_argument('--drop', nargs='*', default=[])
    a = ap.parse_args()
    J = job_dir(a.job)
    words = [w for w in json.load(open(f'{J}/words.json'))['words'] if not FILLER.match(w['w'].strip())]
    drops = [tuple(map(float, d.split('-'))) for d in a.drop]
    words = [w for w in words if not any(x <= (w['s'] + w['e']) / 2 <= y for x, y in drops)]
    if a.start is not None:
        words = [w for w in words if w['e'] > a.start]
    if a.end is not None:
        words = [w for w in words if w['s'] < a.end]
    y, sr = sf.read(f'{J}/voice.wav', dtype='float32')
    if y.ndim > 1:
        y = y.mean(1)
    hop = sr // 100
    n = len(y) // hop
    rms = np.sqrt(np.convolve(y[:n * hop] ** 2, np.ones(hop * 3) / (hop * 3), 'same')[::hop][:n] + 1e-12)
    db = 20 * np.log10(rms + 1e-7)
    speech = np.concatenate([db[int(w['s'] * 100):int(w['e'] * 100) + 1] for w in words]) if words else db
    ref = np.percentile(speech, 90)
    th_in, th_edge = ref - 30, ref - 34   # ішкі кідіріс / шет шегі (сөйлеу деңгейіне қатысты)

    # 1) сөздерден өрескел аралықтар (0,5 с-тан ұзын үзіліс — бөлек аралық)
    rough = []
    for w in words:
        s, e = w['s'] - .12, w['e'] + .15
        if rough and s - rough[-1][1] < .5:
            rough[-1][1] = max(rough[-1][1], e)
        else:
            rough.append([s, e])
    for x, y2 in drops:  # drop шегі аралықты міндетті түрде бөледі
        nr = []
        for s, e in rough:
            if x < e and y2 > s:
                if s < x: nr.append([s, x])
                if y2 < e: nr.append([y2, e])
            else:
                nr.append([s, e])
        rough = nr
    if a.start is not None:
        rough = [[max(s, a.start), e] for s, e in rough if e > a.start]
    if a.end is not None:
        rough = [[s, min(e, a.end)] for s, e in rough if s < a.end]

    # 2) энергиямен тазарту
    keep = []
    mp = int(round(a.min_pause * 100))
    for s, e in rough:
        i, j = max(int(s * 100), 0), min(int(e * 100), n - 1)
        while i < j and db[i] < th_edge:
            i += 1
        while j > i and db[j] < th_edge:
            j -= 1
        st, k = i, i
        while k < j:
            if db[k] < th_in:
                g = k
                while k < j and db[k] < th_in:
                    k += 1
                if k - g >= mp:
                    keep.append([round(max(st / 100 - .03, 0), 3), round(g / 100 + .05, 3)])
                    st = k
            else:
                k += 1
        if j > st:
            keep.append([round(st / 100 - .03, 3), round(j / 100 + .06, 3)])
    keep = [k for k in keep if k[1] - k[0] > .12]
    json.dump(keep, open(f'{J}/keep.json', 'w'))
    tot = sum(b - a_ for a_, b in keep)
    print(f'{len(keep)} аралық, {tot:.1f} с сақталды (бастапқы {rough[-1][1] - rough[0][0]:.1f} с) -> keep.json')


if __name__ == '__main__':
    main()
