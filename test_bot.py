# test_bot.py - Простой тест бота

import asyncio
import logging
import os
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from config import BOT_TOKEN, LOG_FILE

# Настройка логирования
def setup_logging():
    """Настраиваем логирование в файл и консоль"""
    # Создаем папку logs если её нет
    os.makedirs("logs", exist_ok=True)
    
    # Настройка формата логов
    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    
    # Настройка логирования
    logging.basicConfig(
        level=logging.INFO,
        format=log_format,
        handlers=[
            logging.FileHandler(LOG_FILE, encoding='utf-8'),  # В файл
            logging.StreamHandler()  # В консоль
        ]
    )
    
    return logging.getLogger(__name__)

logger = setup_logging()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    user_id = update.effective_user.id
    user_name = update.effective_user.first_name
    
    logger.info(f"👤 Пользователь {user_name} (ID: {user_id}) запустил команду /start")
    
    await update.message.reply_text("🤖 Привет! Тестовый бот работает! מצב טוב")
    
    logger.info(f"✅ Отправили приветствие пользователю {user_name}")

async def hello(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /hello"""
    user_id = update.effective_user.id
    user_name = update.effective_user.first_name
    
    logger.info(f"👤 Пользователь {user_name} (ID: {user_id}) запустил команду /hello")
    
    await update.message.reply_text(f"Привет, {user_name}! 👋")
    
    logger.info(f"✅ Поздоровались с пользователем {user_name}")

def main():
    """Главная функция"""
    logger.info("🚀 Запускаем тестового бота...")
    logger.info(f"📁 Логи сохраняются в: {LOG_FILE}")
    
    try:
        # Создаем приложение
        application = Application.builder().token(BOT_TOKEN).build()
        
        # Добавляем обработчики
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("hello", hello))
        
        logger.info("✅ Обработчики команд добавлены")
        logger.info("🔄 Бот запущен и ожидает сообщения...")
        print("✅ Бот запущен! Нажмите Ctrl+C для остановки")
        print(f"📊 Логи в реальном времени: {LOG_FILE}")
        
        # Запускаем бота
        application.run_polling()
        
    except Exception as e:
        logger.error(f"❌ Ошибка при запуске бота: {e}")
        print(f"❌ Ошибка: {e}")
    
    finally:
        logger.info("🛑 Бот остановлен")

if __name__ == "__main__":
    main()