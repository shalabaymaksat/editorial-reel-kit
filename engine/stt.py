"""Жергілікті Whisper (API жоқ): Mac-та mlx-whisper, басқа жерде faster-whisper. Модель large-v3.

python3 stt.py JOB [--lang kk] [--prompt "терминдер"] [--model large-v3]
-> projects/JOB/words.json  {"text", "words":[{w,s,e}]}
"""
import argparse, json, os, platform
from paths import job_dir

ap = argparse.ArgumentParser(); ap.add_argument('job'); ap.add_argument('--lang', default='kk')
ap.add_argument('--prompt', default=None); ap.add_argument('--model', default=os.environ.get('ER_WHISPER', 'large-v3'))
a = ap.parse_args()
J = job_dir(a.job); wav = f'{J}/voice16k.wav'
lang = None if a.lang == 'auto' else a.lang
words, texts = [], []

use_mlx = platform.system() == 'Darwin' and platform.machine() == 'arm64'
if use_mlx:
    try:
        import mlx_whisper
    except ImportError:
        use_mlx = False

# Ұзын аудиода Whisper бөліктерді өткізіп жібереді: ~25 с бөліктерге ең тыныш жерден бөліп таныймыз.
import numpy as np, soundfile as sf
y, sr = sf.read(wav, dtype='float32')
hop = sr // 100
en = np.sqrt(np.convolve(y[:len(y) // hop * hop] ** 2, np.ones(hop * 4) / (hop * 4), 'same')[::hop] + 1e-12)
cuts, pos = [0], 0
while len(y) / sr - pos / 100 > 32:
    lo, hi = pos + 2000, min(pos + 2900, len(en) - 1)
    k = lo + int(np.argmin(en[lo:hi]))
    cuts.append(k)
    pos = k
cuts.append(len(en))
model = None


def transcribe(a0, a1):
    """y[a0:a1] (сэмпл) бөлігін тану -> [(сөз, s, e)], мәтін."""
    global model
    off = a0 / sr
    chunk = f'{J}/_chunk.wav'
    sf.write(chunk, y[a0:a1], sr)
    out, txt = [], []
    if use_mlx:
        r = mlx_whisper.transcribe(chunk, path_or_hf_repo=f'mlx-community/whisper-{a.model}-mlx', language=lang,
                                   word_timestamps=True, initial_prompt=a.prompt, condition_on_previous_text=False)
        for sg in r['segments']:
            txt.append(sg['text'].strip())
            out += [dict(w=w['word'].strip(), s=round(w['start'] + off, 3), e=round(w['end'] + off, 3)) for w in sg.get('words', [])]
    else:
        if model is None:
            from faster_whisper import WhisperModel
            model = WhisperModel(a.model, device='cpu', compute_type='int8', cpu_threads=os.cpu_count() or 4)
        segs, _ = model.transcribe(chunk, language=lang, word_timestamps=True, initial_prompt=a.prompt,
                                   vad_filter=True, condition_on_previous_text=False, beam_size=5)
        for sg in segs:
            txt.append(sg.text.strip())
            out += [dict(w=w.word.strip(), s=round(w.start + off, 3), e=round(w.end + off, 3)) for w in sg.words or []]
    os.remove(chunk)
    return out, txt


for ci in range(len(cuts) - 1):
    o, t_ = transcribe(cuts[ci] * hop, min(cuts[ci + 1] * hop, len(y)))
    words += o
    texts += t_

# Екінші өту: дыбыс бар, бірақ сөз жоқ 3 с-тан ұзын аралықты бөлек қайта тану
db = 20 * np.log10(en + 1e-9)
active = db > np.percentile(db, 90) - 25
gaps = []
prev = 0.0
for w in sorted(words, key=lambda w: w['s']) + [dict(s=len(y) / sr, e=len(y) / sr)]:
    if w['s'] - prev > 3 and active[int(prev * 100):int(w['s'] * 100)].mean() > .3:
        gaps.append((prev, w['s']))
    prev = max(prev, w['e'])
for g0, g1 in gaps:
    o, t_ = transcribe(int(max(g0 - .3, 0) * sr), int(min(g1 + .3, len(y) / sr) * sr))
    o = [w for w in o if g0 - .2 <= w['s'] <= g1]
    if o:
        print(f'  қайта танылды {g0:.1f}–{g1:.1f} с: {len(o)} сөз')
        words += o
        texts += t_
words.sort(key=lambda w: w['s'])

words = [w for w in words if w['w']]
# Whisper галлюцинациясы: тыныштықта бір сөзді қайталап жазады — қатарынан 3-тен көп бірдей сөзді алып таста
clean, run_ = [], 0
for i, w in enumerate(words):
    run_ = run_ + 1 if i and w['w'].lower().strip('.,!?') == words[i - 1]['w'].lower().strip('.,!?') else 0
    if run_ < 2 and w['e'] - w['s'] < 3:
        clean.append(w)
if len(clean) < len(words):
    print(f'!! {len(words) - len(clean)} күмәнді сөз алынды (қайталау/тыныштық): дыбысты тексер')
words = clean
json.dump(dict(text=' '.join(texts), words=words), open(f'{J}/words.json', 'w'), ensure_ascii=False, indent=1)
print(' '.join(texts))
print(f'{len(words)} сөз -> {J}/words.json ({"mlx" if use_mlx else "faster-whisper"} {a.model})')
