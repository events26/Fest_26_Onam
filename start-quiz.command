#!/bin/bash
# Onotsavam Quiz Buzzer — double-click launcher for macOS.
# The Windows equivalent is start-quiz.bat.

cd "$(dirname "$0")" || exit 1

if ! command -v python3 >/dev/null 2>&1; then
  cat <<'MSG'

  Python 3 is not installed on this Mac.

  The quickest way to get it:
    1. Open Terminal and run:  xcode-select --install
       Click Install and wait for it to finish.
    2. Or download it from  https://www.python.org/downloads/

  Then double-click this file again.

MSG
  read -r -p "  Press Enter to close. "
  exit 1
fi

echo
echo "  Starting the quiz server. Keep this window open."
echo "  Close it, or press Control-C, to stop the quiz."
echo

python3 quiz-server.py

echo
echo "  The server has stopped."
read -r -p "  Press Enter to close. "
