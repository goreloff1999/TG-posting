# 🚀 Crypto Autoposting System - БЫСТРАЯ УСТАНОВКА

## За 5 минут до запуска!

### Что нужно установить (один раз):

1. **Docker Desktop** - скачать с https://www.docker.com/products/docker-desktop
2. **Git** - скачать с https://git-scm.com/downloads

### Установка системы:

```bash
# 1. Скачать систему
git clone <your-repo-url> crypto-autoposting-system
cd crypto-autoposting-system

# 2. Запустить настройку (интерактивно)
python setup.py

# 3. Запустить систему
./start.sh        # Linux/macOS
start.bat         # Windows
```

## Что спросит программа настройки:

### 🔑 ШАГ 1: API ключи
- **OpenAI ключ** (обязательно) - получить на https://platform.openai.com/api-keys
- **Telegram Bot токен** (обязательно) - написать @BotFather → /newbot
- **Telegram API** (обязательно) - получить на https://my.telegram.org/apps
- **DeepL ключ** (опционально) - получить на https://www.deepl.com/pro-api
- **Stability AI** (опционально) - получить на https://platform.stability.ai/

### 📺 ШАГ 2: Источники
```
Telegram каналы: @cryptonews, @bitcoin, @ethereum
Twitter аккаунты: coindesk, cointelegraph
```

### 💰 ШАГ 3: Партнерские ссылки
```
Binance: https://accounts.binance.com/register?ref=ВАША_ССЫЛКА
Bybit: https://www.bybit.com/register?affiliate_id=ВАШ_ID
Каждый 5-й пост (настраивается)
```

### 📅 ШАГ 4: Публикация  
```
Канал для постов: @your_channel или -1001234567890
Постов в день: 10
Интервал: 60 минут
Время работы: 09:00-23:00
```

## После настройки:

✅ **Запуск**: `./start.sh` или `start.bat`

✅ **Открыть панели**:
- http://localhost:8000 - управление системой
- http://localhost:3000 - статистика (admin/admin)

✅ **Добавить бота в канал** как администратора с правами на отправку сообщений

## Полезные команды:

```bash
# Посмотреть что происходит
docker-compose logs -f worker

# Проверить очереди  
docker-compose exec redis redis-cli llen raw_content_queue

# Остановить систему
docker-compose down

# Перезапустить
docker-compose restart
```

## Решение проблем:

❌ **"Docker не найден"** → Установить Docker Desktop и перезагрузиться

❌ **"Бот не отвечает"** → Проверить что бот добавлен в канал как админ

❌ **"Нет постов"** → Проверить что источники активные и доступные

❌ **"Ошибки API"** → Проверить правильность ключей в .env файле

## Что дальше:

1. **Запустите систему** - она начнет мониторить источники
2. **Проверьте модерацию** - http://localhost:8000/hitl  
3. **Настройте под себя** - добавьте больше источников через веб-интерфейс
4. **Мониторьте качество** - следите за статистикой в Grafana

---

**Всё! Система работает автоматически 24/7** 🎉

При проблемах смотрите полную документацию в `docs/INSTALLATION.md`
