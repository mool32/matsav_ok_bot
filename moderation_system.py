# moderation_system.py - Расширенная система модерации для оптимизированного бота

import asyncio
import aiosqlite
import logging
import re
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes, CallbackQueryHandler

from config import ADMIN_ID, STOP_WORDS

logger = logging.getLogger(__name__)

class ModerationSystem:
    """Расширенная система модерации фраз"""
    
    def __init__(self, db_path: str = "data/matsav_tov.db"):
        self.db_path = db_path
        self.current_moderation_session = {}  # user_id -> session_data
        
    async def get_pending_phrases(self, limit: int = 10, offset: int = 0) -> List[Dict]:
        """Получаем фразы на модерации"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                cursor = await db.execute("""
                    SELECT p.id, p.text, p.created_at, p.user_id, u.username
                    FROM phrases p
                    LEFT JOIN users u ON p.user_id = u.user_id
                    WHERE p.status = 'pending'
                    ORDER BY p.created_at ASC
                    LIMIT ? OFFSET ?
                """, (limit, offset))
                
                phrases = await cursor.fetchall()
                
                return [
                    {
                        'id': phrase[0],
                        'text': phrase[1],
                        'created_at': phrase[2],
                        'user_id': phrase[3],
                        'username': phrase[4] or f"User_{phrase[3]}"
                    }
                    for phrase in phrases
                ]
                
        except Exception as e:
            logger.error(f"❌ Ошибка получения фраз на модерации: {e}")
            return []
    
    async def get_moderation_stats(self) -> Dict:
        """Получаем статистику модерации"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                # Всего фраз на модерации
                cursor = await db.execute("SELECT COUNT(*) FROM phrases WHERE status = 'pending'")
                pending_count = (await cursor.fetchone())[0]
                
                # Одобренных фраз от пользователей
                cursor = await db.execute("SELECT COUNT(*) FROM phrases WHERE status = 'active' AND source = 'user'")
                approved_count = (await cursor.fetchone())[0]
                
                # Отклоненных фраз
                cursor = await db.execute("SELECT COUNT(*) FROM phrases WHERE status = 'rejected'")
                rejected_count = (await cursor.fetchone())[0]
                
                # Фразы за последние 24 часа
                cursor = await db.execute("""
                    SELECT COUNT(*) FROM phrases 
                    WHERE created_at > datetime('now', '-1 day') AND source = 'user'
                """)
                phrases_24h = (await cursor.fetchone())[0]
                
                # Топ активных пользователей по фразам
                cursor = await db.execute("""
                    SELECT u.username, COUNT(*) as phrase_count
                    FROM phrases p
                    JOIN users u ON p.user_id = u.user_id
                    WHERE p.source = 'user'
                    GROUP BY p.user_id
                    ORDER BY phrase_count DESC
                    LIMIT 5
                """)
                top_contributors = await cursor.fetchall()
                
                return {
                    'pending': pending_count,
                    'approved': approved_count,
                    'rejected': rejected_count,
                    'phrases_24h': phrases_24h,
                    'top_contributors': [(user[0], user[1]) for user in top_contributors]
                }
                
        except Exception as e:
            logger.error(f"❌ Ошибка получения статистики модерации: {e}")
            return {}
    
    async def approve_phrase(self, phrase_id: int, admin_id: int) -> bool:
        """Одобряем фразу"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                # Проверяем что фраза существует и на модерации
                cursor = await db.execute(
                    "SELECT text, user_id FROM phrases WHERE id = ? AND status = 'pending'",
                    (phrase_id,)
                )
                phrase_data = await cursor.fetchone()
                
                if not phrase_data:
                    logger.warning(f"⚠️ Фраза {phrase_id} не найдена или уже обработана")
                    return False
                
                # Одобряем фразу
                await db.execute(
                    "UPDATE phrases SET status = 'active' WHERE id = ?",
                    (phrase_id,)
                )
                
                await db.commit()
                
                phrase_text, user_id = phrase_data
                logger.info(f"✅ Админ {admin_id} одобрил фразу {phrase_id}: '{phrase_text[:50]}...' от пользователя {user_id}")
                
                return True
                
        except Exception as e:
            logger.error(f"❌ Ошибка одобрения фразы {phrase_id}: {e}")
            return False
    
    async def reject_phrase(self, phrase_id: int, admin_id: int, reason: str = "") -> bool:
        """Отклоняем фразу"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                # Проверяем что фраза существует и на модерации
                cursor = await db.execute(
                    "SELECT text, user_id FROM phrases WHERE id = ? AND status = 'pending'",
                    (phrase_id,)
                )
                phrase_data = await cursor.fetchone()
                
                if not phrase_data:
                    logger.warning(f"⚠️ Фраза {phrase_id} не найдена или уже обработана")
                    return False
                
                # Отклоняем фразу
                await db.execute(
                    "UPDATE phrases SET status = 'rejected' WHERE id = ?",
                    (phrase_id,)
                )
                
                await db.commit()
                
                phrase_text, user_id = phrase_data
                logger.info(f"❌ Админ {admin_id} отклонил фразу {phrase_id}: '{phrase_text[:50]}...' от пользователя {user_id}. Причина: {reason}")
                
                return True
                
        except Exception as e:
            logger.error(f"❌ Ошибка отклонения фразы {phrase_id}: {e}")
            return False
    
    async def auto_approve_quality_phrases(self) -> int:
        """Автоматически одобряем качественные фразы"""
        try:
            pending_phrases = await self.get_pending_phrases(limit=100)
            approved_count = 0
            
            for phrase in pending_phrases:
                if self._is_high_quality_phrase(phrase['text']):
                    success = await self.approve_phrase(phrase['id'], 0)  # 0 = автомодерация
                    if success:
                        approved_count += 1
            
            logger.info(f"🤖 Автоматически одобрено {approved_count} качественных фраз")
            return approved_count
            
        except Exception as e:
            logger.error(f"❌ Ошибка автоодобрения: {e}")
            return 0
    
    def _is_high_quality_phrase(self, text: str) -> bool:
        """Определяем высококачественные фразы для автоодобрения"""
        # Быстрые проверки
        if len(text) < 10 or len(text) > 200:
            return False
        
        # Проверяем стоп-слова
        text_lower = text.lower()
        for stop_word in STOP_WORDS:
            if stop_word in text_lower:
                return False
        
        # Проверяем ссылки
        if re.search(r'http[s]?://|www\.|\w+\.\w+', text):
            return False
        
        # Позитивные маркеры качества
        quality_markers = [
            'спасибо', 'благодарю', 'поддержка', 'сила', 'любовь', 'дружба',
            'надежда', 'вера', 'мир', 'добро', 'счастье', 'радость', 'свет',
            'тепло', 'улыбка', 'обнимаю', 'будет лучше', 'не сдавайся',
            'держись', 'справишься', 'верю в тебя', 'ты сильный', 'пройдет'
        ]
        
        positive_score = sum(1 for marker in quality_markers if marker in text_lower)
        
        # Автоодобряем если есть несколько позитивных маркеров
        return positive_score >= 2
    
    def create_moderation_keyboard(self, phrase_id: int, current_index: int, total_count: int) -> InlineKeyboardMarkup:
        """Создаем клавиатуру для модерации"""
        keyboard = [
            [
                InlineKeyboardButton("✅ Одобрить", callback_data=f"mod_approve_{phrase_id}"),
                InlineKeyboardButton("❌ Отклонить", callback_data=f"mod_reject_{phrase_id}")
            ],
            [
                InlineKeyboardButton("⏪ Предыдущая", callback_data=f"mod_prev_{current_index}"),
                InlineKeyboardButton(f"{current_index + 1}/{total_count}", callback_data="mod_noop"),
                InlineKeyboardButton("⏩ Следующая", callback_data=f"mod_next_{current_index}")
            ],
            [
                InlineKeyboardButton("📊 Статистика", callback_data="mod_stats"),
                InlineKeyboardButton("🤖 Автоодобрить", callback_data="mod_auto_approve"),
                InlineKeyboardButton("❌ Закрыть", callback_data="mod_close")
            ]
        ]
        
        return InlineKeyboardMarkup(keyboard)

