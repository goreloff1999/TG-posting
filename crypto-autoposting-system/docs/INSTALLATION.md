# Инструкция по установке и эксплуатации

## 🚀 БЫСТРАЯ УСТАНОВКА (5 минут)

### Предварительные требования:
1. **Docker Desktop** - https://www.docker.com/products/docker-desktop
2. **Git** - https://git-scm.com/downloads

### Установка за 3 команды:
```bash
git clone <your-repo-url> crypto-autoposting-system
cd crypto-autoposting-system
python setup.py
```

**Программа setup.py проведет вас через 4 простых шага:**
1. 🔑 API ключи (OpenAI, Telegram Bot, Telegram API)
2. 📺 Источники (каналы и аккаунты для мониторинга)  
3. 💰 Партнерские ссылки (ваши реферальные ссылки)
4. 📅 Настройки публикации (канал, количество постов)

### Запуск:
```bash
./start.sh        # Linux/macOS
start.bat         # Windows
```

### Готово! Откройте:
- **http://localhost:8000** - управление системой
- **http://localhost:3000** - статистика (admin/admin)

---

## 📋 ПОДРОБНАЯ НАСТРОЙКА

### Часть 1: Получение API ключей

### 1.1 Получение API ключей

#### Telegram Bot API:
1. Напишите @BotFather в Telegram
2. Отправьте `/newbot`
3. Выберите имя и username для бота
4. Сохраните полученный token

#### Telegram API для мониторинга:
1. Перейдите на https://my.telegram.org/
2. Войдите в аккаунт
3. Создайте новое приложение
4. Сохраните `api_id` и `api_hash`

#### OpenAI API:
1. Зарегистрируйтесь на https://platform.openai.com/
2. Перейдите в API Keys
3. Создайте новый ключ
4. Пополните баланс аккаунта ($10+ рекомендуется)

#### DeepL API:
1. Зарегистрируйтесь на https://www.deepl.com/pro-api
2. Выберите план (Free или Pro)
3. Получите API ключ в аккаунте

#### Twitter API (опционально):
1. Зарегистрируйтесь на https://developer.twitter.com/
2. Создайте новое приложение
3. Получите Bearer Token

#### Stability AI API (для генерации изображений):
1. Зарегистрируйтесь на https://platform.stability.ai/
2. Получите API ключ
3. Пополните баланс

### 1.2 Настройка хостинга

#### Для VPS/Dedicated сервера:
```bash
# Обновление системы (Ubuntu)
sudo apt update && sudo apt upgrade -y

# Установка Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER

# Установка Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# Перезагрузка для применения изменений
sudo reboot
```

## Часть 2: Установка системы

### 2.1 Клонирование репозитория

```bash
# Клонирование
git clone <repository-url> crypto-autoposting-system
cd crypto-autoposting-system

# Создание структуры папок
mkdir -p data/postgres data/redis data/minio logs
```

### 2.2 Настройка конфигурации

#### Основной конфигурационный файл:
```bash
cp .env.example .env
nano .env
```

Заполните все значения в `.env`:

```env
# === Основные настройки ===
DEBUG=false
LOG_LEVEL=INFO
DATABASE_URL=postgresql://cryptouser:your_secure_password@postgres:5432/cryptodb
REDIS_URL=redis://redis:6379/0

# === API ключи ===
OPENAI_API_KEY=sk-your-openai-key
DEEPL_API_KEY=your-deepl-key
TELEGRAM_BOT_TOKEN=your-bot-token
TELEGRAM_API_ID=your-api-id
TELEGRAM_API_HASH=your-api-hash
TWITTER_BEARER_TOKEN=your-twitter-token
STABILITY_API_KEY=your-stability-key

# === Каналы и источники ===
TELEGRAM_CHANNELS=@channel1,@channel2,@channel3
TWITTER_ACCOUNTS=username1,username2,username3
OUTPUT_TELEGRAM_CHANNEL=-1001234567890

# === Файловое хранилище ===
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=your_secure_minio_password
MINIO_BUCKET=crypto-content

# === Безопасность ===
SECRET_KEY=your-very-secure-secret-key-min-32-chars
POSTGRES_USER=cryptouser
POSTGRES_PASSWORD=your_secure_password
POSTGRES_DB=cryptodb

# === Аффилированные ссылки ===
AFFILIATE_LINKS={"binance": "https://accounts.binance.com/register?ref=YOUR_REF", "bybit": "https://www.bybit.com/register?affiliate_id=YOUR_ID"}
AFFILIATE_FREQUENCY=5

# === Модерация ===
HITL_WEBHOOK_URL=https://your-domain.com/hitl
ADMIN_TELEGRAM_IDS=123456789,987654321
```

