# scheduler.py - Автоматическая рассылка фраз

import asyncio
import logging
import random
from datetime import datetime, time
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from telegram.error import TelegramError

from config import DAILY_NOTIFICATIONS
from database import get_random_phrase, get_all_users

logger = logging.getLogger(__name__)

class NotificationScheduler:
    """Класс для управления автоматической рассылкой"""
    
    def __init__(self, bot_application):
        """Инициализация планировщика"""
        self.bot = bot_application.bot
        self.scheduler = AsyncIOScheduler()
        self.notification_count = 0
        
        logger.info("📅 Инициализируем планировщик рассылки")
    
    def start(self):
        """Запускаем планировщик с расписанием рассылок"""
        try:
            # Планируем рассылки на каждый день
            self.schedule_daily_notifications()
            
            # Запускаем планировщик
            self.scheduler.start()
            
            logger.info("✅ Планировщик рассылки запущен")
            logger.info(f"🎯 Запланировано {DAILY_NOTIFICATIONS} уведомления в день")
            
        except Exception as e:
            logger.error(f"❌ Ошибка запуска планировщика: {e}")
    
    def schedule_daily_notifications(self):
        """Планируем случайные рассылки на каждый день"""
        
        # Временные интервалы для рассылки (чтобы не спамить)
        time_slots = [
            (9, 11),   # Утро: 9:00-11:00
            (12, 14),  # Обед: 12:00-14:00
            (15, 17),  # День: 15:00-17:00
            (18, 20),  # Вечер: 18:00-20:00
            (21, 22),  # Поздний вечер: 21:00-22:00
        ]
        
        # Планируем рассылки в случайное время из каждого слота
        for i in range(DAILY_NOTIFICATIONS):
            if i < len(time_slots):
                start_hour, end_hour = time_slots[i]
            else:
                # Если нужно больше уведомлений, используем случайные часы
                start_hour, end_hour = random.choice(time_slots)
            
            # Случайное время в интервале
            random_hour = random.randint(start_hour, end_hour)
            random_minute = random.randint(0, 59)
            
            # Добавляем задачу в планировщик
            self.scheduler.add_job(
                self.send_daily_notification,
                trigger=CronTrigger(hour=random_hour, minute=random_minute),
                id=f"daily_notification_{i}",
                replace_existing=True,
                max_instances=1
            )
            
            logger.info(f"📅 Запланировано уведомление #{i+1} на {random_hour:02d}:{random_minute:02d}")
    
    async def send_daily_notification(self):
        """Отправляем ежедневное уведомление всем пользователям"""
        try:
            # Получаем всех пользователей
            users = get_all_users()
            
            if not users:
                logger.warning("👥 Нет зарегистрированных пользователей для рассылки")
                return
            
            # Получаем случайную фразу
            phrase = get_random_phrase()
            
            # Форматируем сообщение
            notification_message = f"📢 מצב טוב: {phrase}"
            
            # Счетчики для статистики
            sent_count = 0
            error_count = 0
            
            logger.info(f"📤 Начинаем рассылку для {len(users)} пользователей")
            logger.info(f"💌 Отправляем: '{phrase[:50]}...'")
            
            # Отправляем всем пользователям
            for user_id in users:
                try:
                    await self.bot.send_message(
                        chat_id=user_id,
                        text=notification_message
                    )
                    sent_count += 1
                    
                    # Небольшая пауза между отправками (чтобы не нарушать лимиты Telegram)
                    await asyncio.sleep(0.1)
                    
                except TelegramError as e:
                    error_count += 1
                    logger.warning(f"⚠️ Не удалось отправить пользователю {user_id}: {e}")
                    
                    # Если пользователь заблокировал бота, можно его удалить из списка
                    if "blocked" in str(e).lower():
                        logger.info(f"🚫 Пользователь {user_id} заблокировал бота")
                        # TODO: Можно добавить удаление из списка пользователей
                
                except Exception as e:
                    error_count += 1
                    logger.error(f"❌ Неожиданная ошибка при отправке пользователю {user_id}: {e}")
            
            # Логируем результаты рассылки
            self.notification_count += 1
            
            logger.info(f"✅ Рассылка #{self.notification_count} завершена")
            logger.info(f"📊 Отправлено: {sent_count}, Ошибок: {error_count}")
            
            if sent_count > 0:
                logger.info(f"🎉 {sent_count} человек получили порцию тепла!")
            
        except Exception as e:
            logger.error(f"❌ Критическая ошибка в рассылке: {e}")
    
    async def send_test_notification(self, user_id: int):
        """Отправляем тестовое уведомление (для отладки)"""
        try:
            phrase = get_random_phrase()
            test_message = f"🧪 ТЕСТ: מצב טוב: {phrase}"
            
            await self.bot.send_message(
                chat_id=user_id,
                text=test_message
            )
            
            logger.info(f"✅ Тестовое уведомление отправлено пользователю {user_id}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка отправки тестового уведомления: {e}")
            return False
    
    def get_next_notifications(self):
        """Получаем информацию о следующих запланированных рассылках"""
        try:
            jobs = self.scheduler.get_jobs()
            
            next_times = []
            for job in jobs:
                if job.id.startswith("daily_notification"):
                    next_run = job.next_run_time
                    if next_run:
                        next_times.append(next_run.strftime("%H:%M"))
            
            next_times.sort()
            return next_times
            
        except Exception as e:
            logger.error(f"❌ Ошибка получения расписания: {e}")
            return []
    
    def reschedule_notifications(self):
        """Перепланируем уведомления (на случай изменения настроек)"""
        try:
            # Удаляем старые задачи
            for job in self.scheduler.get_jobs():
                if job.id.startswith("daily_notification"):
                    job.remove()
            
            # Планируем заново
            self.schedule_daily_notifications()
            
            logger.info("🔄 Расписание рассылки обновлено")
            
        except Exception as e:
            logger.error(f"❌ Ошибка перепланирования: {e}")
    
    def stop(self):
        """Останавливаем планировщик"""
        try:
            self.scheduler.shutdown(wait=False)
            logger.info("🛑 Планировщик рассылки остановлен")
            
        except Exception as e:
            logger.error(f"❌ Ошибка остановки планировщика: {e}")
    
    def get_stats(self):
        """Получаем статистику рассылок"""
        return {
            "total_notifications": self.notification_count,
            "scheduled_jobs": len([j for j in self.scheduler.get_jobs() if j.id.startswith("daily_notification")]),
            "is_running": self.scheduler.running
        }