# moderation.py - Инструменты модерации фраз

import csv
import logging
import os
from datetime import datetime
from typing import List, Dict, Tuple

from config import USER_PHRASES_FILE, PHRASES_FILE

logger = logging.getLogger(__name__)

def get_pending_phrases() -> List[Dict]:
    """Получаем все фразы ожидающие модерации"""
    pending_phrases = []
    
    try:
        if not os.path.exists(USER_PHRASES_FILE):
            return []
        
        with open(USER_PHRASES_FILE, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get('status') == 'pending':
                    pending_phrases.append({
                        'id': len(pending_phrases),  # Простой ID для ссылки
                        'date': row.get('date', ''),
                        'user_id': row.get('user_id', ''),
                        'username': row.get('username', ''),
                        'phrase': row.get('phrase', ''),
                        'status': row.get('status', '')
                    })
        
        logger.info(f"📄 Загружено {len(pending_phrases)} фраз на модерации")
        return pending_phrases
        
    except Exception as e:
        logger.error(f"❌ Ошибка загрузки фраз на модерации: {e}")
        return []

def get_phrases_by_status(status: str) -> List[Dict]:
    """Получаем фразы по статусу (pending, approved, rejected)"""
    phrases = []
    
    try:
        if not os.path.exists(USER_PHRASES_FILE):
            return []
        
        with open(USER_PHRASES_FILE, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get('status') == status:
                    phrases.append({
                        'date': row.get('date', ''),
                        'user_id': row.get('user_id', ''),
                        'username': row.get('username', ''),
                        'phrase': row.get('phrase', ''),
                        'status': row.get('status', '')
                    })
        
        return phrases
        
    except Exception as e:
        logger.error(f"❌ Ошибка загрузки фраз со статусом {status}: {e}")
        return []

def update_phrase_status(phrase_text: str, new_status: str, moderator_note: str = "") -> bool:
    """Обновляем статус фразы"""
    try:
        # Читаем все строки
        rows = []
        updated = False
        
        with open(USER_PHRASES_FILE, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames
            
            # Добавляем поля если их нет
            if 'moderator_note' not in fieldnames:
                fieldnames.append('moderator_note')
            if 'moderation_date' not in fieldnames:
                fieldnames.append('moderation_date')
            
            for row in reader:
                if row['phrase'] == phrase_text and row['status'] == 'pending':
                    row['status'] = new_status
                    row['moderator_note'] = moderator_note
                    row['moderation_date'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    updated = True
                    logger.info(f"📝 Обновили статус фразы '{phrase_text[:30]}...' на '{new_status}'")
                
                rows.append(row)
        
        if not updated:
            logger.warning(f"⚠️ Фраза не найдена для обновления: '{phrase_text[:30]}...'")
            return False
        
        # Записываем обновленные данные
        with open(USER_PHRASES_FILE, 'w', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Ошибка обновления статуса фразы: {e}")
        return False

def approve_phrase(phrase_text: str, add_to_rotation: bool = True) -> bool:
    """Одобряем фразу и опционально добавляем в ротацию"""
    try:
        # Обновляем статус
        if not update_phrase_status(phrase_text, 'approved', 'Одобрено модератором'):
            return False
        
        # Добавляем в ротацию если нужно
        if add_to_rotation:
            with open(PHRASES_FILE, 'a', encoding='utf-8') as f:
                f.write(phrase_text + '\n')
            
            logger.info(f"✅ Фраза добавлена в ротацию: '{phrase_text[:30]}...'")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Ошибка одобрения фразы: {e}")
        return False

def reject_phrase(phrase_text: str, reason: str = "Не соответствует стандартам") -> bool:
    """Отклоняем фразу"""
    return update_phrase_status(phrase_text, 'rejected', reason)

def get_moderation_stats() -> Dict:
    """Получаем статистику модерации"""
    stats = {
        'total_pending': 0,
        'total_approved': 0,
        'total_rejected': 0,
        'recent_submissions': 0  # За последние 7 дней
    }
    
    try:
        if not os.path.exists(USER_PHRASES_FILE):
            return stats
        
        recent_date = (datetime.now() - datetime.timedelta(days=7)).strftime("%Y-%m-%d")
        
        with open(USER_PHRASES_FILE, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                status = row.get('status', '')
                date = row.get('date', '')
                
                if status == 'pending':
                    stats['total_pending'] += 1
                elif status == 'approved':
                    stats['total_approved'] += 1
                elif status == 'rejected':
                    stats['total_rejected'] += 1
                
                # Проверяем recent submissions
                if date >= recent_date:
                    stats['recent_submissions'] += 1
        
        logger.info(f"📊 Статистика модерации: {stats}")
        return stats
        
    except Exception as e:
        logger.error(f"❌ Ошибка получения статистики модерации: {e}")
        return stats

def format_pending_phrases_for_admin(limit: int = 5) -> str:
    """Форматируем фразы на модерации для админа"""
    pending = get_pending_phrases()
    
    if not pending:
        return "✅ Нет фраз ожидающих модерации!"
    
    message = f"📝 **Фразы на модерации ({len(pending)} всего):**\n\n"
    
    # Показываем только первые несколько
    for i, phrase_data in enumerate(pending[:limit]):
        date = phrase_data['date'][:10]  # Только дата без времени
        username = phrase_data['username']
        phrase = phrase_data['phrase']
        
        message += f"**{i+1}.** {phrase}\n"
        message += f"   👤 {username} • 📅 {date}\n\n"
    
    if len(pending) > limit:
        message += f"... и ещё {len(pending) - limit} фраз\n\n"
    
    message += "🔧 **Команды:**\n"
    message += "/moderate - подробный просмотр\n"
    message += "/approve_all - одобрить все\n"
    message += "/stats_moderation - статистика"
    
    return message

def get_top_contributors() -> List[Tuple[str, int]]:
    """Получаем топ авторов по количеству одобренных фраз"""
    contributors = {}
    
    try:
        approved_phrases = get_phrases_by_status('approved')
        
        for phrase_data in approved_phrases:
            username = phrase_data.get('username', 'Неизвестный')
            contributors[username] = contributors.get(username, 0) + 1
        
        # Сортируем по количеству
        top_contributors = sorted(contributors.items(), key=lambda x: x[1], reverse=True)
        
        return top_contributors[:10]  # Топ 10
        
    except Exception as e:
        logger.error(f"❌ Ошибка получения топ авторов: {e}")
        return []

def batch_approve_pending(max_count: int = 10) -> Tuple[int, int]:
    """Пакетное одобрение фраз (для качественных фраз)"""
    pending = get_pending_phrases()
    approved_count = 0
    error_count = 0
    
    for phrase_data in pending[:max_count]:
        phrase_text = phrase_data['phrase']
        
        # Простые проверки качества
        if len(phrase_text) < 10:  # Слишком короткая
            continue
        if phrase_text.count('!') > 3:  # Слишком много восклицательных знаков
            continue
        
        if approve_phrase(phrase_text, add_to_rotation=True):
            approved_count += 1
            logger.info(f"✅ Автоматически одобрена: '{phrase_text[:30]}...'")
        else:
            error_count += 1
    
    return approved_count, error_count