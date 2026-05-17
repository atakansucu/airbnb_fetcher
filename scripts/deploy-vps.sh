#!/usr/bin/env bash
# Ucuz VPS'te (Hetzner, DigitalOcean vb.) 7/24 Docker ile çalıştırma.
# Kullanım (sunucuda):
#   git clone <repo-url> airbnb-barcelona-monitor && cd airbnb-barcelona-monitor
#   cp .env.example .env   # düzenle
#   ./scripts/deploy-vps.sh

set -euo pipefail
cd "$(dirname "$0")/.."

if [[ ! -f .env ]]; then
  echo "Hata: .env yok. Önce cp .env.example .env ve Telegram bilgilerini doldur."
  exit 1
fi

mkdir -p data logs

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker kurulu değil. Örn: https://docs.docker.com/engine/install/"
  exit 1
fi

docker compose up -d --build
echo ""
echo "Monitor arka planda çalışıyor."
echo "  Loglar: docker compose logs -f"
echo "  Durdur: docker compose down"