### 2.3 Настройка источников

Создайте файл `config/sources.yaml`:

```yaml
telegram_channels:
  - name: "CoinDesk"
    username: "@CoinDeskOfficial"
    weight: 1.0
    language: "en"
    keywords: ["bitcoin", "ethereum", "crypto", "blockchain"]
    
  - name: "Cointelegraph"
    username: "@Cointelegraph"
    weight: 0.9
    language: "en"
    keywords: ["cryptocurrency", "news", "analysis"]

twitter_accounts:
  - username: "CoinDesk"
    weight: 1.0
    language: "en"
    
  - username: "cointelegraph"
    weight: 0.9
    language: "en"

processing_rules:
  min_score: 0.3
  max_similarity: 0.8
  hitl_threshold: 0.7
  languages: ["en", "ru"]
  content_types: ["news", "analysis", "technical"]
```

## Часть 3: Запуск системы

### 3.1 Первичная настройка базы данных

```bash
# Создание и запуск только базы данных
docker-compose up -d postgres redis

# Ожидание готовности БД (30 секунд)
sleep 30

# Инициализация схемы
docker-compose exec postgres psql -U cryptouser -d cryptodb -f /docker-entrypoint-initdb.d/init-db.sql
```

### 3.2 Запуск всех сервисов

```bash
# Сборка образов
docker-compose build

# Запуск всех сервисов
docker-compose up -d

# Проверка статуса
docker-compose ps
```

Все сервисы должны быть в состоянии "Up":
- postgres
- redis
- minio
- api
- worker
- telegram-ingestion
- twitter-ingestion
- scheduler
- prometheus
- grafana

### 3.3 Проверка работоспособности

```bash
# Проверка API
curl http://localhost:8000/health

# Проверка логов
docker-compose logs api
docker-compose logs worker

# Проверка очередей Redis
docker-compose exec redis redis-cli llen raw_content_queue
```

## Часть 4: Первоначальная настройка

### 4.1 Настройка Telegram бота

1. Добавьте вашего бота в выходной канал как администратора
2. Дайте боту права на отправку сообщений
3. Получите ID канала:

```bash
# Отправьте тестовое сообщение в канал, затем получите ID
curl -X GET "https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates"
```

### 4.2 Настройка мониторинга

1. Откройте Grafana: http://localhost:3000
2. Логин: admin, пароль: admin
3. Измените пароль при первом входе
4. Импортируйте дашборды из `monitoring/grafana/dashboards/`

### 4.3 Тестирование системы

```bash
# Добавление тестового источника
curl -X POST http://localhost:8000/sources/ \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Test Source",
    "source_type": "telegram",
    "identifier": "@test_channel",
    "is_active": true,
    "weight": 1.0
  }'

# Запуск тестовой обработки
curl -X POST http://localhost:8000/process/test \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Bitcoin reaches new all-time high above $100,000",
    "source": "test"
  }'
```

## Часть 5: Эксплуатация системы

### 5.1 Ежедневное управление

#### Мониторинг очередей:
```bash
# Проверка количества задач в очередях
docker-compose exec redis redis-cli llen raw_content_queue
docker-compose exec redis redis-cli llen processing_queue
docker-compose exec redis redis-cli llen publishing_queue
```

#### Проверка логов:
```bash
# Логи обработки контента
docker-compose logs -f worker

# Логи публикации
docker-compose logs -f api

# Ошибки в системе
docker-compose logs --tail=100 | grep ERROR
```

### 5.2 Human-in-the-Loop (HITL)

#### Веб-интерфейс для модерации:
1. Откройте http://localhost:8000/hitl
2. Авторизуйтесь с помощью Telegram
3. Просматривайте материалы, требующие модерации
4. Одобряйте или отклоняйте с комментариями

#### API для модерации:
```bash
# Получение ожидающих модерации
curl http://localhost:8000/hitl/pending

# Одобрение материала
curl -X POST http://localhost:8000/hitl/approve/123 \
  -H "Content-Type: application/json" \
  -d '{"approved": true, "comment": "Good quality content"}'
```

### 5.3 Управление источниками

