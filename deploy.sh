#!/bin/bash
# deploy.sh - Автоматический деплой бота "Мацав Тов" на VPS

set -e  # Остановка при ошибке

echo "🚀 Начинаем деплой оптимизированного бота 'Мацав Тов'"
echo "=================================================="

# Переменные (настройте под ваш сервер)
BOT_USER="matsav"
BOT_DIR="/opt/matsav_tov_bot"
SERVICE_NAME="matsav-tov"
PYTHON_VERSION="3.9"

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

print_status() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

# Проверка прав root
if [[ $EUID -ne 0 ]]; then
   print_error "Скрипт должен запускаться с правами root"
   exit 1
fi

print_status "Проверка системы..."

# Обновление системы
apt update && apt upgrade -y
print_status "Система обновлена"

# Установка зависимостей
apt install -y python3 python3-pip python3-venv git systemd nginx htop
print_status "Зависимости установлены"

# Создание пользователя для бота
if ! id "$BOT_USER" &>/dev/null; then
    useradd -r -s /bin/false -d "$BOT_DIR" "$BOT_USER"
    print_status "Создан пользователь $BOT_USER"
else
    print_warning "Пользователь $BOT_USER уже существует"
fi

# Создание директорий
mkdir -p "$BOT_DIR"/{data,logs,backups}
print_status "Созданы директории"

# Клонирование или обновление кода
if [ -d "$BOT_DIR/.git" ]; then
    cd "$BOT_DIR"
    git pull
    print_status "Код обновлен"
else
    print_warning "Скопируйте файлы проекта в $BOT_DIR"
    print_warning "Или клонируйте: git clone [ваш_репозиторий] $BOT_DIR"
fi

# Создание виртуального окружения
cd "$BOT_DIR"
if [ ! -d "venv" ]; then
    python3 -m venv venv
    print_status "Виртуальное окружение создано"
fi

# Активация и установка зависимостей
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements_optimized.txt
print_status "Python зависимости установлены"

# Настройка прав доступа
chown -R "$BOT_USER:$BOT_USER" "$BOT_DIR"
chmod -R 755 "$BOT_DIR"
chmod -R 750 "$BOT_DIR/data" "$BOT_DIR/logs"
print_status "Права доступа настроены"

# Создание systemd сервиса
cat > "/etc/systemd/system/${SERVICE_NAME}.service" << EOF
[Unit]
Description=Matsav Tov Telegram Bot (Optimized)
After=network.target

[Service]
Type=simple
User=$BOT_USER
Group=$BOT_USER
WorkingDirectory=$BOT_DIR
Environment=PATH=$BOT_DIR/venv/bin
Environment=BOT_TOKEN=${BOT_TOKEN:-TOKEN_NOT_SET}
Environment=ADMIN_ID=${ADMIN_ID:-472118566}
Environment=PRODUCTION=true
ExecStart=$BOT_DIR/venv/bin/python main_optimized.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

# Ограничения ресурсов
MemoryMax=512M
CPUQuota=50%

# Безопасность
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=$BOT_DIR

[Install]
WantedBy=multi-user.target
EOF

print_status "Systemd сервис создан"

# Перезагрузка systemd
systemctl daemon-reload
systemctl enable "$SERVICE_NAME"
print_status "Сервис включен в автозагрузку"

# Создание скрипта бэкапа
cat > "$BOT_DIR/backup.sh" << 'EOF'
#!/bin/bash
# Автоматический бэкап базы данных

BACKUP_DIR="/opt/matsav_tov_bot/backups"
DB_FILE="/opt/matsav_tov_bot/data/matsav_tov.db"
DATE=$(date +%Y%m%d_%H%M%S)

