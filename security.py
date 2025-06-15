# security.py - Защита от спама и безопасность

import json
import logging
import os
import re
from datetime import datetime, timedelta
from typing import Dict, Set, List
from collections import defaultdict

logger = logging.getLogger(__name__)

# Файлы для хранения данных безопасности
SECURITY_DATA_FILE = "data/security.json"
BLOCKED_USERS_FILE = "data/blocked_users.txt"

class SecurityManager:
    """Менеджер безопасности бота"""
    
    def __init__(self):
        self.user_actions = defaultdict(list)  # История действий пользователей
        self.blocked_users = set()
        self.suspicious_patterns = []
        self.rate_limits = {
            'messages_per_hour': 10,
            'phrases_per_day': 3,
            'commands_per_minute': 5
        }
        
        self.load_security_data()
        self.load_blocked_users()
        self._init_suspicious_patterns()
    
    def _init_suspicious_patterns(self):
        """Инициализируем паттерны подозрительного поведения"""
        self.suspicious_patterns = [
            # Спам паттерны
            r'(.)\1{5,}',  # Повторяющиеся символы (aaaaa)
            r'[!]{3,}',    # Много восклицательных знаков
            r'[?]{3,}',    # Много вопросительных знаков
            r'[A-ZА-Я]{10,}',  # Много заглавных букв подряд
            
            # Подозрительные ссылки
            r'bit\.ly|tinyurl|t\.me/\w+',
            r'@\w+',  # Упоминания пользователей
            
            # Реклама
            r'куп[иы]|продаж|скидк|акция|реклам',
            r'деньги|доход|заработ|млн|тысяч',
            r'телеграм[- ]?канал|подписыва',
        ]
    
    def load_security_data(self):
        """Загружаем данные безопасности"""
        try:
            if os.path.exists(SECURITY_DATA_FILE):
                with open(SECURITY_DATA_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    # Можно добавить загрузку дополнительных данных
                    logger.info("📊 Данные безопасности загружены")
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки данных безопасности: {e}")
    
    def save_security_data(self):
        """Сохраняем данные безопасности"""
        try:
            os.makedirs("data", exist_ok=True)
            data = {
                'last_updated': datetime.now().isoformat(),
                'total_blocked': len(self.blocked_users),
                'rate_limits': self.rate_limits
            }
            
            with open(SECURITY_DATA_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                
        except Exception as e:
            logger.error(f"❌ Ошибка сохранения данных безопасности: {e}")
    
    def load_blocked_users(self):
        """Загружаем список заблокированных пользователей"""
        try:
            if os.path.exists(BLOCKED_USERS_FILE):
                with open(BLOCKED_USERS_FILE, 'r', encoding='utf-8') as f:
                    for line in f:
                        user_id = line.strip()
                        if user_id.isdigit():
                            self.blocked_users.add(int(user_id))
                
                logger.info(f"🚫 Загружено {len(self.blocked_users)} заблокированных пользователей")
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки заблокированных пользователей: {e}")
    
    def save_blocked_users(self):
        """Сохраняем список заблокированных пользователей"""
        try:
            os.makedirs("data", exist_ok=True)
            with open(BLOCKED_USERS_FILE, 'w', encoding='utf-8') as f:
                for user_id in self.blocked_users:
                    f.write(f"{user_id}\n")
        except Exception as e:
            logger.error(f"❌ Ошибка сохранения заблокированных пользователей: {e}")
    
    def is_user_blocked(self, user_id: int) -> bool:
        """Проверяем заблокирован ли пользователь"""
        return user_id in self.blocked_users
    
    def block_user(self, user_id: int, reason: str = "Spam"):
        """Блокируем пользователя"""
        self.blocked_users.add(user_id)
        self.save_blocked_users()
        logger.warning(f"🚫 Заблокирован пользователь {user_id}: {reason}")
    
    def unblock_user(self, user_id: int):
        """Разблокируем пользователя"""
        self.blocked_users.discard(user_id)
        self.save_blocked_users()
        logger.info(f"✅ Разблокирован пользователь {user_id}")
    
    def check_rate_limit(self, user_id: int, action_type: str) -> bool:
        """Проверяем не превышает ли пользователь лимиты"""
        now = datetime.now()
        user_actions = self.user_actions[user_id]
        
        # Очищаем старые действия
        if action_type == 'message':
            # Лимит сообщений в час
            cutoff = now - timedelta(hours=1)
            recent_messages = [a for a in user_actions if a['type'] == 'message' and a['time'] > cutoff]
            
            if len(recent_messages) >= self.rate_limits['messages_per_hour']:
                logger.warning(f"⚠️ Пользователь {user_id} превысил лимит сообщений в час")
                return False
        
        elif action_type == 'phrase':
            # Лимит фраз в день
            cutoff = now - timedelta(days=1)
            recent_phrases = [a for a in user_actions if a['type'] == 'phrase' and a['time'] > cutoff]
            
            if len(recent_phrases) >= self.rate_limits['phrases_per_day']:
                logger.warning(f"⚠️ Пользователь {user_id} превысил лимит фраз в день")
                return False
        
        elif action_type == 'command':
            # Лимит команд в минуту
            cutoff = now - timedelta(minutes=1)
            recent_commands = [a for a in user_actions if a['type'] == 'command' and a['time'] > cutoff]
            
            if len(recent_commands) >= self.rate_limits['commands_per_minute']:
                logger.warning(f"⚠️ Пользователь {user_id} превысил лимит команд в минуту")
                return False
        
        return True
    
    def log_user_action(self, user_id: int, action_type: str, content: str = ""):
        """Логируем действие пользователя"""
        action = {
            'type': action_type,
            'time': datetime.now(),
            'content': content[:100]  # Ограничиваем длину
        }
        
        self.user_actions[user_id].append(action)
        
        # Очищаем старые действия (оставляем только за последние 7 дней)
        cutoff = datetime.now() - timedelta(days=7)
        self.user_actions[user_id] = [
            a for a in self.user_actions[user_id] if a['time'] > cutoff
        ]
    
    def check_suspicious_content(self, text: str) -> List[str]:
        """Проверяем содержимое на подозрительные паттерны"""
        found_patterns = []
        text_lower = text.lower()
        
        for pattern in self.suspicious_patterns:
            if re.search(pattern, text_lower):
                found_patterns.append(pattern)
        
        if found_patterns:
            logger.warning(f"🔍 Найдены подозрительные паттерны в тексте: {found_patterns}")
        
        return found_patterns
    
    def is_content_suspicious(self, text: str) -> bool:
        """Проверяем подозрительное ли содержимое"""
        patterns = self.check_suspicious_content(text)
        return len(patterns) > 0
    
    def auto_moderate_phrase(self, user_id: int, phrase: str) -> Dict[str, any]:
        """Автоматическая модерация фразы"""
        result = {
            'allowed': True,
            'reason': '',
            'suspicion_level': 0,
            'auto_block': False
        }
        
        # Проверяем заблокирован ли пользователь
        if self.is_user_blocked(user_id):
            result['allowed'] = False
            result['reason'] = 'Пользователь заблокирован'
            return result
        
        # Проверяем rate limit
        if not self.check_rate_limit(user_id, 'phrase'):
            result['allowed'] = False
            result['reason'] = 'Превышен лимит фраз в день'
            result['suspicion_level'] = 3
            return result
        
        # Проверяем подозрительное содержимое
        suspicious_patterns = self.check_suspicious_content(phrase)
        if suspicious_patterns:
            result['suspicion_level'] = len(suspicious_patterns)
            
            if result['suspicion_level'] >= 3:
                result['allowed'] = False
                result['reason'] = 'Подозрительное содержимое'
                result['auto_block'] = True
            elif result['suspicion_level'] >= 2:
                result['allowed'] = False
                result['reason'] = 'Требует ручной модерации'
        
        # Логируем действие
        self.log_user_action(user_id, 'phrase', phrase)
        
        return result
    
    def get_security_stats(self) -> Dict:
        """Получаем статистику безопасности"""
        return {
            'blocked_users': len(self.blocked_users),
            'active_users_tracked': len(self.user_actions),
            'rate_limits': self.rate_limits,
            'suspicious_patterns_count': len(self.suspicious_patterns)
        }

# Глобальный экземпляр менеджера безопасности
security_manager = SecurityManager()