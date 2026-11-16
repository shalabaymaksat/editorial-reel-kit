"""words.json -> plan.draft.json: бір-бір сөзден субтитр + бастапқы сахна (бет).

python3 subs_auto.py JOB
Қысқа сөздер (<0,2 с) келесісімен бірігеді. Claude мәтінді түзетіп, кілт сөзге "style": "m" қояды,
сахналарды қосып, plan.json етіп сақтайды.
"""
import json, re, sys
from paths import job_dir

FILLER = re.compile(r'^(ы+|э+|м+|а+|ее+|эм+|мм+|хм+|uh+|um+|hmm+)[.,!?…]*$', re.I)
J = job_dir(sys.argv[1])
words = [w for w in json.load(open(f'{J}/words.json'))['words'] if not FILLER.match(w['w'].strip())]
out = []
for i, w in enumerate(words):
    t = w['w'].strip()
    nxt = words[i + 1]['s'] if i + 1 < len(words) else w['e'] + 1
    if out and out[-1].get('_short') and len(out[-1]['t']) + len(t) < 18:
        out[-1]['t'] += ' ' + t
        out[-1].pop('_short')
        continue
    e = dict(at=round(w['s'], 2), t=t)
    if nxt - w['s'] < .2:
        e['_short'] = True
    out.append(e)
for e in out:
    e.pop('_short', None)
plan = dict(name=sys.argv[1], zoom='cut', scenes=[dict(s=round(words[0]['s'], 2) if words else 0, type='head', top=[])], words=out, sfx=[])
json.dump(plan, open(f'{J}/plan.draft.json', 'w'), ensure_ascii=False, indent=1)
print(f'{len(out)} субтитр -> plan.draft.json')
