# database.py - Работа с файлами данных

import os
import csv
import random
import logging
from datetime import datetime
from typing import List, Set
from config import PHRASES_FILE, USER_PHRASES_FILE, USERS_FILE

logger = logging.getLogger(__name__)

def init_data_files():
    """Создаем начальные файлы с данными если их нет"""
    
    # Создаем папку data если её нет
    os.makedirs("data", exist_ok=True)
    logger.info("📁 Проверили папку data")
    
    # Создаем файл с базовыми фразами
    if not os.path.exists(PHRASES_FILE):
        initial_phrases = [
            "Ты не обязан быть сильным всё время.",
            "Вот ты читаешь это — и уже не один.",
            "Иногда просто выдох — уже подвиг.",
            "Твои чувства важны и имеют право быть.",
            "Ошибки — это просто опыт с другим названием.",
            "Ты справился с 100% своих плохих дней до сих пор.",
            "Маленькие шаги тоже ведут к цели.",
            "Сегодня может быть трудно, но завтра — новый шанс.",
            "Ты более смелый, чем думаешь.",
            "Просто быть здесь — уже достижение.",
            "Твоё присутствие в мире что-то меняет.",
            "Отдых — это не лень, это необходимость.",
            "Ты растёшь даже тогда, когда этого не чувствуешь.",
            "Каждый день ты делаешь то, что можешь.",
            "Твоя история ещё не закончена."
        ]
        
        with open(PHRASES_FILE, 'w', encoding='utf-8') as f:
            for phrase in initial_phrases:
                f.write(phrase + '\n')
        
        logger.info(f"✅ Создали файл с базовыми фразами: {PHRASES_FILE} ({len(initial_phrases)} фраз)")
    else:
        logger.info(f"📄 Файл с фразами уже существует: {PHRASES_FILE}")
    
    # Создаем файл для пользовательских фраз (CSV)
    if not os.path.exists(USER_PHRASES_FILE):
        with open(USER_PHRASES_FILE, 'w', encoding='utf-8', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['date', 'user_id', 'username', 'phrase', 'status'])
        
        logger.info(f"✅ Создали CSV файл для пользовательских фраз: {USER_PHRASES_FILE}")
    else:
        logger.info(f"📄 CSV файл для пользовательских фраз уже существует: {USER_PHRASES_FILE}")
    
    # Создаем файл для пользователей
    if not os.path.exists(USERS_FILE):
        with open(USERS_FILE, 'w', encoding='utf-8') as f:
            pass  # Пустой файл
        
        logger.info(f"✅ Создали файл пользователей: {USERS_FILE}")
    else:
        logger.info(f"📄 Файл пользователей уже существует: {USERS_FILE}")

def get_random_phrase() -> str:
    """Получаем случайную фразу из файла"""
    try:
        with open(PHRASES_FILE, 'r', encoding='utf-8') as f:
            phrases = [line.strip() for line in f if line.strip()]
        
        if not phrases:
            logger.warning("⚠️ Файл с фразами пуст!")
            return "Ты не один. מצב טוב."
        
        selected_phrase = random.choice(phrases)
        logger.info(f"🎲 Выбрали случайную фразу: '{selected_phrase[:30]}...'")
        
        return selected_phrase
        
    except Exception as e:
        logger.error(f"❌ Ошибка при чтении фраз: {e}")
        return "Ты не один. מצב טוב."

def save_user_phrase(user_id: int, username: str, phrase: str) -> bool:
    """Сохраняем фразу от пользователя в CSV"""
    try:
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        with open(USER_PHRASES_FILE, 'a', encoding='utf-8', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([current_time, user_id, username, phrase, 'pending'])
        
        logger.info(f"💾 Сохранили фразу от {username} (ID: {user_id}): '{phrase[:50]}...'")
        return True
        
    except Exception as e:
        logger.error(f"❌ Ошибка при сохранении фразы: {e}")
        return False

def add_user(user_id: int, username: str = None) -> bool:
    """Добавляем пользователя в список"""
    try:
        # Читаем существующих пользователей
        existing_users = get_all_users()
        
        if user_id in existing_users:
            logger.info(f"👤 Пользователь {username} (ID: {user_id}) уже зарегистрирован")
            return True
        
        # Добавляем нового пользователя
        with open(USERS_FILE, 'a', encoding='utf-8') as f:
            f.write(f"{user_id}\n")
        
        logger.info(f"🆕 Добавили нового пользователя: {username} (ID: {user_id})")
        return True
        
    except Exception as e:
        logger.error(f"❌ Ошибка при добавлении пользователя: {e}")
        return False

def get_all_users() -> Set[int]:
    """Получаем всех зарегистрированных пользователей"""
    try:
        if not os.path.exists(USERS_FILE):
            return set()
        
        with open(USERS_FILE, 'r', encoding='utf-8') as f:
            users = set()
            for line in f:
                try:
                    user_id = int(line.strip())
                    users.add(user_id)
                except ValueError:
                    continue
        
        logger.info(f"📊 Загрузили {len(users)} пользователей")
        return users
        
    except Exception as e:
        logger.error(f"❌ Ошибка при чтении пользователей: {e}")
        return set()

def get_phrases_count() -> int:
    """Получаем количество доступных фраз"""
    try:
        with open(PHRASES_FILE, 'r', encoding='utf-8') as f:
            count = len([line for line in f if line.strip()])
        
        logger.info(f"📊 В базе {count} фраз")
        return count
        
    except Exception as e:
        logger.error(f"❌ Ошибка при подсчете фраз: {e}")
        return 0

def get_pending_phrases_count() -> int:
    """Получаем количество фраз ожидающих модерации"""
    try:
        with open(USER_PHRASES_FILE, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            next(reader)  # Пропускаем заголовок
            count = sum(1 for row in reader if len(row) > 4 and row[4] == 'pending')
        
        logger.info(f"📊 Ожидает модерации: {count} фраз")
        return count
        
    except Exception as e:
        logger.error(f"❌ Ошибка при подсчете фраз на модерации: {e}")
        return 0