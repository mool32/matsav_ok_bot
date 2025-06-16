# main_optimized.py - Оптимизированный главный файл для масштабирования

import asyncio
import logging
import os
import signal
import sys
from telegram.ext import Application, CommandHandler, MessageHandler, filters

from config import BOT_TOKEN, LOG_FILE
from database_optimized import optimized_db
from scheduler_optimized import OptimizedNotificationScheduler

def setup_logging():
    """Настраиваем продвинутое логирование"""
    # Создаем папки
    os.makedirs("logs", exist_ok=True)
    
    # Формат логов с больше информации
    log_format = '%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s'
    
    # Настройка логирования с ротацией
    from logging.handlers import RotatingFileHandler
    
    # Ротирующий файловый хендлер (макс 10MB, 5 файлов)
    file_handler = RotatingFileHandler(
        LOG_FILE, 
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(logging.Formatter(log_format))
    
    # Консольный хендлер
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(logging.Formatter(log_format))
    
    # Настройка root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)
    
    # Уменьшаем логи от сторонних библиотек
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("telegram").setLevel(logging.WARNING)
    logging.getLogger("apscheduler").setLevel(logging.WARNING)
    
    return logging.getLogger(__name__)

class OptimizedMatsavTovBot:
    """Оптимизированный класс бота"""
    
    def __init__(self):
        self.logger = setup_logging()
        self.application = None
        self.scheduler = None
        self.shutdown_event = asyncio.Event()
        
    async def initialize(self):
        """Асинхронная инициализация"""
        self.logger.info("🚀 Инициализация оптимизированного бота...")
        
        try:
            # Инициализируем базу данных
            self.logger.info("📂 Инициализация оптимизированной БД...")
            await optimized_db.init_database()
            self.logger.info("✅ База данных готова")
            
            # Создаем приложение
            self.logger.info("🔧 Создание приложения бота...")
            self.application = Application.builder().token(BOT_TOKEN).build()
            
            # Инициализируем планировщик
            self.logger.info("📅 Инициализация оптимизированного планировщика...")
            self.scheduler = OptimizedNotificationScheduler(self.application)
            
            # Устанавливаем глобальный планировщик для обработчиков
            from bot_handlers_optimized import set_global_scheduler
            set_global_scheduler(self.scheduler)
            
            # Добавляем обработчики
            self._setup_handlers()
            
            self.logger.info("✅ Инициализация завершена")
            
        except Exception as e:
            self.logger.error(f"❌ Ошибка инициализации: {e}")
            raise
    
    def _setup_handlers(self):
        """Настраиваем обработчики команд"""
        self.logger.info("⚙️ Настройка обработчиков...")
        
        from bot_handlers_optimized import (
            start_command, text_message_handler, admin_stats_command,
            admin_test_notification, admin_test_soon, admin_reschedule
        )
        
        # Пользовательские команды
        self.application.add_handler(CommandHandler("start", start_command))
        
        # Админские команды
        self.application.add_handler(CommandHandler("admin", admin_stats_command))
        self.application.add_handler(CommandHandler("test_notification", admin_test_notification))
        self.application.add_handler(CommandHandler("test_soon", admin_test_soon))
        self.application.add_handler(CommandHandler("reschedule", admin_reschedule))
        
        # Обработчик текстовых сообщений
        self.application.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, text_message_handler)
        )
        
        self.logger.info("✅ Обработчики настроены")
    
    async def start(self):
        """Запускаем бота"""
        try:
            # Запускаем планировщик
            self.logger.info("🚀 Запуск планировщика...")
            self.scheduler.start()
            
            # Выводим информацию о запуске
            self._print_startup_info()
            
            # Запускаем бота
            self.logger.info("🔄 Запуск бота...")
            await self.application.initialize()
            await self.application.start()
            await self.application.updater.start_polling(drop_pending_updates=True)
            
            self.logger.info("✅ Бот запущен и работает")
            
            # Ждем сигнала остановки
            await self.shutdown_event.wait()
            
        except Exception as e:
            self.logger.error(f"❌ Ошибка запуска: {e}")
            raise
    
    def _print_startup_info(self):
        """Выводим информацию о запуске"""
        print("=" * 60)
        print("🤖 МАЦАВ ТОВ БОТ (ОПТИМИЗИРОВАННАЯ ВЕРСИЯ)")
        print("=" * 60)
        print("✅ Бот успешно запущен!")
        print(f"📊 Логи: {LOG_FILE}")
        print("🔔 Автоматическая рассылка активна")
        print("🚀 Оптимизирован для большого количества пользователей")
        print("")
        print("👑 Админские команды:")
        print("   /admin - расширенная статистика")
        print("   /test_notification - тест рассылки")
        print("   /test_soon - тест через 1 минуту")
        print("   /reschedule - перепланировать рассылки")
        print("")
        print("🛑 Для остановки: Ctrl+C")
        print("=" * 60)
    
    async def stop(self):
        """Корректная остановка бота"""
        self.logger.info("🛑 Начинаем корректную остановку...")
        
        try:
            # Останавливаем планировщик
            if self.scheduler:
                self.scheduler.stop()
                self.logger.info("✅ Планировщик остановлен")
            
            # Останавливаем приложение
            if self.application:
                await self.application.updater.stop()
                await self.application.stop()
                await self.application.shutdown()
                self.logger.info("✅ Приложение остановлено")
            
            self.logger.info("🏁 Корректная остановка завершена")
            
        except Exception as e:
            self.logger.error(f"❌ Ошибка при остановке: {e}")
        
        finally:
            self.shutdown_event.set()
    
    def setup_signal_handlers(self):
        """Настраиваем обработчики сигналов"""
        def signal_handler(signum, frame):
            self.logger.info(f"🛑 Получен сигнал {signum}")
            asyncio.create_task(self.stop())
        
        # Регистрируем обработчики сигналов (только для Unix)
        if hasattr(signal, 'SIGTERM'):
            signal.signal(signal.SIGTERM, signal_handler)
        if hasattr(signal, 'SIGINT'):
            signal.signal(signal.SIGINT, signal_handler)

async def run_bot():
    """Основная асинхронная функция"""
    bot = OptimizedMatsavTovBot()
    
    try:
        # Настраиваем обработчики сигналов
        bot.setup_signal_handlers()
        
        # Инициализируем
        await bot.initialize()
        
        # Запускаем
        await bot.start()
        
    except KeyboardInterrupt:
        bot.logger.info("🛑 Получен сигнал остановки от пользователя")
        
    except Exception as e:
        bot.logger.error(f"❌ Критическая ошибка: {e}")
        
    finally:
        await bot.stop()
        print("\n👋 Оптимизированный бот остановлен!")

def main():
    """Главная функция"""
    try:
        # Устанавливаем политику событий для Windows
        if sys.platform.startswith('win'):
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        
        # Запускаем основной цикл
        asyncio.run(run_bot())
        
    except KeyboardInterrupt:
        print("\n🛑 Остановка по запросу пользователя")
        
    except Exception as e:
        print(f"❌ Критическая ошибка: {e}")
        
    finally:
        print("🏁 Завершение работы")

if __name__ == "__main__":
    main()