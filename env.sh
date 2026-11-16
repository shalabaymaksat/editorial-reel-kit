# source <kit>/env.sh — әр Bash командасының басында (shell күйі сақталмайды)
#   K — kit түбірі   E — engine   PY — python
#   ER_HOME — жұмыс папкасы: <пайдаланушы репосы>/editorial (kit өз ішінде іске қосылса — kit түбірі)
K="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"; export K E="$K/engine"
R="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
if [ "$R" = "$K" ]; then export ER_HOME="$K"; else export ER_HOME="$R/editorial"; fi
[ -n "$ER_PY" ] && export PY="$ER_PY" || export PY=python3
mkdir -p "$ER_HOME"/{inbox,broll,assets,projects,ready}
if [ "$ER_HOME" != "$K" ]; then
  [ -f "$ER_HOME/.gitignore" ] || printf 'inbox/\nbroll/\nprojects/*/media/\nprojects/*/*.mp4\nprojects/*/*.wav\nprojects/*/check/\n' > "$ER_HOME/.gitignore"
  touch "$ER_HOME/assets/.gitkeep" "$ER_HOME/ready/.gitkeep"
fi
true
