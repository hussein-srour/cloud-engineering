#!/bin/bash
set -e
cd -- "$(dirname -- "$0")"
trap 'echo "Setup could not finish. Review the error above, then press Enter."; read -r' ERR
if ! command -v python3 >/dev/null; then
  echo 'Install Python 3.10 or newer from python.org, then run this file again.'
  read -r
  exit 1
fi
if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv
fi
if ! .venv/bin/python -c 'import flask, reportlab, PIL, waitress' >/dev/null 2>&1; then
  echo 'Installing the app. Internet is needed for this first setup only.'
  .venv/bin/python -m pip install -r requirements.txt
fi
.venv/bin/python app.py
