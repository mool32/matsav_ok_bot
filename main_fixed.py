# main_fixed.py - Исправленная версия главного файла

import asyncio
import logging
import os
from telegram.ext import Application, CommandHandler, MessageHandler, filters

from config import BOT_TOKEN, LOG_FILE
from database import init_data_files
from scheduler import NotificationScheduler

def setup_logging():
    """Настраиваем логирование"""
    # Создаем папку logs если её нет
    os.makedirs("logs", exist_ok=True)
    
    # Настройка формата логов
    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    
    # Настройка логирования
    logging.basicConfig(
        level=logging.INFO,
        format=log_format,
        handlers=[
            logging.FileHandler(LOG_FILE, encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
    
    # Уменьшаем логи от httpx (слишком много HTTP запросов)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    
    return logging.getLogger(__name__)

def main():
    """Главная функция запуска бота"""
    logger = setup_logging()
    
    logger.info("🚀 Запускаем бота Мацав Тов...")
    logger.info(f"📁 Логи сохраняются в: {LOG_FILE}")
    
    try:
        # Инициализируем файлы данных
        logger.info("📂 Инициализируем файлы данных...")
        init_data_files()
        
        # Создаем приложение
        logger.info("🔧 Создаем приложение бота...")
        application = Application.builder().token(BOT_TOKEN).build()
        
        # Инициализируем планировщик рассылки
        logger.info("📅 Инициализируем планировщик рассылки...")
        scheduler = NotificationScheduler(application)
        logger.info("✅ Планировщик создан")
        
        # Сохраняем планировщик в bot_data для доступа из обработчиков
        application.bot_data['scheduler'] = scheduler
        logger.info("💾 Планировщик сохранён в bot_data")
        
        # Устанавливаем глобальный планировщик ПОСЛЕ импорта
        logger.info("🔧 Устанавливаем глобальный планировщик...")
        
        # Импортируем обработчики и устанавливаем планировщик
        from bot_handlers_fixed import (
            start_command, text_message_handler, admin_stats_command,
            admin_test_notification, admin_reschedule, set_global_scheduler,
            admin_moderate_command, admin_moderation_stats, admin_approve_all,
            admin_security_command
        )
        
        set_global_scheduler(scheduler)
        logger.info("✅ Глобальный планировщик установлен в main.py")
        
        # Добавляем обработчики
        logger.info("⚙️ Добавляем обработчики команд...")
        
        # Команда /start
        application.add_handler(CommandHandler("start", start_command))
        
        # Админские команды
        application.add_handler(CommandHandler("admin", admin_stats_command))
        application.add_handler(CommandHandler("test_notification", admin_test_notification))
        application.add_handler(CommandHandler("reschedule", admin_reschedule))
        
        # Команды модерации
        application.add_handler(CommandHandler("moderate", admin_moderate_command))
        application.add_handler(CommandHandler("stats_moderation", admin_moderation_stats))
        application.add_handler(CommandHandler("approve_all", admin_approve_all))
        
        # Команды безопасности
        application.add_handler(CommandHandler("security", admin_security_command))
        
        # Обработчик всех текстовых сообщений
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_message_handler))
        
        logger.info("✅ Все обработчики добавлены")
        
        # Запускаем планировщик рассылки
        logger.info("🚀 Запускаем планировщик рассылки...")
        scheduler.start()
        
        logger.info("🔄 Бот запущен и ожидает сообщения...")
        
        print("=" * 50)
        print("🤖 МАЦАВ ТОВ БОТ ЗАПУЩЕН")
        print("=" * 50)
        print("✅ Бот работает!")
        print(f"📊 Логи: {LOG_FILE}")
        print("🔔 Автоматическая рассылка активна")
        print("👑 Админские команды:")
        print("   /admin - общая статистика")
        print("   /test_notification - тест рассылки")
        print("   /reschedule - перепланировать")
        print("📝 Модерация:")
        print("   /moderate - фразы на модерации")
        print("   /stats_moderation - статистика модерации")
        print("   /approve_all - одобрить качественные")
        print("🔐 Безопасность:")
        print("   /security - статистика безопасности")
        print("🛑 Для остановки: Ctrl+C")
        print("=" * 50)
        
        # Запускаем бота
        application.run_polling(drop_pending_updates=True)
        
    except KeyboardInterrupt:
        logger.info("🛑 Получен сигнал остановки")
        print("\n🛑 Бот остановлен пользователем")
        
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}")
        print(f"❌ Ошибка: {e}")
        
    finally:
        # Останавливаем планировщик при завершении
        if 'scheduler' in locals():
            scheduler.stop()
        
        logger.info("🏁 Завершение работы бота")
        print("👋 До свидания!")

if __name__ == "__main__":
    main()