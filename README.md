# Airbnb Barcelona Trip Monitor

Barcelona (16–22 Haziran 2026, 3 kişi) için Airbnb ilanlarını sürekli tarayan, yeni ilan ve fiyat düşüşlerini Telegram/Discord ile bildiren Python aracı.

## Özellikler

- Playwright ile Airbnb arama sonuçlarını tarama (JSON + DOM yedek çıkarım)
- SQLite ile görülen ilanlar ve fiyat geçmişi
- Plaça de Catalunya’ya haversine mesafe + mahalle tahmini
- Ağırlıklı skorlama: merkez, fiyat, yorum, iptal, tüm daire
- Nadir fırsat tespiti (merkezi ilanların alt yüzdelik dilimi)
- Telegram (tercih) ve Discord bildirimleri
- Yinelenen bildirim engeli
- Docker desteği
- Yapılandırılabilir anket aralığı (varsayılan 20 dk)

## Proje yapısı

```
airbnb-barcelona-monitor/
├── config.yaml           # Varsayılan ayarlar
├── .env.example          # Gizli anahtarlar şablonu
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── run.sh
├── data/                 # SQLite (otomatik oluşur)
├── logs/
└── src/
    ├── main.py           # CLI giriş noktası
    ├── config.py
    ├── monitor.py        # Ana döngü
    ├── models.py
    ├── scraper/airbnb.py
    ├── scoring/ranker.py
    ├── storage/database.py
    ├── notifications/
    └── geo/
```

## Kurulum

### 1. Depoyu hazırlayın

```bash
cd airbnb-barcelona-monitor
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

### 2. Ortam değişkenleri

```bash
cp .env.example .env
```

`.env` içinde en azından:

- `TELEGRAM_BOT_TOKEN` — [@BotFather](https://t.me/BotFather) ile bot oluşturun
- `TELEGRAM_CHAT_ID` — [@userinfobot](https://t.me/userinfobot) veya `getUpdates` ile chat id alın

### 3. Tek seferlik test

```bash
chmod +x run.sh
./run.sh --once
```

### 4. Sürekli izleme

```bash
./run.sh
# veya
python -m src.main
```

Aralık: `POLL_INTERVAL_MINUTES` (ör. 15–30).

## Docker

```bash
cp .env.example .env
# .env düzenleyin
docker compose up -d --build
docker compose logs -f
```

Tek döngü:

```bash
docker compose run --rm airbnb-monitor python -m src.main --once
```

## Skorlama (0–100)

| Bileşen | Ağırlık | Mantık |
|--------|---------|--------|
| Mesafe | 30% | Plaça de Catalunya’ya km; ≤1 km ≈ 95+ |
| Fiyat | 30% | €900 bütçeye oran; düşük = yüksek skor |
| Yorum | 15% | ≥4.8 → 90+ |
| İptal | 15% | Ücretsiz iptal → 100 |
| Tüm daire | 10% | Entire home bonus |
| Mahalle | +8 | Eixample, Born, Gràcia vb. |

**Nadir fırsat:** ≤3 km içindeki ilanların fiyat dağılımında alt %15 (ayar: `RARE_DEAL_PERCENTILE`).

Bildirim eşiği: `min_score_to_notify` (config.yaml, varsayılan 55).

## Yapılandırma

| Değişken | Açıklama |
|----------|----------|
| `MAX_TOTAL_PRICE_EUR` | Üst fiyat (900) |
| `POLL_INTERVAL_MINUTES` | Tarama aralığı |
| `REQUIRE_SUPERHOST` | Zorunlu Superhost |
| `REQUIRE_SELF_CHECK_IN` | Zorunlu self check-in |
| `REQUIRE_ENTIRE_HOME` | Sadece tüm daire |
| `REQUIRE_FREE_CANCELLATION` | Ücretsiz iptal zorunlu |
| `HEADLESS` | `false` ile tarayıcı görünür (debug) |

`config.yaml` içinde `preferred_neighborhoods` ve skor ağırlıkları düzenlenebilir.

## Önemli notlar

1. **Airbnb Kullanım Şartları:** Otomatik tarama Airbnb ToS ile çelişebilir. Kişisel kullanım için dikkatli olun; aşırı sık istek atmayın (`POLL_INTERVAL_MINUTES` ≥ 15 önerilir).
2. **Anti-bot:** Airbnb arayüzü sık değişir. Seçiciler kırılırsa `HEADLESS=false` ile `./run.sh --once` çalıştırıp logları kontrol edin.
3. **Fiyatlar:** Toplam fiyat bazen sayfada net görünmez; ilk döngüde eksik fiyat normaldir.

## Geliştirme

```bash
pytest tests/ -q
```

## Lisans

Kişisel kullanım — sorumluluk kullanıcıya aittir.