# Обработчики команд для интеграции в bot_handlers_optimized.py

async def admin_moderate_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда модерации фраз"""
    user = update.effective_user
    user_id = user.id
    
    if user_id != ADMIN_ID:
        await update.message.reply_text("У вас нет доступа к этой команде.")
        return
    
    moderation = ModerationSystem()
    
    # Получаем фразы на модерации
    pending_phrases = await moderation.get_pending_phrases(limit=1)
    
    if not pending_phrases:
        await update.message.reply_text("🎉 Нет фраз на модерации!")
        return
    
    phrase = pending_phrases[0]
    
    # Сохраняем сессию модерации
    moderation.current_moderation_session[user_id] = {
        'current_index': 0,
        'total_count': len(await moderation.get_pending_phrases(limit=1000))  # Получаем общее количество
    }
    
    # Формируем сообщение
    message_text = f"""📝 **МОДЕРАЦИЯ ФРАЗЫ #{phrase['id']}**

👤 **От:** {phrase['username']} (ID: {phrase['user_id']})
📅 **Дата:** {phrase['created_at']}

💬 **Текст:**
"{phrase['text']}"

🔍 **Анализ:**
• Длина: {len(phrase['text'])} символов
• Содержит ссылки: {'Да' if re.search(r'http[s]?://|www\.', phrase['text']) else 'Нет'}
• Подозрительные слова: {'Да' if any(word in phrase['text'].lower() for word in STOP_WORDS) else 'Нет'}"""
    
    keyboard = moderation.create_moderation_keyboard(phrase['id'], 0, moderation.current_moderation_session[user_id]['total_count'])
    
    await update.message.reply_text(
        message_text,
        reply_markup=keyboard,
        parse_mode='Markdown'
    )
    
    logger.info(f"👑 Админ {user.first_name} начал модерацию")

async def admin_moderation_stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Статистика модерации"""
    user = update.effective_user
    user_id = user.id
    
    if user_id != ADMIN_ID:
        await update.message.reply_text("У вас нет доступа к этой команде.")
        return
    
    moderation = ModerationSystem()
    stats = await moderation.get_moderation_stats()
    
    message = f"""📊 **СТАТИСТИКА МОДЕРАЦИИ**

📋 **Фразы:**
• На модерации: {stats.get('pending', 0)}
• Одобрено: {stats.get('approved', 0)}
• Отклонено: {stats.get('rejected', 0)}
• За 24 часа: {stats.get('phrases_24h', 0)}

👥 **Топ авторов фраз:**"""
    
    for i, (username, count) in enumerate(stats.get('top_contributors', []), 1):
        message += f"\n{i}. {username}: {count} фраз"
    
    if not stats.get('top_contributors'):
        message += "\nПока нет данных"
    
    await update.message.reply_text(message, parse_mode='Markdown')

