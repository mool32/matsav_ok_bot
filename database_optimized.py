# database_optimized.py - Оптимизированная база данных с SQLite (ИСПРАВЛЕННАЯ)

import asyncio
import aiosqlite
import logging
import os
import random
from datetime import datetime, timedelta
from typing import List, Set, Dict, Optional
from dataclasses import dataclass
import time

from config import PHRASES_FILE

logger = logging.getLogger(__name__)

@dataclass
class User:
    user_id: int
    username: str
    first_seen: datetime
    last_activity: datetime
    is_active: bool = True

@dataclass
class Phrase:
    id: int
    text: str
    source: str  # 'system' или 'user'
    status: str  # 'active', 'pending', 'rejected'
    created_at: datetime
    user_id: Optional[int] = None

class OptimizedDatabase:
    """Оптимизированная база данных для масштабирования"""
    
    def __init__(self, db_path: str = "data/matsav_tov.db"):
        self.db_path = db_path
        self._phrase_cache = {}
        self._cache_timestamp = 0
        self._cache_ttl = 300  # 5 минут
        
        # Создаем папку если нужно
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
    
    async def init_database(self):
        """Инициализируем базу данных"""
        try:
            # ИСПРАВЛЕНИЕ: Сначала настраиваем PRAGMA вне транзакции
            async with aiosqlite.connect(self.db_path) as db:
                # Включаем WAL режим для лучшей производительности
                await db.execute("PRAGMA journal_mode=WAL")
                await db.execute("PRAGMA synchronous=NORMAL") 
                await db.execute("PRAGMA cache_size=10000")
                await db.execute("PRAGMA temp_store=memory")
            
            # Затем создаем таблицы и мигрируем данные
            async with aiosqlite.connect(self.db_path) as db:
                await self._create_tables(db)
                await self._migrate_from_files(db)
                await db.commit()
            
            logger.info("✅ База данных инициализирована")
            
        except Exception as e:
            logger.error(f"❌ Ошибка инициализации БД: {e}")
            raise
    
    async def _create_tables(self, db: aiosqlite.Connection):
        """Создаем таблицы"""
        
        # Пользователи
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_active BOOLEAN DEFAULT 1,
                notification_count INTEGER DEFAULT 0
            )
        """)
        
        # Фразы
        await db.execute("""
            CREATE TABLE IF NOT EXISTS phrases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                text TEXT NOT NULL UNIQUE,
                source TEXT DEFAULT 'system',
                status TEXT DEFAULT 'active',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                user_id INTEGER,
                usage_count INTEGER DEFAULT 0,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        """)
        
        # Логи уведомлений
        await db.execute("""
            CREATE TABLE IF NOT EXISTS notification_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                phrase_id INTEGER NOT NULL,
                sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                status TEXT DEFAULT 'sent',
                error_message TEXT,
                retry_count INTEGER DEFAULT 0,
                FOREIGN KEY (user_id) REFERENCES users (user_id),
                FOREIGN KEY (phrase_id) REFERENCES phrases (id)
            )
        """)
        
        # Создаем индексы для производительности
        await db.execute("CREATE INDEX IF NOT EXISTS idx_users_active ON users(is_active)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_phrases_status ON phrases(status)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_notifications_status ON notification_logs(status)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_notifications_user ON notification_logs(user_id)")
    
    async def _migrate_from_files(self, db: aiosqlite.Connection):
        """Мигрируем данные из файлов"""
        try:
            # Проверяем есть ли уже данные
            cursor = await db.execute("SELECT COUNT(*) FROM phrases")
            count = await cursor.fetchone()
            if count[0] > 0:
                return  # Данные уже есть
            
            # Мигрируем фразы из файла
            if os.path.exists(PHRASES_FILE):
                with open(PHRASES_FILE, 'r', encoding='utf-8') as f:
                    phrases = [line.strip() for line in f if line.strip()]
                
                for phrase in phrases:
                    await db.execute(
                        "INSERT OR IGNORE INTO phrases (text, source, status) VALUES (?, ?, ?)",
                        (phrase, 'system', 'active')
                    )
                
                logger.info(f"📥 Мигрировали {len(phrases)} системных фраз")
            
            # Мигрируем пользователей из файла
            users_file = "data/users.txt"
            if os.path.exists(users_file):
                with open(users_file, 'r', encoding='utf-8') as f:
                    user_ids = [int(line.strip()) for line in f if line.strip().isdigit()]
                
                for user_id in user_ids:
                    await db.execute(
                        "INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)",
                        (user_id, f"User_{user_id}")
                    )
                
                logger.info(f"📥 Мигрировали {len(user_ids)} пользователей")
            
        except Exception as e:
            logger.error(f"❌ Ошибка миграции: {e}")
    
    async def add_user(self, user_id: int, username: str = None) -> bool:
        """Добавляем пользователя"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("""
                    INSERT OR REPLACE INTO users 
                    (user_id, username, last_activity) 
                    VALUES (?, ?, CURRENT_TIMESTAMP)
                """, (user_id, username or f"User_{user_id}"))
                await db.commit()
            
            logger.info(f"👤 Добавлен/обновлен пользователь {username} (ID: {user_id})")
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка добавления пользователя: {e}")
            return False
    
    async def get_active_users(self) -> List[int]:
        """Получаем активных пользователей"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                cursor = await db.execute(
                    "SELECT user_id FROM users WHERE is_active = 1"
                )
                users = await cursor.fetchall()
                return [user[0] for user in users]
                
        except Exception as e:
            logger.error(f"❌ Ошибка получения пользователей: {e}")
            return []
    
    async def get_random_phrase(self) -> Optional[str]:
        """Получаем случайную фразу с кэшированием"""
        try:
            # Проверяем кэш
            current_time = time.time()
            if (current_time - self._cache_timestamp) > self._cache_ttl or not self._phrase_cache:
                await self._refresh_phrase_cache()
            
            if not self._phrase_cache:
                return "Ты не один. מצב טוב."
            
            # Выбираем случайную фразу
            phrase_data = random.choice(list(self._phrase_cache.values()))
            
            # Обновляем счетчик использования асинхронно
            asyncio.create_task(self._increment_phrase_usage(phrase_data['id']))
            
            return phrase_data['text']
            
        except Exception as e:
            logger.error(f"❌ Ошибка получения фразы: {e}")
            return "Ты не один. מצב טוב."
    
    async def _refresh_phrase_cache(self):
        """Обновляем кэш фраз"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                cursor = await db.execute(
                    "SELECT id, text FROM phrases WHERE status = 'active'"
                )
                phrases = await cursor.fetchall()
                
                self._phrase_cache = {
                    phrase[0]: {'id': phrase[0], 'text': phrase[1]} 
                    for phrase in phrases
                }
                self._cache_timestamp = time.time()
                
                logger.info(f"🔄 Кэш фраз обновлен: {len(self._phrase_cache)} фраз")
                
        except Exception as e:
            logger.error(f"❌ Ошибка обновления кэша: {e}")
    
    async def _increment_phrase_usage(self, phrase_id: int):
        """Увеличиваем счетчик использования фразы"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    "UPDATE phrases SET usage_count = usage_count + 1 WHERE id = ?",
                    (phrase_id,)
                )
                await db.commit()
        except Exception as e:
            logger.error(f"❌ Ошибка обновления счетчика: {e}")
    
    async def save_user_phrase(self, user_id: int, username: str, phrase: str) -> bool:
        """Сохраняем фразу от пользователя"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("""
                    INSERT INTO phrases (text, source, status, user_id) 
                    VALUES (?, 'user', 'pending', ?)
                """, (phrase, user_id))
                await db.commit()
            
            logger.info(f"💾 Сохранили фразу от {username}: '{phrase[:50]}...'")
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка сохранения фразы: {e}")
            return False
    
    async def log_notification(self, user_id: int, phrase_id: int, status: str, error: str = None):
        """Логируем отправку уведомления"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("""
                    INSERT INTO notification_logs 
                    (user_id, phrase_id, status, error_message) 
                    VALUES (?, ?, ?, ?)
                """, (user_id, phrase_id, status, error))
                
                # Обновляем счетчик уведомлений у пользователя
                if status == 'sent':
                    await db.execute(
                        "UPDATE users SET notification_count = notification_count + 1 WHERE user_id = ?",
                        (user_id,)
                    )
                
                await db.commit()
                
        except Exception as e:
            logger.error(f"❌ Ошибка логирования уведомления: {e}")
    
    async def mark_user_inactive(self, user_id: int):
        """Помечаем пользователя как неактивного (заблокировал бота)"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    "UPDATE users SET is_active = 0 WHERE user_id = ?",
                    (user_id,)
                )
                await db.commit()
            
            logger.info(f"🚫 Пользователь {user_id} помечен как неактивный")
            
        except Exception as e:
            logger.error(f"❌ Ошибка деактивации пользователя: {e}")
    
    async def get_stats(self) -> Dict:
        """Получаем статистику базы данных"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                # Пользователи
                cursor = await db.execute("SELECT COUNT(*) FROM users WHERE is_active = 1")
                active_users = (await cursor.fetchone())[0]
                
                cursor = await db.execute("SELECT COUNT(*) FROM users")
                total_users = (await cursor.fetchone())[0]
                
                # Фразы
                cursor = await db.execute("SELECT COUNT(*) FROM phrases WHERE status = 'active'")
                active_phrases = (await cursor.fetchone())[0]
                
                cursor = await db.execute("SELECT COUNT(*) FROM phrases WHERE status = 'pending'")
                pending_phrases = (await cursor.fetchone())[0]
                
                # Уведомления за последние 24 часа
                cursor = await db.execute("""
                    SELECT COUNT(*) FROM notification_logs 
                    WHERE sent_at > datetime('now', '-1 day') AND status = 'sent'
                """)
                notifications_24h = (await cursor.fetchone())[0]
                
                # Неудачные уведомления
                cursor = await db.execute("SELECT COUNT(*) FROM notification_logs WHERE status = 'failed'")
                failed_notifications = (await cursor.fetchone())[0]
                
                return {
                    'active_users': active_users,
                    'total_users': total_users,
                    'active_phrases': active_phrases,
                    'pending_phrases': pending_phrases,
                    'notifications_24h': notifications_24h,
                    'failed_notifications': failed_notifications,
                    'cache_size': len(self._phrase_cache)
                }
                
        except Exception as e:
            logger.error(f"❌ Ошибка получения статистики: {e}")
            return {}

# Глобальный экземпляр оптимизированной БД
optimized_db = OptimizedDatabase()