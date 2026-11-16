"""Дыбыс: дауыс (шумсыз, терең) + синтез SFX + музыка -> mix.wav, содан кейін ready/NAME.mp4.

python3 mix.py JOB [--music track.mp3] [--music-db -32] [--music-start 15] [--no-auto-sfx]

Дауыс: шум тазалау (afftdn) -> терең тембр EQ -> компрессор -> статикалық gain -14 LUFS -> лимитер.
(Динамикалық loudnorm қолданылмайды: ол кідірістегі шуды көтереді.)
SFX лицензиясыз синтезделеді: whoosh, hit, impact, riser, tick, pop. plan.json "sfx" тізімі +
сахналардан авто (--no-auto-sfx өшіреді).
"""
import argparse, json, os, subprocess
import numpy as np
import soundfile as sf
import pyloudnorm as pyln
from paths import FF, HOME, job_dir, run

SR = 48000
VOICE = ('afftdn=nr=14:nf=-48:tn=1,highpass=f=70,'
         'equalizer=f=95:t=o:w=0.9:g=6,equalizer=f=170:t=o:w=0.6:g=-2,equalizer=f=320:t=o:w=0.9:g=-3,'
         'equalizer=f=4200:t=o:w=0.6:g=-1.5,highshelf=f=7000:g=3,'
         'acompressor=threshold=-24dB:ratio=3:attack=6:release=90:makeup=4dB,deesser=i=0.35:m=0.5:f=0.45')


def load(path):
    r = subprocess.run([FF, '-v', 'error', '-i', path, '-f', 'f32le', '-ac', '2', '-ar', str(SR), '-'], capture_output=True, check=True)
    return np.frombuffer(r.stdout, np.float32).reshape(-1, 2).copy()


# ---------- синтез SFX ----------
rng = np.random.default_rng(7)


def _env(n, a, d):
    t = np.arange(n) / SR
    return np.minimum(t / max(a, 1e-4), 1) * np.exp(-np.maximum(t - a, 0) / d)


def _bandnoise(n, f0, f1, q=6):
    """Жиілігі f0->f1 жылжитын жолақты шу (FFT сүзгі)."""
    x = rng.normal(0, 1, n)
    out = np.zeros(n)
    blk = 1024
    for s in range(0, n, blk):
        seg = x[s:s + blk * 2]
        fc = f0 + (f1 - f0) * (s / n)
        F = np.fft.rfft(seg * np.hanning(len(seg)))
        fr = np.fft.rfftfreq(len(seg), 1 / SR)
        F *= np.exp(-((np.log2(fr + 1) - np.log2(fc)) ** 2) * q)
        y = np.fft.irfft(F, len(seg))
        out[s:s + len(y)] += y[:n - s]
    return out / (np.abs(out).max() + 1e-9)


def sfx(kind):
    """(сигнал, пик индексі)"""
    if kind == 'whoosh':
        n = int(.55 * SR)
        y = _bandnoise(n, 400, 5000, 3) * np.sin(np.linspace(0, np.pi, n)) ** 2
        return y, int(n * .5)
    if kind == 'hit':
        n = int(.5 * SR); t = np.arange(n) / SR
        y = np.sin(2 * np.pi * (90 * t + 140 * (1 - np.exp(-t / .03)) * .03)) * _env(n, .002, .12)
        y += .35 * _bandnoise(n, 3000, 2000, 2) * _env(n, .001, .02)
        return y, int(.004 * SR)
    if kind == 'impact':
        n = int(1.6 * SR); t = np.arange(n) / SR
        y = np.sin(2 * np.pi * (48 * t + 60 * (1 - np.exp(-t / .08)) * .08)) * _env(n, .004, .55)
        y += .4 * _bandnoise(n, 1200, 300, 2) * _env(n, .002, .25)
        return y, int(.01 * SR)
    if kind == 'riser':
        n = int(2.2 * SR); t = np.arange(n) / SR
        y = _bandnoise(n, 300, 6000, 2) * (t / t[-1]) ** 2.2
        y += .25 * np.sin(2 * np.pi * (200 * t + 300 * t ** 2 / t[-1])) * (t / t[-1]) ** 3
        return y, n - 1
    if kind == 'tick':
        n = int(.05 * SR); t = np.arange(n) / SR
        y = np.sin(2 * np.pi * 1900 * t) * np.exp(-t / .012)
        y[:40] += rng.normal(0, .6, 40)
        return y, 0
    if kind == 'pop':
        n = int(.09 * SR); t = np.arange(n) / SR
        return np.sin(2 * np.pi * (760 * t - 2000 * t * t)) * np.exp(-t / .025), 0
    raise ValueError(kind)