#### Добавление нового Telegram канала:
```bash
curl -X POST http://localhost:8000/sources/ \
  -H "Content-Type: application/json" \
  -d '{
    "name": "New Crypto Channel",
    "source_type": "telegram",
    "identifier": "@new_channel",
    "is_active": true,
    "weight": 0.8,
    "language": "en"
  }'
```

#### Отключение источника:
```bash
curl -X PATCH http://localhost:8000/sources/123 \
  -H "Content-Type: application/json" \
  -d '{"is_active": false}'
```

### 5.4 Настройка расписания публикаций

```bash
# Создание расписания
curl -X POST http://localhost:8000/schedule/ \
  -H "Content-Type: application/json" \
  -d '{
    "time_slots": ["09:00", "14:00", "18:00", "22:00"],
    "max_posts_per_day": 10,
    "min_interval_minutes": 120
  }'
```

### 5.5 Управление аффилированными ссылками

#### Обновление ссылок:
```bash
curl -X POST http://localhost:8000/affiliates/ \
  -H "Content-Type: application/json" \
  -d '{
    "exchange": "binance",
    "url": "https://accounts.binance.com/register?ref=NEW_REF",
    "weight": 0.6
  }'
```

## Часть 6: Администрирование

### 6.1 Резервное копирование

#### Ежедневное резервное копирование БД:
```bash
# Создание скрипта бэкапа
cat > backup.sh << 'EOF'
#!/bin/bash
DATE=$(date +%Y%m%d_%H%M%S)
docker-compose exec postgres pg_dump -U cryptouser cryptodb > backups/db_backup_$DATE.sql
find backups/ -name "*.sql" -mtime +7 -delete
EOF

chmod +x backup.sh

# Добавление в crontab
echo "0 3 * * * /path/to/crypto-autoposting-system/backup.sh" | crontab -
```

#### Резервное копирование файлов:
```bash
# Бэкап MinIO данных
docker-compose exec minio mc mirror /data/crypto-content /backup/minio-backup/
```

### 6.2 Обновление системы

```bash
# Получение обновлений
git pull origin main

# Остановка сервисов
docker-compose down

# Пересборка с обновлениями
docker-compose build --no-cache

# Запуск обновленной системы
docker-compose up -d

# Проверка миграций БД
docker-compose exec api python -m alembic upgrade head
```

### 6.3 Масштабирование

#### Увеличение количества воркеров:
```bash
# Редактирование docker-compose.yml
nano docker-compose.yml

# Увеличьте replicas для worker:
services:
  worker:
    # ... other config
    deploy:
      replicas: 3

# Применение изменений
docker-compose up -d --scale worker=3
```

#### Настройка кластера Redis:
Для высоких нагрузок рассмотрите настройку Redis Cluster или использование внешнего Redis сервиса.

### 6.4 Мониторинг производительности

#### Ключевые метрики в Grafana:
1. **Пропускная способность**: сообщений в минуту
2. **Время обработки**: среднее время от получения до публикации
3. **Качество**: процент материалов, прошедших модерацию
4. **Ошибки**: количество ошибок API и обработки
5. **Использование ресурсов**: CPU, память, диск

#### Настройка алертов:
```yaml
# prometheus/alerts.yml
groups:
  - name: crypto-autoposting
    rules:
      - alert: HighErrorRate
        expr: rate(errors_total[5m]) > 0.1
        for: 2m
        annotations:
          summary: "High error rate detected"
          
      - alert: QueueBacklog
        expr: redis_queue_length > 1000
        for: 5m
        annotations:
          summary: "Processing queue backlog"
```

## Часть 7: Устранение неполадок

### 7.1 Частые проблемы

#### API ключи не работают:
```bash
# Проверка переменных окружения
docker-compose exec api env | grep API

# Тестирование OpenAI
docker-compose exec api python -c "
import openai
openai.api_key = 'your-key'
print(openai.Model.list())
"
```

#### Telegram бот не отвечает:
```bash
# Проверка webhook
curl https://api.telegram.org/bot<TOKEN>/getWebhookInfo

# Сброс webhook
curl https://api.telegram.org/bot<TOKEN>/deleteWebhook

# Проверка логов
docker-compose logs telegram-ingestion
```

#### База данных недоступна:
```bash
# Проверка статуса
docker-compose exec postgres pg_isready

# Подключение к БД
docker-compose exec postgres psql -U cryptouser -d cryptodb

# Проверка таблиц
\dt
```

