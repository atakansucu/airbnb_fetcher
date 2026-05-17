#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

echo "==> Sanal ortam"
if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi
source .venv/bin/activate
pip install -q -r requirements.txt

echo "==> Playwright Chromium"
export PLAYWRIGHT_BROWSERS_PATH="${PLAYWRIGHT_BROWSERS_PATH:-$(pwd)/.playwright-browsers}"
playwright install chromium

echo "==> .env"
if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "Oluşturuldu: .env — TELEGRAM_BOT_TOKEN ve TELEGRAM_CHAT_ID doldurun."
else
  echo ".env zaten var."
fi

mkdir -p data logs
echo ""
echo "Kurulum tamam. Sonraki adımlar:"
echo "  1. .env içinde Telegram bilgilerini girin"
echo "  2. ./run.sh --once     # tek tarama testi"
echo "  3. ./run.sh            # sürekli izleme"
