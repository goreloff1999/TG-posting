#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Простое управление системой
"""

import subprocess
import sys
import argparse

def run_command(cmd, description):
    """Выполнить команду с описанием"""
    print(f"🔄 {description}...")
    try:
        result = subprocess.run(cmd, shell=True, check=True, capture_output=True, text=True)
        print(f"✅ {description} - готово!")
        if result.stdout:
            print(result.stdout)
    except subprocess.CalledProcessError as e:
        print(f"❌ Ошибка: {e}")
        if e.stderr:
            print(e.stderr)
        return False
    return True

def status():
    """Показать статус системы"""
    print("📊 Статус системы:")
    run_command("docker-compose ps", "Проверка контейнеров")
    
    print("\n📈 Очереди:")
    run_command("docker-compose exec redis redis-cli llen raw_content_queue", "Входящий контент")
    run_command("docker-compose exec redis redis-cli llen processing_queue", "Обработка")
    run_command("docker-compose exec redis redis-cli llen publishing_queue", "Публикация")

def start():
    """Запустить систему"""
    run_command("mkdir -p data/postgres data/redis data/minio logs", "Создание директорий")
    run_command("docker-compose up -d postgres redis", "Запуск БД")
    print("⏳ Ожидание готовности БД...")
    run_command("sleep 15", "Ожидание")
    run_command("docker-compose exec -T postgres psql -U cryptouser -d cryptodb -f /docker-entrypoint-initdb.d/init-db.sql", "Инициализация БД")
    run_command("docker-compose up -d", "Запуск всех сервисов")
    
    print("\n🎉 Система запущена!")
    print("📊 Панель: http://localhost:3000")
    print("🔧 API: http://localhost:8000")
    print("📝 Модерация: http://localhost:8000/hitl")

def stop():
    """Остановить систему"""
    run_command("docker-compose down", "Остановка системы")

def restart():
    """Перезапустить систему"""
    stop()
    start()

def logs():
    """Показать логи"""
    print("📋 Логи системы (Ctrl+C для выхода):")
    subprocess.run("docker-compose logs -f worker api", shell=True)

def backup():
    """Создать бэкап"""
    from datetime import datetime
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    run_command("mkdir -p backups", "Создание папки бэкапов")
    run_command(f"docker-compose exec postgres pg_dump -U cryptouser cryptodb > backups/db_backup_{timestamp}.sql", "Бэкап базы данных")
    print(f"💾 Бэкап сохранен: backups/db_backup_{timestamp}.sql")

def health():
    """Проверка здоровья системы"""
    print("🏥 Проверка здоровья системы:")
    
    checks = [
        ("curl -s http://localhost:8000/health", "API доступен"),
        ("docker-compose exec postgres pg_isready", "PostgreSQL работает"),
        ("docker-compose exec redis redis-cli ping", "Redis работает"),
        ("curl -s http://localhost:9000/minio/health/live", "MinIO доступен"),
    ]
    
    for cmd, desc in checks:
        if run_command(cmd, desc):
            print(f"✅ {desc}")
        else:
            print(f"❌ {desc}")

def main():
    parser = argparse.ArgumentParser(description='Управление Crypto Autoposting System')
    parser.add_argument('command', choices=['start', 'stop', 'restart', 'status', 'logs', 'backup', 'health'], 
                       help='Команда для выполнения')
    
    if len(sys.argv) == 1:
        print("""
🚀 Crypto Autoposting System - Управление

Доступные команды:
  start    - Запустить систему
  stop     - Остановить систему  
  restart  - Перезапустить систему
  status   - Показать статус
  logs     - Показать логи (в реальном времени)
  backup   - Создать бэкап базы данных
  health   - Проверить здоровье системы

Примеры:
  python manage.py start
  python manage.py status
  python manage.py logs
        """)
        return
    
    args = parser.parse_args()
    
    commands = {
        'start': start,
        'stop': stop,
        'restart': restart,
        'status': status,
        'logs': logs,
        'backup': backup,
        'health': health
    }
    
    commands[args.command]()

if __name__ == "__main__":
    main()
