# editorial-reel-kit

Камераға сөйлеген видеоны Claude Code өзі editorial стиліндегі рилске монтаждайды:
- **цвет:** қалыпты видеоның түсін қалаған скриншотқа сәйкестендіреді, Sony S-Log3 видеоны да түрлендіреді;
- **дыбыс:** бөлек жазылған таза аудионы камерамен синхрондап, шумын тазалап, тереңдетеді;
- **қию:** кідірістер мен ыңылдауды қиып, кесінді сайын 1,0 ↔ 1,2 зум жасайды;
- **тақырып:** бастың артына кететін үлкен тақырып қояды (жуан гротеск + Playfair курсив);
- **субтитр:** бір-бір сөзден шығарады, кілт сөз жалбыз түсті курсив болады;
- **интерфейс экрандары:** итеріп ауысатын ақ экран, чек-лист, салыстыру жолақтары, қызыл фондағы үлкен сан;
- **B-roll:** айтылған сөзге сай қояды және пиксель шықпауын 4K ережесімен тексереді;
- **SFX мен музыка:** SFX-ті өзі синтездейді, файл керек емес; фон музыкасы міндетті емес.

## Қалай қолданамын
Claude Code-қа (Mac, веб не телефон) жаз:
```
Осы нұсқаулықпен монтаж жаса: https://github.com/shalabaymaksat/editorial-reel-kit/blob/main/SKILL.md
Видео: <Google Drive сілтемесі>
Таза аудио: <сілтеме, бар болса>
Цвет референсі: <скриншот, бар болса>
```
Claude мәтін мен сахна картасын көрсетеді. «Дұрыс» десең, рендерлеп, `editorial/ready/` ішіне салады.

## Не керек
- ffmpeg, Python 3.10+ (`setup.sh` орнатады), Whisper моделі (~3 GB, бір рет жүктеледі).
- API кілті керек емес.
- B-roll-ды өзің бересің (Drive сілтемесі не файл). Толық экранға 4K көлденең не 1080×1920 тік видео керек.

## Лицензия
Код: MIT (`LICENSE`).

Ішіндегі файлдар:
- **Inter Tight, Playfair Display:** SIL Open Font License 1.1 (`fonts/OFL-*.txt`).
- **MediaPipe selfie multiclass моделі:** Apache 2.0 (Google).

B-roll, музыка және сенің видеоларыңның құқығы өзіңде.

---

**English.** Claude Code skill that edits a talking-head video into a 9:16 editorial reel. It matches the colors of
regular (or Sony S-Log3) footage to a reference screenshot, syncs a separate clean audio track, cuts pauses and filler, and adds 1.0↔1.2
cut zooms. Big titles sit behind the speaker's head, subtitles appear one word at a time with key words in a mint serif,
and there are white/red interface scenes (push, checklist, compare, big number). B-roll follows what is said and is
checked against a 4K quality rule. SFX are synthesized, and background music is optional. Start with `SKILL.md`.