# Создание бэкапа SQLite
if [ -f "$DB_FILE" ]; then
    sqlite3 "$DB_FILE" ".backup $BACKUP_DIR/matsav_tov_${DATE}.db"
    echo "✅ Бэкап создан: matsav_tov_${DATE}.db"
    
    # Удаление старых бэкапов (старше 30 дней)
    find "$BACKUP_DIR" -name "matsav_tov_*.db" -mtime +30 -delete
    echo "🧹 Старые бэкапы очищены"
else
    echo "❌ База данных не найдена: $DB_FILE"
    exit 1
fi
EOF

chmod +x "$BOT_DIR/backup.sh"
chown "$BOT_USER:$BOT_USER" "$BOT_DIR/backup.sh"
print_status "Скрипт бэкапа создан"

# Добавление в crontab для бэкапов каждые 6 часов
(crontab -u "$BOT_USER" -l 2>/dev/null; echo "0 */6 * * * $BOT_DIR/backup.sh >> $BOT_DIR/logs/backup.log 2>&1") | crontab -u "$BOT_USER" -
print_status "Автоматические бэкапы настроены (каждые 6 часов)"

# Создание скрипта мониторинга
cat > "$BOT_DIR/monitor.sh" << 'EOF'
#!/bin/bash
# Мониторинг бота

SERVICE="matsav-tov"
LOG_FILE="/opt/matsav_tov_bot/logs/monitor.log"
DATE=$(date '+%Y-%m-%d %H:%M:%S')

# Проверка статуса сервиса
if systemctl is-active --quiet "$SERVICE"; then
    echo "[$DATE] ✅ Сервис $SERVICE работает" >> "$LOG_FILE"
else
    echo "[$DATE] ❌ Сервис $SERVICE не работает! Перезапускаем..." >> "$LOG_FILE"
    systemctl restart "$SERVICE"
    sleep 5
    if systemctl is-active --quiet "$SERVICE"; then
        echo "[$DATE] ✅ Сервис $SERVICE перезапущен успешно" >> "$LOG_FILE"
    else
        echo "[$DATE] 🚨 КРИТИЧНО: Не удалось перезапустить $SERVICE" >> "$LOG_FILE"
        # Здесь можно добавить отправку email/SMS алерта
    fi
fi

# Проверка использования ресурсов
MEMORY=$(ps -o pid,user,%mem,command -C python3 | grep matsav | awk '{print $3}')
if [ ! -z "$MEMORY" ]; then
    echo "[$DATE] 📊 Использование памяти: ${MEMORY}%" >> "$LOG_FILE"
    
    # Алерт при превышении 80% памяти
    if (( $(echo "$MEMORY > 80" | bc -l) )); then
        echo "[$DATE] ⚠️ ВНИМАНИЕ: Высокое использование памяти: ${MEMORY}%" >> "$LOG_FILE"
    fi
fi
EOF

chmod +x "$BOT_DIR/monitor.sh"
chown "$BOT_USER:$BOT_USER" "$BOT_DIR/monitor.sh"

# Добавление мониторинга в crontab каждые 5 минут
(crontab -u root -l 2>/dev/null; echo "*/5 * * * * $BOT_DIR/monitor.sh") | crontab -u root -
print_status "Мониторинг настроен (каждые 5 минут)"

print_status "=================================================="
print_status "🎉 Деплой завершен!"
echo ""
print_warning "ВАЖНО: Не забудьте:"
echo "1. Установить переменные окружения BOT_TOKEN и ADMIN_ID"
echo "2. Скопировать файлы проекта в $BOT_DIR"
echo "3. Запустить: systemctl start $SERVICE_NAME"
echo ""
print_status "Полезные команды:"
echo "• Статус: systemctl status $SERVICE_NAME"
echo "• Логи: journalctl -u $SERVICE_NAME -f"
echo "• Перезапуск: systemctl restart $SERVICE_NAME"
echo "• Мониторинг: tail -f $BOT_DIR/logs/bot.log"
echo "• Бэкапы: ls -la $BOT_DIR/backups/"
echo ""
print_status "Система готова к production! 🚀"