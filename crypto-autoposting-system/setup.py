#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Упрощенная настройка системы автопостинга
Всего 4 шага для запуска!
"""

import os
import json
import yaml
import secrets
import subprocess
import sys
from pathlib import Path

def print_header():
    print("""
╔══════════════════════════════════════════════════════════════╗
║                                                              ║
║           🚀 CRYPTO AUTOPOSTING SYSTEM SETUP 🚀              ║
║                                                              ║
║              Настройка за 4 простых шага!                   ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
    """)

def step_1_api_keys():
    print("\n📝 ШАГ 1: API КЛЮЧИ")
    print("=" * 50)
    
    keys = {}
    
    # OpenAI (обязательный)
    print("\n🤖 OpenAI API ключ (ОБЯЗАТЕЛЬНО):")
    print("   Получить: https://platform.openai.com/api-keys")
    keys['openai'] = input("   Вставьте ключ: ").strip()
    
    # Telegram Bot (обязательный)
    print("\n📱 Telegram Bot Token (ОБЯЗАТЕЛЬНО):")
    print("   Получить: напишите @BotFather -> /newbot")
    keys['telegram_bot'] = input("   Вставьте токен: ").strip()
    
    # Telegram API для мониторинга (обязательный)
    print("\n📡 Telegram API для мониторинга каналов:")
    print("   Получить: https://my.telegram.org/apps")
    keys['telegram_api_id'] = input("   API ID: ").strip()
    keys['telegram_api_hash'] = input("   API Hash: ").strip()
    
    # DeepL (опционально)
    print("\n🌐 DeepL API (опционально, можно пропустить):")
    print("   Получить: https://www.deepl.com/pro-api")
    deepl_key = input("   API ключ (Enter для пропуска): ").strip()
    if deepl_key:
        keys['deepl'] = deepl_key
    
    # Stability AI (опционально)
    print("\n🎨 Stability AI для генерации картинок (опционально):")
    print("   Получить: https://platform.stability.ai/")
    stability_key = input("   API ключ (Enter для пропуска): ").strip()
    if stability_key:
        keys['stability'] = stability_key
    
    return keys

def step_2_sources():
    print("\n\n📺 ШАГ 2: ИСТОЧНИКИ ИНФОРМАЦИИ")
    print("=" * 50)
    
    sources = {
        'telegram_channels': [],
        'twitter_accounts': []
    }
    
    # Telegram каналы
    print("\n📱 Telegram каналы для мониторинга:")
    print("   Формат: @channel_name или https://t.me/channel_name")
    print("   Примеры: @cryptonews, @bitcoin, @ethereum")
    
    channels_input = input("\n   Введите каналы через запятую: ").strip()
    if channels_input:
        channels = [ch.strip().replace('https://t.me/', '@') for ch in channels_input.split(',')]
        for channel in channels:
            if not channel.startswith('@'):
                channel = '@' + channel
            sources['telegram_channels'].append({
                'name': channel.replace('@', ''),
                'username': channel,
                'weight': 1.0,
                'language': 'auto'
            })
    
    # Twitter аккаунты (опционально)
    print("\n🐦 Twitter аккаунты (опционально):")
    print("   Примеры: coindesk, cointelegraph, elonmusk")
    
    twitter_input = input("   Введите через запятую (Enter для пропуска): ").strip()
    if twitter_input:
        accounts = [acc.strip().replace('@', '') for acc in twitter_input.split(',')]
        for account in accounts:
            sources['twitter_accounts'].append({
                'username': account,
                'weight': 1.0,
                'language': 'auto'
            })
    
    return sources

def step_3_affiliate():
    print("\n\n💰 ШАГ 3: ПАРТНЕРСКИЕ ССЫЛКИ")
    print("=" * 50)
    
    affiliate = {}
    
    print("\n💎 Добавьте ваши реферальные ссылки:")
    print("   Оставьте пустым если пока нет")
    
    # Binance
    binance_ref = input("\n   Binance реф. ссылка: ").strip()
    if binance_ref:
        affiliate['binance'] = binance_ref
    
    # Bybit
    bybit_ref = input("   Bybit реф. ссылка: ").strip()
    if bybit_ref:
        affiliate['bybit'] = bybit_ref
    
    # OKX
    okx_ref = input("   OKX реф. ссылка: ").strip()
    if okx_ref:
        affiliate['okx'] = okx_ref
    
    # Другие
    other_ref = input("   Другая ссылка (название:ссылка): ").strip()
    if other_ref and ':' in other_ref:
        name, link = other_ref.split(':', 1)
        affiliate[name.strip()] = link.strip()
    
    # Частота вставки
    print("\n📊 Как часто вставлять партнерские ссылки?")
    frequency = input("   Каждый N-ый пост (по умолчанию 5): ").strip()
    try:
        affiliate_frequency = int(frequency) if frequency else 5
    except:
        affiliate_frequency = 5
    
    return affiliate, affiliate_frequency

def step_4_posting():
    print("\n\n📅 ШАГ 4: НАСТРОЙКИ ПУБЛИКАЦИИ")
    print("=" * 50)
    
    # Выходной канал
    print("\n📢 В какой канал публиковать?")
    print("   Добавьте бота как администратора в канал!")
    output_channel = input("   ID канала или @username: ").strip()
    
    # Количество постов
    posts_per_day = input("\n📈 Сколько постов в день? (по умолчанию 10): ").strip()
    try:
        posts_per_day = int(posts_per_day) if posts_per_day else 10
    except:
        posts_per_day = 10
    
    # Интервал между постами
    min_interval = input("   Минимальный интервал между постами в минутах (по умолчанию 60): ").strip()
    try:
        min_interval = int(min_interval) if min_interval else 60
    except:
        min_interval = 60
    
    # Время работы
    print("\n⏰ В какое время публиковать? (24-часовой формат)")
    work_hours = input("   Время работы, например: 09:00-23:00 (по умолчанию 24/7): ").strip()
    
    return {
        'output_channel': output_channel,
        'posts_per_day': posts_per_day,
        'min_interval': min_interval,
        'work_hours': work_hours or '00:00-23:59'
    }

def generate_env_file(keys, affiliate, affiliate_frequency, posting):
    """Генерация .env файла"""
    
    # Генерация случайных паролей
    secret_key = secrets.token_urlsafe(32)
    postgres_password = secrets.token_urlsafe(16)
    minio_password = secrets.token_urlsafe(16)
    
    env_content = f"""# 🚀 CRYPTO AUTOPOSTING SYSTEM CONFIG 🚀
