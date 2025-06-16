# load_test.py - Нагрузочное тестирование оптимизированного бота

import asyncio
import aiosqlite
import time
import random
import logging
from datetime import datetime
from typing import List, Dict
import psutil
import os

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('load_test.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class LoadTester:
    """Класс для нагрузочного тестирования бота"""
    
    def __init__(self, db_path: str = "data/matsav_tov.db"):
        self.db_path = db_path
        self.test_results = {
            'users_created': 0,
            'phrases_retrieved': 0,
            'avg_response_time': 0,
            'errors': 0,
            'memory_usage': [],
            'cpu_usage': []
        }
    
    async def create_test_users(self, count: int) -> List[int]:
        """Создает тестовых пользователей в БД"""
        logger.info(f"🔧 Создание {count} тестовых пользователей...")
        
        start_time = time.time()
        user_ids = []
        
        try:
            async with aiosqlite.connect(self.db_path) as db:
                for i in range(count):
                    # Генерируем уникальные ID (начиная с 1000000)
                    user_id = 1000000 + i
                    username = f"LoadTest_User_{i}"
                    
                    await db.execute("""
                        INSERT OR REPLACE INTO users 
                        (user_id, username, is_active) 
                        VALUES (?, ?, 1)
                    """, (user_id, username))
                    
                    user_ids.append(user_id)
                    
                    if (i + 1) % 100 == 0:
                        logger.info(f"✅ Создано {i + 1}/{count} пользователей")
                
                await db.commit()
                
        except Exception as e:
            logger.error(f"❌ Ошибка создания пользователей: {e}")
            return []
        
        elapsed = time.time() - start_time
        self.test_results['users_created'] = count
        
        logger.info(f"✅ {count} тестовых пользователей создано за {elapsed:.2f}с")
        return user_ids
    
    async def test_phrase_retrieval(self, user_count: int, iterations: int = 1000) -> Dict:
        """Тестирует скорость получения фраз"""
        logger.info(f"🎯 Тестирование получения фраз ({iterations} запросов)")
        
        start_time = time.time()
        successful_requests = 0
        errors = 0
        response_times = []
        
        try:
            async with aiosqlite.connect(self.db_path) as db:
                for i in range(iterations):
                    request_start = time.time()
                    
                    try:
                        # Имитируем получение случайной фразы
                        cursor = await db.execute(
                            "SELECT text FROM phrases WHERE status = 'active' ORDER BY RANDOM() LIMIT 1"
                        )
                        phrase = await cursor.fetchone()
                        
                        if phrase:
                            successful_requests += 1
                        else:
                            errors += 1
                            
                    except Exception as e:
                        errors += 1
                        logger.error(f"❌ Ошибка запроса {i}: {e}")
                    
                    request_time = time.time() - request_start
                    response_times.append(request_time)
                    
                    # Мониторинг каждые 100 запросов
                    if (i + 1) % 100 == 0:
                        avg_time = sum(response_times[-100:]) / 100
                        logger.info(f"📊 {i + 1}/{iterations} - Среднее время: {avg_time*1000:.1f}ms")
                    
                    # Небольшая задержка для реалистичности
                    await asyncio.sleep(0.001)
        
        except Exception as e:
            logger.error(f"❌ Критическая ошибка тестирования: {e}")
        
        elapsed = time.time() - start_time
        avg_response_time = sum(response_times) / len(response_times) if response_times else 0
        
        results = {
            'total_requests': iterations,
            'successful_requests': successful_requests,
            'errors': errors,
            'total_time': elapsed,
            'avg_response_time': avg_response_time,
            'requests_per_second': iterations / elapsed if elapsed > 0 else 0,
            'min_response_time': min(response_times) if response_times else 0,
            'max_response_time': max(response_times) if response_times else 0
        }
        
        self.test_results.update(results)
        return results
    
    async def simulate_batch_notification(self, user_ids: List[int]) -> Dict:
        """Имитирует батч-рассылку уведомлений"""
        logger.info(f"📤 Симуляция батч-рассылки для {len(user_ids)} пользователей")
        
        batch_size = 50  # Как в реальном боте
        batch_delay = 0.5
        message_delay = 0.03
        
        start_time = time.time()
        total_sent = 0
        total_failed = 0
        
        # Разбиваем на батчи
        batches = [user_ids[i:i + batch_size] for i in range(0, len(user_ids), batch_size)]
        
        try:
            async with aiosqlite.connect(self.db_path) as db:
                # Получаем фразу для рассылки
                cursor = await db.execute(
                    "SELECT id, text FROM phrases WHERE status = 'active' ORDER BY RANDOM() LIMIT 1"
                )
                phrase_data = await cursor.fetchone()
                
                if not phrase_data:
                    logger.error("❌ Нет доступных фраз для рассылки")
                    return {}
                
                phrase_id, phrase_text = phrase_data
                logger.info(f"💌 Используем фразу: '{phrase_text[:50]}...'")
                
                # Обрабатываем батчи
                for batch_num, batch_users in enumerate(batches, 1):
                    batch_start = time.time()
                    logger.info(f"📦 Батч {batch_num}/{len(batches)} ({len(batch_users)} пользователей)")
                    
                    # Параллельно "отправляем" сообщения в батче
                    tasks = []
                    for user_id in batch_users:
                        task = self._simulate_send_message(db, user_id, phrase_id)
                        tasks.append(task)
                    
                    # Ждем выполнения всех задач в батче
                    results = await asyncio.gather(*tasks, return_exceptions=True)
                    
                    # Подсчитываем результаты
                    for result in results:
                        if isinstance(result, Exception):
                            total_failed += 1
                        elif result:
                            total_sent += 1
                        else:
                            total_failed += 1
                    
                    batch_time = time.time() - batch_start
                    logger.info(f"✅ Батч {batch_num} завершен за {batch_time:.2f}с")
                    
                    # Задержка между батчами
                    if batch_num < len(batches):
                        await asyncio.sleep(batch_delay)
        
        except Exception as e:
            logger.error(f"❌ Ошибка симуляции рассылки: {e}")
        
        elapsed = time.time() - start_time
        
        results = {
            'total_users': len(user_ids),
            'sent_count': total_sent,
            'failed_count': total_failed,
            'success_rate': (total_sent / len(user_ids)) * 100 if user_ids else 0,
            'total_time': elapsed,
            'messages_per_second': len(user_ids) / elapsed if elapsed > 0 else 0
        }
        
        logger.info(f"📊 Результаты симуляции рассылки:")
        logger.info(f"   👥 Пользователей: {results['total_users']}")
        logger.info(f"   ✅ Отправлено: {results['sent_count']}")
        logger.info(f"   ❌ Ошибок: {results['failed_count']}")
        logger.info(f"   📈 Успешность: {results['success_rate']:.1f}%")
        logger.info(f"   ⚡ Скорость: {results['messages_per_second']:.1f} сообщений/сек")
        
        return results
    
    async def _simulate_send_message(self, db: aiosqlite.Connection, user_id: int, phrase_id: int) -> bool:
        """Имитирует отправку сообщения пользователю"""
        try:
            # Имитируем задержку отправки Telegram API
            await asyncio.sleep(0.03)
            
            # Логируем "отправку"
            await db.execute("""
                INSERT INTO notification_logs 
                (user_id, phrase_id, status) 
                VALUES (?, ?, 'sent')
            """, (user_id, phrase_id))
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка отправки {user_id}: {e}")
            return False
    
    def monitor_system_resources(self) -> Dict:
        """Мониторинг системных ресурсов"""
        try:
            memory = psutil.virtual_memory()
            cpu = psutil.cpu_percent(interval=1)
            disk = psutil.disk_usage('/')
            
            resources = {
                'memory_percent': memory.percent,
                'memory_used_mb': memory.used / 1024 / 1024,
                'memory_total_mb': memory.total / 1024 / 1024,
                'cpu_percent': cpu,
                'disk_percent': disk.percent,
                'disk_free_gb': disk.free / 1024 / 1024 / 1024
            }
            
            self.test_results['memory_usage'].append(memory.percent)
            self.test_results['cpu_usage'].append(cpu)
            
            return resources
            
        except Exception as e:
            logger.error(f"❌ Ошибка мониторинга ресурсов: {e}")
            return {}
    
    async def cleanup_test_users(self, user_ids: List[int]):
        """Очищает тестовых пользователей"""
        logger.info(f"🧹 Очистка {len(user_ids)} тестовых пользователей...")
        
        try:
            async with aiosqlite.connect(self.db_path) as db:
                # Удаляем логи уведомлений
                await db.execute(
                    f"DELETE FROM notification_logs WHERE user_id IN ({','.join(['?'] * len(user_ids))})",
                    user_ids
                )
                
                # Удаляем пользователей
                await db.execute(
                    f"DELETE FROM users WHERE user_id IN ({','.join(['?'] * len(user_ids))})",
                    user_ids
                )
                
                await db.commit()
                
            logger.info("✅ Тестовые пользователи очищены")
            
        except Exception as e:
            logger.error(f"❌ Ошибка очистки: {e}")
    
    def print_final_report(self):
        """Выводит финальный отчет"""
        print("\n" + "="*60)
        print("📊 ФИНАЛЬНЫЙ ОТЧЕТ НАГРУЗОЧНОГО ТЕСТИРОВАНИЯ")
        print("="*60)
        
        print(f"👥 Создано пользователей: {self.test_results['users_created']}")
        print(f"🎯 Успешных запросов: {self.test_results.get('successful_requests', 0)}")
        print(f"❌ Ошибок: {self.test_results.get('errors', 0)}")
        print(f"⚡ Среднее время ответа: {self.test_results.get('avg_response_time', 0)*1000:.1f}ms")
        print(f"📈 Запросов в секунду: {self.test_results.get('requests_per_second', 0):.1f}")
        
        if self.test_results['memory_usage']:
            avg_memory = sum(self.test_results['memory_usage']) / len(self.test_results['memory_usage'])
            max_memory = max(self.test_results['memory_usage'])
            print(f"💾 Среднее использование памяти: {avg_memory:.1f}%")
            print(f"💾 Пиковое использование памяти: {max_memory:.1f}%")
        
        if self.test_results['cpu_usage']:
            avg_cpu = sum(self.test_results['cpu_usage']) / len(self.test_results['cpu_usage'])
            max_cpu = max(self.test_results['cpu_usage'])
            print(f"🔥 Среднее использование CPU: {avg_cpu:.1f}%")
            print(f"🔥 Пиковое использование CPU: {max_cpu:.1f}%")
        
        print("="*60)

async def run_load_test():
    """Основная функция нагрузочного тестирования"""
    print("🧪 ЗАПУСК НАГРУЗОЧНОГО ТЕСТИРОВАНИЯ")
    print("="*50)
    
    tester = LoadTester()
    
    # Конфигурация тестов
    test_configs = [
        {'users': 100, 'name': 'Малая нагрузка'},
        {'users': 500, 'name': 'Средняя нагрузка'},
        {'users': 1000, 'name': 'Высокая нагрузка'},
    ]
    
    for config in test_configs:
        user_count = config['users']
        test_name = config['name']
        
        print(f"\n🎯 {test_name} ({user_count} пользователей)")
        print("-" * 40)
        
        try:
            # Мониторинг ресурсов до теста
            resources_before = tester.monitor_system_resources()
            logger.info(f"📊 Ресурсы до теста: CPU {resources_before.get('cpu_percent', 0):.1f}%, "
                       f"RAM {resources_before.get('memory_percent', 0):.1f}%")
            
            # Создание тестовых пользователей
            user_ids = await tester.create_test_users(user_count)
            
            if not user_ids:
                logger.error(f"❌ Не удалось создать пользователей для теста {test_name}")
                continue
            
            # Тестирование получения фраз
            phrase_results = await tester.test_phrase_retrieval(user_count, iterations=200)
            
            # Симуляция рассылки
            notification_results = await tester.simulate_batch_notification(user_ids)
            
            # Мониторинг ресурсов после теста
            resources_after = tester.monitor_system_resources()
            logger.info(f"📊 Ресурсы после теста: CPU {resources_after.get('cpu_percent', 0):.1f}%, "
                       f"RAM {resources_after.get('memory_percent', 0):.1f}%")
            
            # Очистка
            await tester.cleanup_test_users(user_ids)
            
            print(f"✅ {test_name} завершен успешно!")
            
        except Exception as e:
            logger.error(f"❌ Ошибка в тесте {test_name}: {e}")
        
        # Пауза между тестами
        await asyncio.sleep(2)
    
    # Финальный отчет
    tester.print_final_report()

if __name__ == "__main__":
    # Проверка наличия базы данных
    if not os.path.exists("data/matsav_tov.db"):
        print("❌ База данных не найдена. Убедитесь что бот запускался хотя бы раз.")
        exit(1)
    
    asyncio.run(run_load_test())