#### Очереди не обрабатываются:
```bash
# Проверка воркеров Celery
docker-compose exec worker celery -A src.tasks inspect active

# Перезапуск воркеров
docker-compose restart worker

# Очистка заблокированных задач
docker-compose exec redis redis-cli flushdb
```

### 7.2 Диагностика

#### Проверка всех компонентов:
```bash
#!/bin/bash
echo "=== System Health Check ==="

# API доступность
curl -s http://localhost:8000/health && echo "✓ API OK" || echo "✗ API FAIL"

# База данных
docker-compose exec postgres pg_isready && echo "✓ PostgreSQL OK" || echo "✗ PostgreSQL FAIL"

# Redis
docker-compose exec redis redis-cli ping && echo "✓ Redis OK" || echo "✗ Redis FAIL"

# MinIO
curl -s http://localhost:9000/minio/health/live && echo "✓ MinIO OK" || echo "✗ MinIO FAIL"

# Очереди
QUEUE_SIZE=$(docker-compose exec redis redis-cli llen raw_content_queue)
echo "Raw content queue: $QUEUE_SIZE items"

# Логи ошибок за последний час
echo "=== Recent Errors ==="
docker-compose logs --since=1h | grep ERROR | tail -10
```

### 7.3 Логи и отладка

#### Включение отладочного режима:
```bash
# В .env файле
DEBUG=true
LOG_LEVEL=DEBUG

# Перезапуск
docker-compose restart
```

#### Анализ логов:
```bash
# Поиск ошибок обработки
docker-compose logs worker | grep "Processing failed"

# Поиск проблем с API
docker-compose logs api | grep "HTTP 5"

# Мониторинг в реальном времени
docker-compose logs -f --tail=50
```

## Часть 8: Безопасность

### 8.1 Защита API ключей

```bash
# Использование Docker secrets (в продакшене)
echo "your-openai-key" | docker secret create openai_key -
echo "your-telegram-token" | docker secret create telegram_token -

# Обновление docker-compose.yml для использования secrets
```

### 8.2 Настройка HTTPS

```bash
# Установка Certbot
sudo apt install certbot

# Получение SSL сертификата
sudo certbot certonly --standalone -d your-domain.com

# Настройка Nginx с SSL
```

### 8.3 Файрвол и доступ

```bash
# Настройка UFW
sudo ufw enable
sudo ufw allow 22/tcp      # SSH
sudo ufw allow 80/tcp      # HTTP
sudo ufw allow 443/tcp     # HTTPS
sudo ufw deny 8000/tcp     # Закрыть прямой доступ к API
```

## Часть 9: Оптимизация

### 9.1 Настройка производительности

#### PostgreSQL:
```sql
-- Оптимизация конфигурации
ALTER SYSTEM SET shared_buffers = '2GB';
ALTER SYSTEM SET work_mem = '256MB';
ALTER SYSTEM SET maintenance_work_mem = '512MB';
SELECT pg_reload_conf();
```

#### Redis:
```bash
# Настройка Redis для лучшей производительности
echo "maxmemory 4gb" >> data/redis/redis.conf
echo "maxmemory-policy allkeys-lru" >> data/redis/redis.conf
```

### 9.2 Кэширование

#### Настройка кэша обработанного контента:
```python
# В конфигурации
CACHE_TTL = 3600  # 1 час
SIMILARITY_CACHE_SIZE = 10000
TRANSLATION_CACHE_SIZE = 5000
```

## Часть 10: Техническая поддержка

### 10.1 Контакты поддержки

- **Документация**: [GitHub Wiki]
- **Баг-репорты**: [GitHub Issues]
- **Сообщество**: [Telegram канал поддержки]

### 10.2 Обновления и roadmap

Система регулярно обновляется. Следите за:
- Новыми функциями
- Исправлениями безопасности
- Оптимизациями производительности
- Поддержкой новых API

### 10.3 Коммерческая поддержка

Для крупных проектов доступна:
- Настройка под индивидуальные требования
- Приоритетная техническая поддержка
- Обучение команды
- Консультации по масштабированию

---

## Заключение

После выполнения всех шагов данной инструкции у вас будет полностью функционирующая система автоматического постинга криптовалютных новостей. Система способна обрабатывать сотни материалов в день, создавая качественный уникальный контент для вашей аудитории.

Не забывайте регулярно мониторить работу системы, обновлять конфигурацию под изменяющиеся требования и следить за качеством публикуемого контента.

**Успешной эксплуатации!**