def auto_sfx(plan):
    out, scenes = [], sorted(plan['scenes'], key=lambda s: s['s'])
    for i, s in enumerate(scenes):
        k = s['type']
        if k in ('push', 'check', 'compare'):
            out.append(('whoosh', s['s'], -15))
        if k == 'push' and s.get('b'):
            out.append(('whoosh', s['at'], -15))
        if k == 'check':
            out += [('tick', x, -13) for x in s['ticks']]
        if k == 'compare':
            out += [('pop', r['at'], -13) for r in s['rows']]
        if k == 'number':
            out += [('whoosh', s['s'], -14), ('impact', s['s'] + .02, -14)]
        if s.get('bw') and not (i and scenes[i - 1].get('bw')):
            out.append(('impact', s['s'], -11))
        for e in s.get('top', []):
            if e.get('color') == 'mint':
                out.append(('hit', e['at'], -15))
    if len(scenes) > 1:  # хуктан кейінгі бірінші ауысу: райзер -> соққы
        out += [('riser', scenes[1]['s'], -24), ('impact', scenes[1]['s'], -12)]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('job'); ap.add_argument('--music'); ap.add_argument('--music-db', type=float, default=-32)
    ap.add_argument('--music-start', type=float, default=0); ap.add_argument('--no-auto-sfx', action='store_true')
    a = ap.parse_args()
    J = job_dir(a.job)
    plan = json.load(open(f'{J}/plan.json'))
    tl = json.load(open(f'{J}/timeline.json'))
    ranges = tl['ranges']
    L = int(tl['duration'] * SR)

    def t2o(at):
        for s0, d, o in ranges:
            if at < s0 + d:
                return o + max(at - s0, 0)
        return ranges[-1][2] + ranges[-1][1]

    # дауыс: алдымен шумды бүкіл жазбадан тазалап, сосын аралықтарды қиып жалғау
    fc = [f'[0:a]aresample={SR},aformat=channel_layouts=mono,{VOICE},asplit={len(ranges)}' + ''.join(f'[s{i}]' for i in range(len(ranges)))]
    lab = ''
    for i, (s0, d, _) in enumerate(ranges):
        fc.append(f'[s{i}]atrim={s0:.5f}:{s0 + d:.5f},asetpts=PTS-STARTPTS,afade=t=in:d=0.006,afade=t=out:st={max(d - .008, 0):.5f}:d=0.008[a{i}]')
        lab += f'[a{i}]'
    fc.append(f'{lab}concat=n={len(ranges)}:v=0:a=1[o]')
    run([FF, '-v', 'error', '-y', '-i', f'{J}/voice.wav', '-filter_complex', ';'.join(fc), '-map', '[o]', '-ac', '2', '-ar', str(SR),
         '-c:a', 'pcm_f32le', f'{J}/voice_edit.wav'])
    v = load(f'{J}/voice_edit.wav')[:L]
    v = np.vstack([v, np.zeros((max(L - len(v), 0), 2), np.float32)])
    meter = pyln.Meter(SR)
    v *= 10 ** ((-14 - meter.integrated_loudness(v)) / 20)
    mix = v.copy()

    music = a.music or (plan.get('music') or {}).get('file')
    if music:
        mp = music if os.path.isabs(music) else os.path.join(HOME, music)
        m = load(mp)[int(a.music_start * SR):]
        while len(m) < L:
            m = np.vstack([m, m])
        m = m[:L]
        m *= 10 ** (((plan.get('music') or {}).get('db', a.music_db) - meter.integrated_loudness(m)) / 20)
        env = np.abs(v).max(1)
        hop = SR // 100
        e = np.array([env[j:j + hop].max() for j in range(0, L, hop)])
        sp = np.clip(np.convolve((e > 10 ** (-30 / 20)).astype(float), np.ones(40) / 40, 'same') * 1.6, 0, 1)
        g = 10 ** (np.interp(np.arange(L), np.arange(len(sp)) * hop, -6 * sp) / 20)
        fade = np.minimum(1, (L - np.arange(L)) / SR) * np.minimum(1, np.arange(L) / (.05 * SR))
        mix += m * (g * fade)[:, None]

    events = [] if a.no_auto_sfx else auto_sfx(plan)
    events += [(e['kind'], e['at'], e.get('db', -15)) for e in plan.get('sfx', [])]
    for kind, at, db in events:
        y, pk = sfx(kind)
        y = (y / (np.abs(y).max() + 1e-9) * 10 ** (db / 20)).astype(np.float32)
        st = int(t2o(at) * SR) - pk
        if st < 0:
            y, st = y[-st:], 0
        en = min(L, st + len(y))
        if en > st:
            mix[st:en] += y[:en - st, None]
    raw = f'{J}/_mix.f32'
    mix.astype(np.float32).tofile(raw)
    run([FF, '-v', 'error', '-y', '-f', 'f32le', '-ac', '2', '-ar', str(SR), '-i', raw, '-af',
         'alimiter=limit=0.89:attack=3:release=50:level=false', '-c:a', 'pcm_s16le', f'{J}/mix.wav'])
    os.remove(raw)
    name = plan.get('name', a.job)
    os.makedirs(f'{HOME}/ready', exist_ok=True)
    out = f'{HOME}/ready/{name}.mp4'
    run([FF, '-v', 'error', '-y', '-i', f'{J}/render.mp4', '-i', f'{J}/mix.wav', '-c:v', 'copy', '-c:a', 'aac', '-b:a', '256k',
         '-movflags', '+faststart', out])
    print(f'{len(events)} SFX, музыка: {"иә" if music else "жоқ"} ->', out)


if __name__ == '__main__':
    main()
