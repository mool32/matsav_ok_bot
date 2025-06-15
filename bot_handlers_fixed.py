# bot_handlers_fixed.py - Исправленные обработчики команд и сообщений

import logging
import re
from datetime import datetime, timedelta
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ContextTypes

from config import (
    WELCOME_MESSAGE, PHRASE_REQUEST_MESSAGE, PHRASE_THANKS_MESSAGE,
    MAX_MESSAGE_LENGTH, MESSAGE_COOLDOWN, STOP_WORDS, ADMIN_ID
)
from database import (
    get_random_phrase, save_user_phrase, add_user, 
    get_phrases_count, get_pending_phrases_count, get_all_users
)
from moderation import (
    get_pending_phrases, format_pending_phrases_for_admin, 
    approve_phrase, reject_phrase, get_moderation_stats,
    get_top_contributors, batch_approve_pending
)
from matsav_tov_bot.security import security_manager

logger = logging.getLogger(__name__)

# Глобальные переменные
user_states = {}
user_cooldowns = {}
global_scheduler = None  # Глобальная переменная для планировщика

def set_global_scheduler(scheduler):
    """Устанавливаем глобальный планировщик для доступа из обработчиков"""
    global global_scheduler
    global_scheduler = scheduler
    logger.info("✅ Глобальный планировщик установлен")