async def admin_auto_approve_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Автоматическое одобрение качественных фраз"""
    user = update.effective_user
    user_id = user.id
    
    if user_id != ADMIN_ID:
        await update.message.reply_text("У вас нет доступа к этой команде.")
        return
    
    await update.message.reply_text("🤖 Запускаю автоматическое одобрение...")
    
    moderation = ModerationSystem()
    approved_count = await moderation.auto_approve_quality_phrases()
    
    await update.message.reply_text(
        f"✅ Автоматически одобрено {approved_count} качественных фраз!"
    )
    
    logger.info(f"👑 Админ {user.first_name} запустил автоодобрение: {approved_count} фраз")

async def moderation_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик кнопок модерации"""
    query = update.callback_query
    user_id = query.from_user.id
    
    if user_id != ADMIN_ID:
        await query.answer("У вас нет доступа к этой функции.")
        return
    
    await query.answer()
    
    data = query.data
    moderation = ModerationSystem()
    
    try:
        if data.startswith("mod_approve_"):
            phrase_id = int(data.split("_")[2])
            success = await moderation.approve_phrase(phrase_id, user_id)
            
            if success:
                await query.edit_message_text("✅ Фраза одобрена!")
            else:
                await query.edit_message_text("❌ Ошибка при одобрении фразы.")
        
        elif data.startswith("mod_reject_"):
            phrase_id = int(data.split("_")[2])
            success = await moderation.reject_phrase(phrase_id, user_id, "Отклонено админом")
            
            if success:
                await query.edit_message_text("❌ Фраза отклонена!")
            else:
                await query.edit_message_text("❌ Ошибка при отклонении фразы.")
        
        elif data == "mod_stats":
            stats = await moderation.get_moderation_stats()
            stats_text = f"""📊 Статистика:
• На модерации: {stats.get('pending', 0)}
• Одобрено: {stats.get('approved', 0)}
• Отклонено: {stats.get('rejected', 0)}"""
            
            await query.edit_message_text(stats_text)
        
        elif data == "mod_auto_approve":
            await query.edit_message_text("🤖 Запуск автоодобрения...")
            approved_count = await moderation.auto_approve_quality_phrases()
            await query.edit_message_text(f"✅ Автоодобрено: {approved_count} фраз")
        
        elif data == "mod_close":
            await query.edit_message_text("❌ Модерация закрыта.")
        
        # Навигация между фразами можно добавить позже
        
    except Exception as e:
        logger.error(f"❌ Ошибка в обработчике модерации: {e}")
        await query.edit_message_text("❌ Произошла ошибка.")

# Функция для добавления обработчиков в main_optimized.py
def setup_moderation_handlers(application):
    """Добавляем обработчики модерации в приложение"""
    from telegram.ext import CommandHandler, CallbackQueryHandler
    
    # Команды
    application.add_handler(CommandHandler("moderate", admin_moderate_command))
    application.add_handler(CommandHandler("mod_stats", admin_moderation_stats_command))
    application.add_handler(CommandHandler("auto_approve", admin_auto_approve_command))
    
    # Обработчик кнопок
    application.add_handler(CallbackQueryHandler(moderation_callback_handler, pattern=r"^mod_"))
    
    logger.info("✅ Обработчики модерации добавлены")