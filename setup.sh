#!/bin/bash
# Бір рет (~3–5 мин): ffmpeg, Python кітапханалары, Whisper моделі. Mac-та brew/venv болса, соны қолданады.
K="$(cd "$(dirname "$0")" && pwd)"
(sudo -n true 2>/dev/null && SUDO=sudo) || SUDO=
if ! command -v ffmpeg >/dev/null; then
  if command -v apt-get >/dev/null; then
    $SUDO apt-get update -qq >/dev/null 2>&1; $SUDO apt-get install -y -qq ffmpeg >/dev/null 2>&1
  elif command -v brew >/dev/null; then
    brew install ffmpeg >/dev/null 2>&1
  fi
fi
PY=${ER_PY:-python3}
$PY -m pip install -q --disable-pip-version-check numpy scipy opencv-python-headless mediapipe soundfile pyloudnorm \
  pillow fonttools faster-whisper gdown requests 2>&1 | tail -2
# Whisper large-v3 моделін алдын ала жүктеу (~3 GB, бір рет, фонда)
$PY -c "from faster_whisper import WhisperModel; WhisperModel('${ER_WHISPER:-large-v3}', device='cpu', compute_type='int8')" >/dev/null 2>&1 &
$PY -c "import mediapipe, cv2, soundfile, pyloudnorm, PIL, faster_whisper, gdown; print('python OK')"
ffmpeg -hide_banner -filters 2>/dev/null | grep -q lut3d && echo "ffmpeg OK (lut3d)" || echo "!! ffmpeg жоқ немесе lut3d сүзгісі жоқ"
[ -f "$K/luts/slog3_to_709.cube" ] || $PY "$K/engine/grade.py" base >/dev/null && echo "base LUT OK"
echo "Whisper моделі фонда жүктеліп жатыр"
