# scheduler_optimized.py - Оптимизированный планировщик рассылки

import asyncio
import logging
import random
from datetime import datetime, time, timedelta
from typing import List, Dict, Optional
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from telegram.error import TelegramError, Forbidden, ChatMigrated, RetryAfter
import time as time_module

from config import DAILY_NOTIFICATIONS
from database_optimized import optimized_db

logger = logging.getLogger(__name__)

class OptimizedNotificationScheduler:
    """Оптимизированный планировщик рассылки для большого количества пользователей"""
    
    def __init__(self, bot_application):
        self.bot = bot_application.bot
        self.scheduler = AsyncIOScheduler()
        self.notification_count = 0
        self.is_sending = False
        self.stats = {
            'total_sent': 0,
            'total_failed': 0,
            'last_batch_time': None,
            'average_batch_time': 0,
            'retry_queue_size': 0
        }
        
        # Настройки для оптимизации
        self.batch_size = 50  # Размер батча для рассылки
        self.batch_delay = 0.5  # Задержка между батчами (секунды)
        self.message_delay = 0.03  # Задержка между сообщениями (30ms)
        self.max_retries = 3
        self.retry_delay = 300  # 5 минут между повторными попытками
        
        logger.info("📅 Оптимизированный планировщик инициализирован")
    
    def start(self):
        """Запускаем планировщик"""
        try:
            # Планируем основные рассылки
            self.schedule_daily_notifications()
            
            # Планируем обработку неудачных отправок
            self.schedule_retry_failed_notifications()
            
            # Запускаем планировщик
            self.scheduler.start()
            
            logger.info("✅ Оптимизированный планировщик запущен")
            logger.info(f"🎯 Настройки: батч {self.batch_size}, задержка {self.batch_delay}с")
            
        except Exception as e:
            logger.error(f"❌ Ошибка запуска планировщика: {e}")
    
    def schedule_daily_notifications(self):
        """Планируем ежедневные рассылки"""
        
        # Временные интервалы для рассылок
        time_slots = [
            (7, 9),    # Раннее утро
            (9, 11),   # Утро
            (11, 13),  # Поздее утро
            (13, 15),  # Обед
            (15, 17),  # День
            (17, 19),  # Поздний день
            (19, 21),  # Вечер
            (21, 23),  # Поздний вечер
        ]
        
        # Планируем нужное количество рассылок
        used_slots = random.sample(time_slots, min(DAILY_NOTIFICATIONS, len(time_slots)))
        
        for i, (start_hour, end_hour) in enumerate(used_slots):
            # Случайное время в интервале
            random_hour = random.randint(start_hour, end_hour - 1)
            random_minute = random.randint(0, 59)
            
            # Добавляем задачу
            self.scheduler.add_job(
                self.send_batch_notification,
                trigger=CronTrigger(hour=random_hour, minute=random_minute),
                id=f"daily_notification_{i}",
                replace_existing=True,
                max_instances=1
            )
            
            logger.info(f"📅 Рассылка #{i+1} запланирована на {random_hour:02d}:{random_minute:02d}")
    
    def schedule_retry_failed_notifications(self):
        """Планируем повторные попытки отправки"""
        self.scheduler.add_job(
            self.retry_failed_notifications,
            trigger=CronTrigger(minute='*/10'),  # Каждые 10 минут
            id="retry_failed_notifications",
            replace_existing=True,
            max_instances=1
        )
        
        logger.info("🔄 Запланированы повторные попытки отправки (каждые 10 минут)")
    
    async def send_batch_notification(self):
        """Отправляем уведомления батчами"""
        if self.is_sending:
            logger.warning("⚠️ Предыдущая рассылка еще не завершена, пропускаем")
            return
        
        self.is_sending = True
        start_time = time_module.time()
        
        try:
            # Получаем пользователей и фразу
            users = await optimized_db.get_active_users()
            phrase = await optimized_db.get_random_phrase()
            
            if not users:
                logger.warning("👥 Нет активных пользователей для рассылки")
                return
            
            if not phrase:
                logger.error("💬 Не удалось получить фразу для рассылки")
                return
            
            # Логируем начало рассылки
            self.notification_count += 1
            total_users = len(users)
            
            logger.info(f"📤 Рассылка #{self.notification_count} начата")
            logger.info(f"👥 Получателей: {total_users}")
            logger.info(f"💌 Фраза: '{phrase[:50]}...'")
            
            # Разбиваем пользователей на батчи
            batches = [users[i:i + self.batch_size] for i in range(0, len(users), self.batch_size)]
            
            sent_count = 0
            failed_count = 0
            
            # Отправляем батчами
            for batch_num, batch_users in enumerate(batches, 1):
                logger.info(f"📦 Обрабатываем батч {batch_num}/{len(batches)} ({len(batch_users)} пользователей)")
                
                # Отправляем батч
                batch_sent, batch_failed = await self._send_batch(batch_users, phrase)
                sent_count += batch_sent
                failed_count += batch_failed
                
                # Задержка между батчами (кроме последнего)
                if batch_num < len(batches):
                    await asyncio.sleep(self.batch_delay)
            
            # Обновляем статистику
            elapsed_time = time_module.time() - start_time
            self.stats['total_sent'] += sent_count
            self.stats['total_failed'] += failed_count
            self.stats['last_batch_time'] = elapsed_time
            
            # Вычисляем среднее время
            if self.stats['average_batch_time'] == 0:
                self.stats['average_batch_time'] = elapsed_time
            else:
                self.stats['average_batch_time'] = (self.stats['average_batch_time'] + elapsed_time) / 2
            
            # Логируем результаты
            logger.info(f"✅ Рассылка #{self.notification_count} завершена за {elapsed_time:.1f}с")
            logger.info(f"📊 Отправлено: {sent_count}, Ошибок: {failed_count}")
            
            if sent_count > 0:
                logger.info(f"🎉 {sent_count} человек получили порцию тепла!")
            
        except Exception as e:
            logger.error(f"❌ Критическая ошибка в рассылке: {e}")
            
        finally:
            self.is_sending = False
    
    async def _send_batch(self, user_ids: List[int], phrase: str) -> tuple[int, int]:
        """Отправляем батч пользователям"""
        sent_count = 0
        failed_count = 0
        
        # Создаем задачи для параллельной отправки
        tasks = []
        for user_id in user_ids:
            task = asyncio.create_task(self._send_to_user(user_id, phrase))
            tasks.append(task)
        
        # Ждем выполнения всех задач
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Обрабатываем результаты
        for user_id, result in zip(user_ids, results):
            if isinstance(result, Exception):
                failed_count += 1
                logger.error(f"❌ Ошибка отправки пользователю {user_id}: {result}")
            elif result:
                sent_count += 1
            else:
                failed_count += 1
        
        return sent_count, failed_count
    
    async def _send_to_user(self, user_id: int, phrase: str) -> bool:
        """Отправляем сообщение одному пользователю"""
        try:
            await self.bot.send_message(
                chat_id=user_id,
                text=phrase
            )
            
            # Логируем успешную отправку
            await optimized_db.log_notification(user_id, 0, 'sent')
            
            # Небольшая задержка для соблюдения лимитов Telegram
            await asyncio.sleep(self.message_delay)
            
            return True
            
        except Forbidden:
            # Пользователь заблокировал бота
            await optimized_db.mark_user_inactive(user_id)
            logger.info(f"🚫 Пользователь {user_id} заблокировал бота")
            return False
            
        except RetryAfter as e:
            # Превышен лимит - ждем
            wait_time = min(e.retry_after, 60)  # Максимум минута
            logger.warning(f"⏰ Rate limit для {user_id}, ждем {wait_time}с")
            await asyncio.sleep(wait_time)
            
            # Повторная попытка
            try:
                await self.bot.send_message(chat_id=user_id, text=phrase)
                await optimized_db.log_notification(user_id, 0, 'sent')
                return True
            except Exception as retry_error:
                await optimized_db.log_notification(user_id, 0, 'failed', str(retry_error))
                return False
            
        except ChatMigrated as e:
            # Чат мигрировал - обновляем ID
            new_chat_id = e.new_chat_id
            logger.info(f"📱 Чат мигрировал: {user_id} -> {new_chat_id}")
            return False
            
        except TelegramError as e:
            # Другие ошибки Telegram
            error_msg = str(e)
            await optimized_db.log_notification(user_id, 0, 'failed', error_msg)
            
            if "blocked" in error_msg.lower():
                await optimized_db.mark_user_inactive(user_id)
            
            return False
            
        except Exception as e:
            # Неожиданные ошибки
            await optimized_db.log_notification(user_id, 0, 'failed', str(e))
            logger.error(f"❌ Неожиданная ошибка при отправке {user_id}: {e}")
            return False
    
    async def retry_failed_notifications(self):
        """Повторная отправка неудачных уведомлений"""
        try:
            # Здесь можно добавить логику получения неудачных уведомлений из БД
            # и их повторную отправку
            logger.debug("🔄 Проверка неудачных уведомлений")
            
        except Exception as e:
            logger.error(f"❌ Ошибка повторной отправки: {e}")
    
    async def send_test_notification(self, user_id: int) -> bool:
        """Отправляем тестовое уведомление"""
        try:
            phrase = await optimized_db.get_random_phrase()
            test_message = f"🧪 ТЕСТ: {phrase}"
            
            success = await self._send_to_user(user_id, test_message)
            
            if success:
                logger.info(f"✅ Тестовое уведомление отправлено {user_id}")
            
            return success
            
        except Exception as e:
            logger.error(f"❌ Ошибка тестового уведомления: {e}")
            return False
    
    def schedule_test_notification(self, minutes_from_now: int = 1) -> str:
        """Планируем тестовое уведомление"""
        from datetime import datetime, timedelta
        
        test_time = datetime.now() + timedelta(minutes=minutes_from_now)
        
        self.scheduler.add_job(
            self.send_batch_notification,
            trigger=CronTrigger(
                hour=test_time.hour,
                minute=test_time.minute
            ),
            id="test_notification_scheduled",
            replace_existing=True,
            max_instances=1
        )
        
        time_str = test_time.strftime('%H:%M')
        logger.info(f"🧪 Тестовая рассылка запланирована на {time_str}")
        return time_str
    
    def get_next_notifications(self) -> List[str]:
        """Получаем следующие запланированные рассылки"""
        try:
            jobs = self.scheduler.get_jobs()
            next_times = []
            
            for job in jobs:
                if job.id.startswith("daily_notification") or "test" in job.id:
                    if job.next_run_time:
                        next_times.append(job.next_run_time.strftime("%H:%M"))
            
            return sorted(next_times)
            
        except Exception as e:
            logger.error(f"❌ Ошибка получения расписания: {e}")
            return []
    
    def reschedule_notifications(self):
        """Перепланируем уведомления"""
        try:
            # Удаляем старые задачи рассылок
            for job in self.scheduler.get_jobs():
                if job.id.startswith("daily_notification"):
                    job.remove()
            
            # Планируем заново
            self.schedule_daily_notifications()
            
            logger.info("🔄 Расписание рассылки обновлено")
            
        except Exception as e:
            logger.error(f"❌ Ошибка перепланирования: {e}")
    
    def get_stats(self) -> Dict:
        """Получаем статистику планировщика"""
        return {
            "total_notifications": self.notification_count,
            "scheduled_jobs": len([j for j in self.scheduler.get_jobs() if j.id.startswith("daily_notification")]),
            "is_running": self.scheduler.running,
            "is_sending": self.is_sending,
            "total_sent": self.stats['total_sent'],
            "total_failed": self.stats['total_failed'],
            "last_batch_time": self.stats['last_batch_time'],
            "average_batch_time": round(self.stats['average_batch_time'], 2),
            "retry_queue_size": self.stats['retry_queue_size'],
            "batch_size": self.batch_size
        }
    
    def stop(self):
        """Останавливаем планировщик"""
        try:
            self.scheduler.shutdown(wait=False)
            logger.info("🛑 Оптимизированный планировщик остановлен")
            
        except Exception as e:
            logger.error(f"❌ Ошибка остановки планировщика: {e}")