# Сгенерировано автоматически

# === Основные настройки ===
DEBUG=false
LOG_LEVEL=INFO
SECRET_KEY={secret_key}

# === База данных ===
DATABASE_URL=postgresql://cryptouser:{postgres_password}@postgres:5432/cryptodb
POSTGRES_USER=cryptouser
POSTGRES_PASSWORD={postgres_password}
POSTGRES_DB=cryptodb

# === Redis ===
REDIS_URL=redis://redis:6379/0

# === API ключи ===
OPENAI_API_KEY={keys['openai']}
TELEGRAM_BOT_TOKEN={keys['telegram_bot']}
TELEGRAM_API_ID={keys['telegram_api_id']}
TELEGRAM_API_HASH={keys['telegram_api_hash']}
"""
    
    # Опциональные API ключи
    if 'deepl' in keys:
        env_content += f"DEEPL_API_KEY={keys['deepl']}\n"
    
    if 'stability' in keys:
        env_content += f"STABILITY_API_KEY={keys['stability']}\n"
    
    # Публикация
    env_content += f"""
# === Публикация ===
OUTPUT_TELEGRAM_CHANNEL={posting['output_channel']}
POSTS_PER_DAY={posting['posts_per_day']}
MIN_INTERVAL_MINUTES={posting['min_interval']}
WORK_HOURS={posting['work_hours']}
"""
    
    # Партнерские ссылки
    if affiliate:
        affiliate_json = json.dumps(affiliate, ensure_ascii=False)
        env_content += f"""
# === Партнерские ссылки ===
AFFILIATE_LINKS={affiliate_json}
AFFILIATE_FREQUENCY={affiliate_frequency}
"""
    
    # Файловое хранилище
    env_content += f"""
# === Хранилище файлов ===
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY={minio_password}
MINIO_BUCKET=crypto-content

# === Модерация ===
HITL_WEBHOOK_URL=http://localhost:8000/hitl
ADMIN_TELEGRAM_IDS=
"""
    
    return env_content

def generate_sources_config(sources):
    """Генерация config/sources.yaml"""
    
    config = {
        'telegram_channels': sources['telegram_channels'],
        'twitter_accounts': sources['twitter_accounts'],
        'processing_rules': {
            'min_score': 0.3,
            'max_similarity': 0.8,
            'hitl_threshold': 0.7,
            'languages': ['en', 'ru'],
            'content_types': ['news', 'analysis', 'technical']
        }
    }
    
    return yaml.dump(config, default_flow_style=False, allow_unicode=True)

def create_quick_start_script():
    """Создание скрипта быстрого запуска"""
    
    script_content = """#!/bin/bash
# 🚀 Быстрый запуск системы

echo "🚀 Запуск Crypto Autoposting System..."

# Создание необходимых директорий
mkdir -p data/postgres data/redis data/minio logs backups

# Остановка предыдущих контейнеров (если есть)
docker-compose down 2>/dev/null || true

# Запуск базы данных и Redis
echo "📊 Запуск базы данных..."
docker-compose up -d postgres redis

# Ожидание готовности БД
echo "⏳ Ожидание готовности базы данных..."
sleep 15