def get_main_keyboard():
    """Создаем главную клавиатуру с кнопками"""
    keyboard = [
        [KeyboardButton("🌞 Получить порцию тепла")],
        [KeyboardButton("💌 Поделиться своей фразой")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def is_on_cooldown(user_id: int) -> bool:
    """Проверяем, на cooldown ли пользователь"""
    if user_id not in user_cooldowns:
        return False
    
    time_passed = datetime.now() - user_cooldowns[user_id]
    return time_passed.total_seconds() < MESSAGE_COOLDOWN

def set_cooldown(user_id: int):
    """Устанавливаем cooldown для пользователя"""
    user_cooldowns[user_id] = datetime.now()

def contains_stop_words(text: str) -> bool:
    """Проверяем содержит ли текст стоп-слова"""
    text_lower = text.lower()
    for stop_word in STOP_WORDS:
        if stop_word in text_lower:
            logger.warning(f"🚫 Найдено стоп-слово '{stop_word}' в тексте: '{text[:30]}...'")
            return True
    return False

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    user = update.effective_user
    user_id = user.id
    username = user.first_name or "Пользователь"
    
    logger.info(f"👤 {username} (ID: {user_id}) запустил команду /start")
    
    # Добавляем пользователя в базу
    add_user(user_id, username)
    
    # Сбрасываем состояние пользователя
    user_states[user_id] = "main_menu"
    
    # Отправляем приветствие с клавиатурой
    await update.message.reply_text(
        WELCOME_MESSAGE,
        reply_markup=get_main_keyboard()
    )
    
    logger.info(f"✅ Отправили приветствие пользователю {username}")

async def get_warmth_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик кнопки 'Получить порцию тепла'"""
    user = update.effective_user
    user_id = user.id
    username = user.first_name or "Пользователь"
    
    logger.info(f"🌞 {username} (ID: {user_id}) запросил порцию тепла")
    
    # Получаем случайную фразу
    phrase = get_random_phrase()
    
    # Отправляем фразу
    await update.message.reply_text(
        f"📢 מצב טוב: {phrase}",
        reply_markup=get_main_keyboard()
    )
    
    logger.info(f"✅ Отправили фразу пользователю {username}")

async def share_phrase_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик кнопки 'Поделиться своей фразой'"""
    user = update.effective_user
    user_id = user.id
    username = user.first_name or "Пользователь"
    
    logger.info(f"💌 {username} (ID: {user_id}) хочет поделиться фразой")
    
    # Проверяем cooldown
    if is_on_cooldown(user_id):
        remaining_time = MESSAGE_COOLDOWN - (datetime.now() - user_cooldowns[user_id]).total_seconds()
        remaining_minutes = int(remaining_time // 60)
        
        await update.message.reply_text(
            f"⏰ Пожалуйста, подождите ещё {remaining_minutes} минут перед отправкой новой фразы.",
            reply_markup=get_main_keyboard()
        )
        
        logger.info(f"⏰ {username} на cooldown, осталось {remaining_minutes} минут")
        return
    
    # Устанавливаем состояние ожидания фразы
    user_states[user_id] = "waiting_phrase"
    
    await update.message.reply_text(
        PHRASE_REQUEST_MESSAGE,
        reply_markup=get_main_keyboard()
    )
    
    logger.info(f"✅ Запросили фразу у пользователя {username}")

async def text_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик текстовых сообщений"""
    user = update.effective_user
    user_id = user.id
    username = user.first_name or "Пользователь"
    message_text = update.message.text
    
    # Проверяем заблокирован ли пользователь
    if security_manager.is_user_blocked(user_id):
        logger.warning(f"🚫 Заблокированный пользователь {username} (ID: {user_id}) пытался написать")
        return  # Игнорируем сообщения от заблокированных
    
    # Проверяем rate limit для сообщений
    if not security_manager.check_rate_limit(user_id, 'message'):
        await update.message.reply_text(
            "⏰ Вы отправляете сообщения слишком часто. Попробуйте позже."
        )
        logger.warning(f"⚠️ {username} превысил лимит сообщений")
        return
    
    # Логируем действие пользователя
    security_manager.log_user_action(user_id, 'message', message_text)
    
    logger.info(f"💬 {username} (ID: {user_id}) прислал сообщение: '{message_text[:50]}...'")
    
    # Проверяем состояние пользователя
    if user_id not in user_states:
        user_states[user_id] = "main_menu"
    
    current_state = user_states[user_id]
    
    # Обработка кнопок
    if message_text == "🌞 Получить порцию тепла":
        await get_warmth_handler(update, context)
        
    elif message_text == "💌 Поделиться своей фразой":
        await share_phrase_handler(update, context)
        
    # Обработка ввода фразы
    elif current_state == "waiting_phrase":
        await process_user_phrase(update, context, message_text, user_id, username)
        
    else:
        # Неизвестное сообщение
        await update.message.reply_text(
            "Используйте кнопки ниже для навигации 😊",
            reply_markup=get_main_keyboard()
        )
        
        logger.info(f"❓ {username} прислал неожиданное сообщение в состоянии {current_state}")

async def process_user_phrase(update: Update, context: ContextTypes.DEFAULT_TYPE, 
                            phrase: str, user_id: int, username: str):
    """Обрабатываем фразу от пользователя с проверкой безопасности"""
    
    # Проверяем безопасность фразы
    security_check = security_manager.auto_moderate_phrase(user_id, phrase)
    
    if not security_check['allowed']:
        # Фраза не прошла проверку безопасности
        reason = security_check['reason']
        
        if security_check['auto_block']:
            # Автоматически блокируем пользователя
            security_manager.block_user(user_id, f"Автоблокировка: {reason}")
            
            await update.message.reply_text(
                "🚫 Ваш аккаунт заблокирован за нарушение правил использования.",
                reply_markup=get_main_keyboard()
            )
            
            logger.warning(f"🚫 Заблокирован пользователь {username} (ID: {user_id}): {reason}")
            return
        
        else:
            # Просто отклоняем фразу
            await update.message.reply_text(
                f"😔 Фраза отклонена: {reason}\n"
                f"Попробуйте написать что-то более позитивное и простое.",
                reply_markup=get_main_keyboard()
            )
            
            logger.warning(f"⚠️ Отклонена фраза от {username}: {reason}")
            user_states[user_id] = "main_menu"
            return
    
    # Стандартные проверки длины
    if len(phrase) > MAX_MESSAGE_LENGTH:
        await update.message.reply_text(
            f"📝 Фраза слишком длинная! Максимум {MAX_MESSAGE_LENGTH} символов. "
            f"У вас {len(phrase)} символов.",
            reply_markup=get_main_keyboard()
        )
        
        logger.info(f"📏 {username} прислал слишком длинную фразу: {len(phrase)} символов")
        return
    
    # Проверяем на стоп-слова
    if contains_stop_words(phrase):
        await update.message.reply_text(
            "😔 К сожалению, ваша фраза содержит неподходящие слова. "
            "Попробуйте написать что-то более позитивное.",
            reply_markup=get_main_keyboard()
        )
        
        logger.warning(f"🚫 {username} прислал фразу со стоп-словами")
        user_states[user_id] = "main_menu"
        return
    
    # Проверяем на ссылки
    if re.search(r'http[s]?://|www\.|\w+\.\w+', phrase):
        await update.message.reply_text(
            "🔗 Фразы не должны содержать ссылки. "
            "Поделитесь просто добрыми словами.",
            reply_markup=get_main_keyboard()
        )
        
        logger.warning(f"🔗 {username} прислал фразу со ссылками")
        user_states[user_id] = "main_menu"
        return
    
    # Сохраняем фразу
    if save_user_phrase(user_id, username, phrase):
        # Отправляем ответ в зависимости от уровня подозрительности
        if security_check['suspicion_level'] > 0:
            await update.message.reply_text(
                "📝 Спасибо за фразу! Она будет рассмотрена дополнительно.",
                reply_markup=get_main_keyboard()
            )
            logger.info(f"📝 Фраза от {username} сохранена с подозрением (уровень {security_check['suspicion_level']})")
        else:
            await update.message.reply_text(
                PHRASE_THANKS_MESSAGE,
                reply_markup=get_main_keyboard()
            )
            logger.info(f"✅ Успешно сохранили фразу от {username}")
        
        # Устанавливаем cooldown
        set_cooldown(user_id)
        
    else:
        await update.message.reply_text(
            "😔 Произошла ошибка при сохранении. Попробуйте позже.",
            reply_markup=get_main_keyboard()
        )
        
        logger.error(f"❌ Ошибка сохранения фразы от {username}")
    
    # Сбрасываем состояние
    user_states[user_id] = "main_menu"

async def admin_stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Админская команда для просмотра статистики (только для админа)"""
    user = update.effective_user
    user_id = user.id
    username = user.first_name or "Пользователь"
    
    # Проверяем что это админ
    if user_id != ADMIN_ID:
        logger.warning(f"🚫 Не-админ {username} (ID: {user_id}) пытался получить статистику")
        await update.message.reply_text("У вас нет доступа к этой команде.")
        return
    
    logger.info(f"👑 Админ {username} запросил статистику")
    
    # Получаем подробную статистику
    phrases_count = get_phrases_count()
    pending_count = get_pending_phrases_count()
    users_count = len(get_all_users())
    
    # Получаем статистику планировщика
    scheduler_info = ""
    logger.info(f"🔍 global_scheduler состояние в admin_stats: {global_scheduler is not None}")
    
    if global_scheduler is not None:
        stats = global_scheduler.get_stats()
        next_times = global_scheduler.get_next_notifications()
        
        scheduler_info = f"""
🔔 **Рассылка:**
📤 Отправлено уведомлений: {stats['total_notifications']}
⏰ Запланировано на сегодня: {stats['scheduled_jobs']}
▶️ Статус: {'Работает' if stats['is_running'] else 'Остановлен'}
🕐 Следующие рассылки: {', '.join(next_times[:3]) if next_times else 'Не запланированы'}"""
    else:
        scheduler_info = f"""
🔔 **Рассылка:**
❌ Планировщик недоступен"""
    
    stats_message = f"""👑 **АДМИН СТАТИСТИКА**
    
📊 **База данных:**
🌞 Фраз в ротации: {phrases_count}
⏳ Ждут модерации: {pending_count}
👥 Всего пользователей: {users_count}{scheduler_info}

🔧 **Команды админа:**
/admin - общая статистика
/test_notification - тестовая рассылка
/reschedule - перепланировать рассылки

📁 **Файлы:**
• phrases.txt - основные фразы
• user_phrases.csv - фразы на модерации
• users.txt - список пользователей

✨ Для модерации новых фраз смотрите data/user_phrases.csv"""
    
    await update.message.reply_text(stats_message)
    
    logger.info(f"✅ Отправили админскую статистику")

async def admin_test_notification(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Админская команда для тестовой рассылки"""
    user = update.effective_user
    user_id = user.id
    username = user.first_name or "Пользователь"
    
    # Проверяем что это админ
    if user_id != ADMIN_ID:
        logger.warning(f"🚫 Не-админ {username} пытался отправить тестовое уведомление")
        await update.message.reply_text("У вас нет доступа к этой команде.")
        return
    
    logger.info(f"👑 Админ {username} запросил тестовое уведомление")
    logger.info(f"🔍 global_scheduler состояние: {global_scheduler is not None}")
    
    # ОТЛАДКА: проверим что за объект
    if global_scheduler is not None:
        logger.info(f"🔍 Тип global_scheduler: {type(global_scheduler)}")
        logger.info(f"🔍 Методы global_scheduler: {dir(global_scheduler)}")
    
    # Отправляем тестовое уведомление
    if global_scheduler is not None:
        try:
            success = await global_scheduler.send_test_notification(user_id)
            
            if success:
                await update.message.reply_text("✅ Тестовое уведомление отправлено!")
                logger.info("✅ Тестовое уведомление отправлено успешно")
            else:
                await update.message.reply_text("❌ Ошибка отправки тестового уведомления")
                logger.error("❌ Ошибка отправки тестового уведомления")
        except Exception as e:
            logger.error(f"❌ Исключение в test_notification: {e}")
            await update.message.reply_text(f"❌ Ошибка: {e}")
    else:
        logger.warning(f"❌ global_scheduler is None")
        await update.message.reply_text("❌ Планировщик не инициализирован")

async def admin_moderate_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Админская команда для модерации фраз"""
    user = update.effective_user
    user_id = user.id
    username = user.first_name or "Пользователь"
    
    # Проверяем что это админ
    if user_id != ADMIN_ID:
        await update.message.reply_text("У вас нет доступа к этой команде.")
        return
    
    logger.info(f"👑 Админ {username} запросил модерацию фраз")
    
    # Получаем фразы на модерации
    moderation_message = format_pending_phrases_for_admin(limit=5)
    
    await update.message.reply_text(moderation_message)
    logger.info("✅ Отправлен список фраз на модерации")

async def admin_moderation_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Админская команда для статистики модерации"""
    user = update.effective_user
    user_id = user.id
    username = user.first_name or "Пользователь"
    
    # Проверяем что это админ
    if user_id != ADMIN_ID:
        await update.message.reply_text("У вас нет доступа к этой команде.")
        return
    
    logger.info(f"👑 Админ {username} запросил статистику модерации")
    
    # Получаем статистику
    stats = get_moderation_stats()
    top_contributors = get_top_contributors()
    
    stats_message = f"""📊 **СТАТИСТИКА МОДЕРАЦИИ**

🔄 **Очередь модерации:**
⏳ Ожидают: {stats['total_pending']}
✅ Одобрено: {stats['total_approved']}
❌ Отклонено: {stats['total_rejected']}
📈 За неделю: {stats['recent_submissions']}

👥 **Топ авторов:**"""
    
    if top_contributors:
        for i, (username, count) in enumerate(top_contributors[:5]):
            stats_message += f"\n{i+1}. {username}: {count} фраз"
    else:
        stats_message += "\nПока нет одобренных фраз"
    
    stats_message += f"""

🔧 **Команды модерации:**
/moderate - список фраз
/approve_all - одобрить все качественные
/stats_moderation - эта статистика"""
    
    await update.message.reply_text(stats_message)
    logger.info("✅ Отправлена статистика модерации")

async def admin_approve_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Админская команда для пакетного одобрения фраз"""
    user = update.effective_user
    user_id = user.id
    username = user.first_name or "Пользователь"
    
    # Проверяем что это админ
    if user_id != ADMIN_ID:
        await update.message.reply_text("У вас нет доступа к этой команде.")
        return
    
    logger.info(f"👑 Админ {username} запросил пакетное одобрение")
    
    # Выполняем пакетное одобрение
    approved_count, error_count = batch_approve_pending(max_count=10)
    
    if approved_count > 0:
        await update.message.reply_text(
            f"✅ Одобрено {approved_count} фраз и добавлено в ротацию!\n"
            f"❌ Ошибок: {error_count}\n\n"
            f"Фразы прошли базовую проверку качества."
        )
        logger.info(f"✅ Пакетно одобрено {approved_count} фраз")
    else:
        await update.message.reply_text(
            "📝 Нет подходящих фраз для автоматического одобрения.\n"
            "Возможно, все требуют ручной проверки."
        )
        logger.info("📝 Нет фраз для пакетного одобрения")

async def admin_security_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Админская команда для управления безопасностью"""
    user = update.effective_user
    user_id = user.id
    username = user.first_name or "Пользователь"
    
    # Проверяем что это админ
    if user_id != ADMIN_ID:
        await update.message.reply_text("У вас нет доступа к этой команде.")
        return
    
    logger.info(f"👑 Админ {username} запросил информацию о безопасности")
    
    # Получаем статистику безопасности
    stats = security_manager.get_security_stats()
    
    security_message = f"""🔐 **БЕЗОПАСНОСТЬ БОТА**

🚫 **Заблокированные пользователи:** {stats['blocked_users']}
👥 **Отслеживаемые пользователи:** {stats['active_users_tracked']}
🔍 **Паттернов подозрительности:** {stats['suspicious_patterns_count']}

⚡ **Лимиты скорости:**
📱 Сообщений в час: {stats['rate_limits']['messages_per_hour']}
💬 Фраз в день: {stats['rate_limits']['phrases_per_day']}
⌨️ Команд в минуту: {stats['rate_limits']['commands_per_minute']}

🛡️ **Защита включает:**
• Автоматическое определение спама
• Rate limiting (ограничение частоты)
• Фильтрация подозрительного контента
• Автоматическая блокировка нарушителей

🔧 **Управление:**
/unblock [user_id] - разблокировать пользователя
/block [user_id] - заблокировать пользователя"""
    
    await update.message.reply_text(security_message)
    logger.info("✅ Отправлена информация о безопасности")

async def admin_reschedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Админская команда для перепланирования рассылок"""
    user = update.effective_user
    user_id = user.id
    username = user.first_name or "Пользователь"
    
    # Проверяем что это админ
    if user_id != ADMIN_ID:
        logger.warning(f"🚫 Не-админ {username} пытался перепланировать рассылки")
        await update.message.reply_text("У вас нет доступа к этой команде.")
        return
    
    logger.info(f"👑 Админ {username} перепланирует рассылки")
    logger.info(f"🔍 global_scheduler состояние: {global_scheduler is not None}")
    
    # Перепланируем рассылки
    if global_scheduler is not None:
        try:
            global_scheduler.reschedule_notifications()
            
            # Получаем новое расписание
            next_times = global_scheduler.get_next_notifications()
            
            await update.message.reply_text(
                f"🔄 Расписание обновлено!\n"
                f"⏰ Новые времена рассылки: {', '.join(next_times)}"
            )
            logger.info("✅ Рассылки перепланированы успешно")
            logger.info(f"📅 Новые времена: {', '.join(next_times)}")
        except Exception as e:
            logger.error(f"❌ Исключение в reschedule: {e}")
            await update.message.reply_text(f"❌ Ошибка: {e}")
    else:
        logger.warning(f"❌ global_scheduler is None в reschedule")
        await update.message.reply_text("❌ Планировщик не инициализирован")