# Инициализация БД
echo "🔧 Инициализация базы данных..."
docker-compose exec -T postgres psql -U cryptouser -d cryptodb -f /docker-entrypoint-initdb.d/init-db.sql 2>/dev/null || true

# Запуск всех сервисов
echo "🔄 Запуск всех сервисов..."
docker-compose up -d

# Проверка статуса
echo "✅ Проверка статуса сервисов..."
sleep 10
docker-compose ps

echo ""
echo "🎉 Система запущена!"
echo ""
echo "📊 Панель мониторинга: http://localhost:3000"
echo "🔧 API интерфейс: http://localhost:8000"
echo "📝 Модерация: http://localhost:8000/hitl"
echo ""
echo "📋 Проверить очереди: docker-compose exec redis redis-cli llen raw_content_queue"
echo "📋 Посмотреть логи: docker-compose logs -f worker"
echo ""
"""
    
    return script_content

def create_quick_start_windows():
    """Создание bat файла для Windows"""
    
    bat_content = """@echo off
echo 🚀 Запуск Crypto Autoposting System...

REM Создание необходимых директорий
if not exist "data\\postgres" mkdir data\\postgres
if not exist "data\\redis" mkdir data\\redis  
if not exist "data\\minio" mkdir data\\minio
if not exist "logs" mkdir logs
if not exist "backups" mkdir backups

REM Остановка предыдущих контейнеров
docker-compose down >nul 2>&1

REM Запуск базы данных
echo 📊 Запуск базы данных...
docker-compose up -d postgres redis

REM Ожидание
echo ⏳ Ожидание готовности базы данных...
timeout /t 15 /nobreak >nul

REM Инициализация БД
echo 🔧 Инициализация базы данных...
docker-compose exec -T postgres psql -U cryptouser -d cryptodb -f /docker-entrypoint-initdb.d/init-db.sql >nul 2>&1

REM Запуск всех сервисов
echo 🔄 Запуск всех сервисов...
docker-compose up -d

REM Проверка
echo ✅ Проверка статуса...
timeout /t 10 /nobreak >nul
docker-compose ps

echo.
echo 🎉 Система запущена!
echo.
echo 📊 Панель мониторинга: http://localhost:3000
echo 🔧 API интерфейс: http://localhost:8000  
echo 📝 Модерация: http://localhost:8000/hitl
echo.
pause
"""
    
    return bat_content

def main():
    print_header()
    
    try:
        # Проверка Docker
        subprocess.run(['docker', '--version'], check=True, capture_output=True)
        subprocess.run(['docker-compose', '--version'], check=True, capture_output=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("❌ ОШИБКА: Docker или Docker Compose не установлены!")
        print("   Установите Docker Desktop: https://www.docker.com/products/docker-desktop")
        return
    
    print("✅ Docker найден!")
    
    # Создание директории config если её нет
    os.makedirs('config', exist_ok=True)
    
    # Шаги настройки
    keys = step_1_api_keys()
    sources = step_2_sources()
    affiliate, affiliate_frequency = step_3_affiliate()
    posting = step_4_posting()
    
    print("\n\n🔧 ГЕНЕРАЦИЯ КОНФИГУРАЦИИ...")
    print("=" * 50)
    
    # Генерация файлов
    env_content = generate_env_file(keys, affiliate, affiliate_frequency, posting)
    sources_content = generate_sources_config(sources)
    
    # Сохранение файлов
    with open('.env', 'w', encoding='utf-8') as f:
        f.write(env_content)
    print("✅ Создан файл .env")
    
    with open('config/sources.yaml', 'w', encoding='utf-8') as f:
        f.write(sources_content)
    print("✅ Создан файл config/sources.yaml")
    
    # Создание скриптов запуска
    with open('start.sh', 'w', encoding='utf-8') as f:
        f.write(create_quick_start_script())
    os.chmod('start.sh', 0o755)
    print("✅ Создан скрипт start.sh")
    
    with open('start.bat', 'w', encoding='utf-8') as f:
        f.write(create_quick_start_windows())
    print("✅ Создан скрипт start.bat")
    
    print("\n\n🎉 НАСТРОЙКА ЗАВЕРШЕНА!")
    print("=" * 50)
    print(f"""
📋 Что было создано:
   • .env - основная конфигурация
   • config/sources.yaml - источники контента  
   • start.sh / start.bat - скрипты запуска

🚀 Как запустить:
   
   Linux/macOS:     ./start.sh
   Windows:         start.bat
   
   Или вручную:     docker-compose up -d

📊 После запуска откройте:
   • http://localhost:8000 - API интерфейс
   • http://localhost:3000 - Grafana (admin/admin)
   • http://localhost:8000/hitl - модерация

📝 Полезные команды:
   • Статус: docker-compose ps
   • Логи: docker-compose logs -f worker
   • Остановка: docker-compose down

💡 Совет: добавьте вашего бота как администратора в выходной канал!
""")

if __name__ == "__main__":
    main()
