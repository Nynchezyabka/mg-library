import re
import json
import sqlite3
from datetime import datetime
from collections import defaultdict, Counter
import os
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from docx import Document

@dataclass
class ChatMessage:
    """Класс для представления сообщения чата"""
    message_number: str
    sender: str
    date: str
    message_id: str
    reply_to: str
    text: str
    tags: List[str]
    is_violetta_answer: bool = False

class ChatParser:
    """Парсер для обработки документов чата"""
    
    def __init__(self):
        self.message_patterns = {
            'message_start': re.compile(r'Сообщение\s*#(\d+)'),
            'sender': re.compile(r'От:\s*([^•]+?)\s*•'),
            'date': re.compile(r'Дата:\s*([^•]+?)\s*•'),
            'message_id': re.compile(r'ID:\s*(\d+)'),
            'reply_to': re.compile(r'Ответ на сообщение:\s*(\d+)'),
            'tags': re.compile(r'#[\wа-яА-ЯёЁ\d_-]+', re.IGNORECASE)
        }
    
    def parse_word_document(self, docx_file: str) -> List[ChatMessage]:
        """Парсит Word-документ и извлекает структурированные данные"""
        
        print("📖 Чтение Word-документа...")
        
        if not os.path.exists(docx_file):
            raise FileNotFoundError(f"Файл {docx_file} не найден")
        
        doc = Document(docx_file)
        messages = []
        current_message = None
        
        for paragraph in doc.paragraphs:
            text = paragraph.text.strip()
            
            if not text:
                continue
                
            # Определяем начало нового сообщения
            if self._is_message_start(text):
                # Сохраняем предыдущее сообщение
                if current_message and current_message.text:
                    messages.append(current_message)
                
                # Создаем новое сообщение
                current_message = self._create_new_message(text)
                continue
            
            # Обрабатываем содержимое сообщения
            if current_message is not None:
                self._process_message_content(current_message, text)
        
        # Добавляем последнее сообщение
        if current_message and current_message.text:
            messages.append(current_message)
        
        print(f"📝 Извлечено сообщений: {len(messages)}")
        
        # Определяем ответы Виолетты по тегу
        self._identify_violetta_answers(messages)
        
        # Собираем статистику
        self._print_statistics(messages)
        
        return messages
    
    def _is_message_start(self, text: str) -> bool:
        """Определяет, является ли текст началом нового сообщения"""
        return (self.message_patterns['message_start'].search(text) is not None or 
                '――――――' in text)
    
    def _create_new_message(self, text: str) -> ChatMessage:
        """Создает новый объект сообщения"""
        message_number = ""
        match = self.message_patterns['message_start'].search(text)
        if match:
            message_number = match.group(1)
        
        return ChatMessage(
            message_number=message_number,
            sender="",
            date="",
            message_id="",
            reply_to="",
            text="",
            tags=[]
        )
    
    def _process_message_content(self, message: ChatMessage, text: str):
        """Обрабатывает содержимое сообщения"""
        # Пропускаем разделители
        if any(separator in text for separator in ['――', '─', '―']):
            return
        
        # Извлекаем метаданные
        if not message.sender and self.message_patterns['sender'].search(text):
            message.sender = self.message_patterns['sender'].search(text).group(1).strip()
        
        if not message.date and self.message_patterns['date'].search(text):
            message.date = self.message_patterns['date'].search(text).group(1).strip()
        
        if not message.message_id and self.message_patterns['message_id'].search(text):
            message.message_id = self.message_patterns['message_id'].search(text).group(1)
        
        if not message.reply_to and self.message_patterns['reply_to'].search(text):
            message.reply_to = self.message_patterns['reply_to'].search(text).group(1)
        
        # Основной текст сообщения
        if not any(pattern.search(text) for pattern in [
            self.message_patterns['sender'],
            self.message_patterns['date'], 
            self.message_patterns['message_id'],
            self.message_patterns['reply_to']
        ]):
            if message.text:
                message.text += '\n' + text
            else:
                message.text = text
            
            # Извлекаем теги
            tags = self.message_patterns['tags'].findall(text)
            if tags:
                # Очищаем теги от дубликатов
                unique_tags = list(set(tags))
                message.tags.extend(unique_tags)
    
    def _identify_violetta_answers(self, messages: List[ChatMessage]):
        """Определяет ответы Виолетты по тегу #ответвиолетты"""
        for message in messages:
            # Проверяем наличие тега #ответвиолетты
            has_answer_tag = any('ответвиолетты' in tag.lower() for tag in message.tags)
            message.is_violetta_answer = has_answer_tag
    
    def _print_statistics(self, messages: List[ChatMessage]):
        """Выводит статистику по сообщениям"""
        all_tags = []
        violetta_answers = 0
        
        for msg in messages:
            all_tags.extend(msg.tags)
            if msg.is_violetta_answer:
                violetta_answers += 1
        
        unique_tags = set(all_tags)
        
        print(f"🏷️  Найдено уникальных тегов: {len(unique_tags)}")
        print(f"💡 Ответов Виолетты: {violetta_answers}")

class QAGrouper:
    """Группировщик вопросов и ответов"""
    
    def __init__(self, messages: List[ChatMessage]):
        self.messages = messages
        self.messages_by_id = {msg.message_id: msg for msg in messages if msg.message_id}
    
    def group_questions_answers(self) -> List[Dict[str, Any]]:
        """Группирует вопросы и ответы, учитывая сложные цепочки"""
        
        print("🔗 Группировка вопросов и ответов...")
        
        violetta_answers = [msg for msg in self.messages if msg.is_violetta_answer]
        print(f"💡 Найдено ответов Виолетты: {len(violetta_answers)}")
        
        qa_pairs = []
        processed_questions = set()
        
        for answer in violetta_answers:
            if not answer.reply_to:
                continue
                
            question_thread = self._find_question_thread(answer.reply_to)
            
            if not question_thread:
                print(f"⚠️ Не найдена цепочка вопроса для ответа {answer.message_id}")
                continue
            
            question_key = tuple(sorted([msg.message_id for msg in question_thread if msg.message_id]))
            
            if question_key in processed_questions:
                continue
                
            processed_questions.add(question_key)
            
            answer_thread = self._find_answer_thread(question_thread)
            
            # Создаем пару вопрос-ответ
            qa_pair = self._create_qa_pair(question_thread, answer_thread)
            qa_pairs.append(qa_pair)
        
        self._print_qa_statistics(qa_pairs)
        return qa_pairs
    
    def _find_question_thread(self, start_message_id: str) -> List[ChatMessage]:
        """Находит цепочку вопросов по ID начального сообщения"""
        start_message = self.messages_by_id.get(start_message_id)
        if not start_message:
            return []
        
        parent_id = start_message.reply_to
        sender = start_message.sender
        
        if not parent_id:
            return [start_message]
        
        # Ищем все сообщения от того же отправителя с тем же reply_to
        question_thread = []
        for msg in self.messages:
            if (msg.reply_to == parent_id and 
                msg.sender == sender and 
                not msg.is_violetta_answer):
                question_thread.append(msg)
        
        # Сортируем по номеру сообщения
        question_thread.sort(key=lambda x: int(x.message_number) if x.message_number.isdigit() else 0)
        
        return question_thread
    
    def _find_answer_thread(self, question_thread: List[ChatMessage]) -> List[ChatMessage]:
        """Находит все ответы на цепочку вопросов"""
        question_ids = [msg.message_id for msg in question_thread if msg.message_id]
        
        answers = []
        for msg in self.messages:
            if (msg.is_violetta_answer and 
                msg.reply_to in question_ids):
                answers.append(msg)
        
        answers.sort(key=lambda x: int(x.message_number) if x.message_number.isdigit() else 0)
        return answers
    
    def _create_qa_pair(self, question_thread: List[ChatMessage], 
                       answer_thread: List[ChatMessage]) -> Dict[str, Any]:
        """Создает структурированную пару вопрос-ответ"""
        # Объединяем текст вопроса
        question_text = "\n\n".join([msg.text for msg in question_thread if msg.text])
        
        # Объединяем текст ответов
        answer_text = "\n\n".join([msg.text for msg in answer_thread if msg.text])
        
        # Собираем ВСЕ теги из всех ответов
        all_tags = []
        for msg in answer_thread:
            all_tags.extend(msg.tags)
        all_tags = list(set(all_tags))
        
        return {
            'question_ids': [msg.message_id for msg in question_thread if msg.message_id],
            'question_text': question_text,
            'question_sender': question_thread[0].sender if question_thread else '',
            'question_date': question_thread[0].date if question_thread else '',
            'answer_ids': [msg.message_id for msg in answer_thread if msg.message_id],
            'answer_text': answer_text,
            'tags': all_tags,
            'answer_date': answer_thread[-1].date if answer_thread else ''
        }
    
    def _print_qa_statistics(self, qa_pairs: List[Dict[str, Any]]):
        """Выводит статистику по парам вопрос-ответ"""
        print(f"📚 Создано пар вопрос-ответ: {len(qa_pairs)}")
        
        # Статистика по тегам
        all_library_tags = set()
        for qa in qa_pairs:
            all_library_tags.update(qa.get('tags', []))
        
        print(f"🏷️  Уникальных тегов в библиотеке: {len(all_library_tags)}")

class DatabaseManager:
    """Менеджер для работы с различными форматами базы данных"""
    
    def __init__(self, db_path: str = "chat_database.db"):
        self.db_path = db_path
    
    def save_to_sqlite(self, messages: List[ChatMessage], qa_pairs: List[Dict[str, Any]]):
        """Сохраняет данные в SQLite базу данных"""
        print("💾 Сохранение в SQLite базу данных...")
        
        # Инициализируем базу данных внутри одного соединения
        with sqlite3.connect(self.db_path) as conn:
            # Удаляем существующие таблицы если они есть
            conn.execute('DROP TABLE IF EXISTS message_tags')
            conn.execute('DROP TABLE IF EXISTS tags')
            conn.execute('DROP TABLE IF EXISTS qa_pairs')
            conn.execute('DROP TABLE IF EXISTS messages')
            
            # Создаем таблицы заново
            conn.execute('''
                CREATE TABLE messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    message_number INTEGER,
                    sender TEXT,
                    date TEXT,
                    message_id TEXT UNIQUE,
                    reply_to TEXT,
                    text TEXT,
                    is_violetta_answer BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            conn.execute('''
                CREATE TABLE tags (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tag TEXT UNIQUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            conn.execute('''
                CREATE TABLE message_tags (
                    message_id TEXT,
                    tag TEXT,
                    PRIMARY KEY (message_id, tag),
                    FOREIGN KEY (message_id) REFERENCES messages (message_id),
                    FOREIGN KEY (tag) REFERENCES tags (tag)
                )
            ''')
            
            conn.execute('''
                CREATE TABLE qa_pairs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    question_ids TEXT,
                    question_text TEXT,
                    question_sender TEXT,
                    question_date TEXT,
                    answer_ids TEXT,
                    answer_text TEXT,
                    tags TEXT,
                    answer_date TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Сохраняем сообщения
            for msg in messages:
                conn.execute('''
                    INSERT OR REPLACE INTO messages 
                    (message_number, sender, date, message_id, reply_to, text, is_violetta_answer)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (msg.message_number, msg.sender, msg.date, msg.message_id, 
                      msg.reply_to, msg.text, msg.is_violetta_answer))
                
                # Сохраняем теги
                for tag in msg.tags:
                    conn.execute('INSERT OR IGNORE INTO tags (tag) VALUES (?)', (tag,))
                    conn.execute('''
                        INSERT OR REPLACE INTO message_tags (message_id, tag)
                        VALUES (?, ?)
                    ''', (msg.message_id, tag))
            
            # Сохраняем пары вопрос-ответ
            for qa in qa_pairs:
                conn.execute('''
                    INSERT INTO qa_pairs 
                    (question_ids, question_text, question_sender, question_date,
                     answer_ids, answer_text, tags, answer_date)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    json.dumps(qa['question_ids']), qa['question_text'], qa['question_sender'],
                    qa['question_date'], json.dumps(qa['answer_ids']), qa['answer_text'],
                    json.dumps(qa['tags']), qa['answer_date']
                ))
            
            conn.commit()
    
    def create_json_database(self, qa_pairs: List[Dict[str, Any]], 
                           output_file: str = "библиотека_вопросов_ответов.json"):
        """Создает JSON-базу данных"""
        
        print("💾 Создание JSON-базы данных...")
        
        all_tags = set()
        for qa in qa_pairs:
            all_tags.update(qa.get('tags', []))
        
        # Сортируем теги: сначала #ответвиолетты, затем остальные по алфавиту
        sorted_tags = self._sort_tags_alphabetical(all_tags)
        
        database = {
            "metadata": {
                "created": datetime.now().isoformat(),
                "total_entries": len(qa_pairs),
                "total_unique_tags": len(all_tags),
                "all_tags": sorted_tags,
                "description": "База знаний вопросов и ответов из психологической мастер-группы"
            },
            "data": qa_pairs
        }
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(database, f, ensure_ascii=False, indent=2)
        
        return output_file
    
    def _sort_tags_alphabetical(self, tags: set) -> List[str]:
        """Сортирует теги: сначала #ответвиолетты, затем остальные по алфавиту"""
        tags_list = list(tags)
        
        # Находим тег #ответвиолетты (в любом регистре)
        answer_tag = None
        for tag in tags_list:
            if 'ответвиолетты' in tag.lower():
                answer_tag = tag
                break
        
        # Удаляем его из общего списка
        if answer_tag:
            tags_list.remove(answer_tag)
        
        # Сортируем остальные теги по алфавиту
        tags_list.sort(key=lambda x: x.lower())
        
        # Возвращаем список с #ответвиолетты первым
        if answer_tag:
            return [answer_tag] + tags_list
        else:
            return tags_list

def create_interactive_html(qa_pairs: List[Dict[str, Any]], 
                          output_dir: str = "src"):
    """Создает HTML приложение с встроенными данными"""
    
    print("🎨 Создание веб-приложения...")
    
    # Создаем директории если их нет
    os.makedirs(output_dir, exist_ok=True)
    
    # 1. Сохраняем JSON данные как резервную копию
    json_file = os.path.join(output_dir, "data.json")
    with open(json_file, 'w', encoding='utf-8') as f:
        json.dump({
            "metadata": {
                "created": datetime.now().isoformat(),
                "total_entries": len(qa_pairs),
                "total_unique_tags": len(set(tag for qa in qa_pairs for tag in qa.get('tags', []))),
                "description": "База знаний вопросов и ответов из психологической мастер-группы"
            },
            "data": qa_pairs
        }, f, ensure_ascii=False, indent=2)
    
    # 2. Создаем HTML файл со ВСТРОЕННЫМИ данными
    html_file = os.path.join(output_dir, "index.html")
    
    # Подготавливаем данные для вставки в JavaScript
    qa_data_json = json.dumps(qa_pairs, ensure_ascii=False)
    
    html_content = f'''<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Мастер Группа - Библиотека вопросов и ответов</title>
    <link rel="stylesheet" href="styles.css">
</head>
<body>
    <div class="container">
        <header>
            <div class="header-content">
                <div class="subtitle">Мастер Группа</div>
                <h1>Поток№2: "Мотивация и деятельность"</h1>
                <div class="description">📚 Библиотека вопросов и ответов</div>
            </div>
        </header>
        
        <div class="app-info">
            ✅ Приложение работает офлайн. Все данные загружены в память.
        </div>
        
        <div class="stats">
            Всего записей: <strong><span id="totalCount">{len(qa_pairs)}</span></strong> | 
            Показано: <strong><span id="shownCount">{len(qa_pairs)}</span></strong> |
            Уникальных тегов: <strong><span id="tagsCount">{len(set(tag for qa in qa_pairs for tag in qa.get('tags', [])))}</span></strong>
        </div>
        
        <div class="search-filters">
            <input type="text" id="searchInput" placeholder="🔍 Поиск по вопросам и ответам...">
            <div class="section-title">Фильтр по тегам:</div>
            <div class="tag-filters" id="tagFilters">
                <button class="tag-filter active" data-tag="all">Все теги</button>
            </div>
        </div>
        
        <div class="qa-grid" id="qaGrid">
            <div class="loading">Загрузка данных...</div>
        </div>
    </div>

    <script>
        // ВАЖНО: Все данные встроены прямо в HTML чтобы избежать CORS проблем
        const qaData = {qa_data_json};
        
        class LibraryApp {{
            constructor() {{
                this.qaData = qaData;
                this.sortedTags = this.sortTags(this.getAllTags());
                this.init();
            }}

            init() {{
                this.renderQACards(this.qaData);
                this.initTagFilters();
                this.setupEventListeners();
                this.updateStats();
            }}

            getAllTags() {{
                const allTags = new Set();
                this.qaData.forEach(item => {{
                    if (item.tags && Array.isArray(item.tags)) {{
                        item.tags.forEach(tag => allTags.add(tag));
                    }}
                }});
                return allTags;
            }}

            sortTags(tags) {{
                const tagsArray = Array.from(tags);
                let answerTag = null;
                const otherTags = [];

                for (const tag of tagsArray) {{
                    if (tag.toLowerCase().includes('ответвиолетты')) {{
                        answerTag = tag;
                    }} else {{
                        otherTags.push(tag);
                    }}
                }}

                otherTags.sort((a, b) => a.toLowerCase().localeCompare(b.toLowerCase()));
                return answerTag ? [answerTag, ...otherTags] : otherTags;
            }}

            escapeHtml(text) {{
                if (!text) return '';
                const div = document.createElement('div');
                div.textContent = text;
                return div.innerHTML;
            }}

            renderQACards(data) {{
                const grid = document.getElementById('qaGrid');
                
                if (!grid) {{
                    console.error('Элемент qaGrid не найден');
                    return;
                }}

                grid.innerHTML = '';

                if (data.length === 0) {{
                    grid.innerHTML = '<div class="no-results">😔 Ничего не найдено. Попробуйте изменить поисковый запрос или фильтры.</div>';
                    return;
                }}

                data.forEach((item) => {{
                    const card = document.createElement('div');
                    card.className = 'qa-card';
                    
                    card.innerHTML = `
                        <div class="question">
                            <div class="section-title">Вопрос</div>
                            <div class="question-text">${{this.escapeHtml(item.question_text)}}</div>
                            <div class="meta">
                                От: ${{this.escapeHtml(item.question_sender)}} • 
                                Дата: ${{this.escapeHtml(item.question_date)}}
                            </div>
                        </div>
                        <div class="answer">
                            <div class="section-title">Ответ</div>
                            <div class="answer-text">${{this.escapeHtml(item.answer_text)}}</div>
                            <div class="meta">
                                Дата ответа: ${{this.escapeHtml(item.answer_date)}}
                            </div>
                        </div>
                        <div class="tags">
                            ${{(item.tags || []).map(tag => 
                                `<span class="tag" data-tag="${{tag}}">${{this.escapeHtml(tag)}}</span>`
                            ).join('')}}
                        </div>
                    `;
                    grid.appendChild(card);
                }});

                this.updateShownCount(data.length);
            }}

            initTagFilters() {{
                const tagContainer = document.getElementById('tagFilters');
                if (!tagContainer) return;

                tagContainer.innerHTML = '<button class="tag-filter active" data-tag="all">Все теги</button>';

                this.sortedTags.forEach(tag => {{
                    const filterButton = document.createElement('button');
                    filterButton.className = 'tag-filter';
                    filterButton.textContent = tag;
                    filterButton.dataset.tag = tag;
                    filterButton.onclick = () => this.toggleTagFilter(filterButton);
                    tagContainer.appendChild(filterButton);
                }});
            }}

            toggleTagFilter(button) {{
                button.classList.toggle('active');
                
                if (button.dataset.tag === 'all') {{
                    document.querySelectorAll('.tag-filter:not([data-tag="all"])').forEach(btn => {{
                        btn.classList.remove('active');
                    }});
                }} else {{
                    document.querySelector('[data-tag="all"]').classList.remove('active');
                }}
                
                this.filterAndSearch();
            }}

            filterAndSearch() {{
                const searchTerm = document.getElementById('searchInput').value.toLowerCase();
                const activeTags = Array.from(document.querySelectorAll('.tag-filter.active'))
                    .map(btn => btn.dataset.tag);

                const filtered = this.qaData.filter(item => {{
                    const matchesSearch = !searchTerm || 
                        (item.question_text && item.question_text.toLowerCase().includes(searchTerm)) ||
                        (item.answer_text && item.answer_text.toLowerCase().includes(searchTerm));

                    const matchesTags = activeTags.length === 0 || 
                        activeTags.includes('all') ||
                        (item.tags && activeTags.some(tag => item.tags.includes(tag)));

                    return matchesSearch && matchesTags;
                }});

                this.renderQACards(filtered);
            }}

            setupEventListeners() {{
                const searchInput = document.getElementById('searchInput');
                if (searchInput) {{
                    searchInput.addEventListener('input', () => this.filterAndSearch());
                }}
            }}

            updateStats() {{
                const totalCount = document.getElementById('totalCount');
                const tagsCount = document.getElementById('tagsCount');
                
                if (totalCount) totalCount.textContent = this.qaData.length;
                if (tagsCount) tagsCount.textContent = this.sortedTags.length;
            }}

            updateShownCount(count) {{
                const shownCount = document.getElementById('shownCount');
                if (shownCount) shownCount.textContent = count;
            }}
        }}

        // Запускаем приложение когда страница загружена
        document.addEventListener('DOMContentLoaded', () => {{
            new LibraryApp();
        }});
    </script>
</body>
</html>'''
    
    with open(html_file, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    # 3. Создаем CSS файл
    css_file = os.path.join(output_dir, "styles.css")
    css_content = ''':root {
    --primary-color: #2c3e50;
    --secondary-color: #34495e;
    --accent-color: #3498db;
    --light-bg: #ecf0f1;
    --border-color: #bdc3c7;
}

* {
    box-sizing: border-box;
    margin: 0;
    padding: 0;
}

body {
    font-family: 'Georgia', 'Times New Roman', serif;
    line-height: 1.6;
    color: #2c3e50;
    background-color: #f8f9fa;
    font-size: 16px;
}

.container {
    max-width: 1200px;
    margin: 0 auto;
    padding: 20px;
}

header {
    background: linear-gradient(to right, #1abc9c, #e84393, #e67e22);
    color: white;
    padding: 3rem 0;
    text-align: center;
    margin-bottom: 2rem;
    border-radius: 8px;
    box-shadow: 0 4px 6px rgba(0,0,0,0.1);
}

.header-content h1 {
    font-size: 2.2rem;
    margin-bottom: 0.5rem;
    font-weight: 400;
}

.header-content .subtitle {
    font-size: 1.3rem;
    opacity: 0.95;
    font-style: italic;
    margin-bottom: 0.5rem;
}

.header-content .description {
    font-size: 1.1rem;
    opacity: 0.9;
    margin-top: 0.5rem;
}

.stats {
    background: white;
    padding: 1.5rem;
    border-radius: 8px;
    margin-bottom: 2rem;
    text-align: center;
    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    border-left: 4px solid var(--accent-color);
    font-size: 1.1rem;
}

.search-filters {
    background: white;
    padding: 1.5rem;
    border-radius: 8px;
    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    margin-bottom: 2rem;
}

#searchInput {
    width: 100%;
    padding: 15px;
    border: 2px solid var(--border-color);
    border-radius: 8px;
    font-size: 16px;
    outline: none;
    transition: border-color 0.3s;
    font-family: inherit;
    margin-bottom: 1rem;
}

#searchInput:focus {
    border-color: var(--accent-color);
}

.tag-filters {
    display: flex;
    flex-wrap: wrap;
    gap: 0.8rem;
    padding: 15px;
    background: var(--light-bg);
    border-radius: 8px;
}

.tag-filter {
    background: white;
    border: 2px solid var(--border-color);
    padding: 10px 20px;
    border-radius: 25px;
    cursor: pointer;
    transition: all 0.3s;
    font-size: 14px;
    font-weight: 500;
    color: var(--secondary-color);
    white-space: nowrap;
}

.tag-filter:hover {
    border-color: var(--accent-color);
    color: var(--accent-color);
}

.tag-filter.active {
    background: var(--accent-color);
    border-color: var(--accent-color);
    color: white;
}

.qa-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(500px, 1fr));
    gap: 2rem;
}

.qa-card {
    background: white;
    border-radius: 8px;
    box-shadow: 0 2px 10px rgba(0,0,0,0.1);
    transition: transform 0.3s, box-shadow 0.3s;
    overflow: hidden;
    border: 1px solid var(--border-color);
}

.qa-card:hover {
    transform: translateY(-2px);
    box-shadow: 0 4px 15px rgba(0,0,0,0.15);
}

.question {
    padding: 2rem;
    border-bottom: 1px solid var(--border-color);
    background: var(--light-bg);
}

.question-text {
    font-size: 1.1rem;
    line-height: 1.7;
    color: #2c3e50;
    white-space: pre-line;
}

.answer {
    padding: 2rem;
    background: white;
}

.answer-text {
    font-size: 1.1rem;
    line-height: 1.7;
    color: #2c3e50;
    white-space: pre-line;
}

.tags {
    padding: 1.5rem;
    background: #f8f9fa;
    border-top: 1px solid var(--border-color);
    display: flex;
    flex-wrap: wrap;
    gap: 0.8rem;
}

.tag {
    background: var(--accent-color);
    color: white;
    padding: 8px 16px;
    border-radius: 20px;
    font-size: 13px;
    font-weight: 500;
    letter-spacing: 0.5px;
}

.meta {
    font-size: 14px;
    color: #7f8c8d;
    margin-top: 1rem;
    font-style: italic;
}

.no-results {
    text-align: center;
    padding: 4rem;
    color: #7f8c8d;
    grid-column: 1 / -1;
    font-size: 1.2rem;
}

.loading {
    text-align: center;
    padding: 2rem;
    font-size: 1.2rem;
    color: #7f8c8d;
}

.section-title {
    font-size: 1.3rem;
    font-weight: 600;
    margin-bottom: 1rem;
    color: var(--primary-color);
    border-bottom: 2px solid var(--accent-color);
    padding-bottom: 0.5rem;
}

.app-info {
    background: #e8f5e9;
    padding: 10px;
    border-radius: 5px;
    margin-bottom: 1rem;
    text-align: center;
    font-size: 14px;
    color: #2e7d32;
}

@media (max-width: 768px) {
    .qa-grid {
        grid-template-columns: 1fr;
    }
    
    .container {
        padding: 10px;
    }
    
    header {
        padding: 2rem 0;
    }
    
    .header-content h1 {
        font-size: 1.8rem;
    }
    
    .header-content .subtitle {
        font-size: 1.1rem;
    }
}'''
    
    with open(css_file, 'w', encoding='utf-8') as f:
        f.write(css_content)
    
    return html_file, json_file

def main():
    """Основная функция"""
    
    # Конфигурация - укажите путь к вашему Word файлу
    input_docx = "ВСЕ_СООБЩЕНИЯ_СТАРЫЕ_Чат. Мастер Группа Макеевой Виолетты_20251029_1403.docx"
    
    if not os.path.exists(input_docx):
        print(f"❌ Файл {input_docx} не найден!")
        print("Пожалуйста, положите Word файл в ту же папку что и этот скрипт")
        return
    
    try:
        # Инициализация компонентов
        parser = ChatParser()
        db_manager = DatabaseManager()
        
        # Парсинг документа
        messages = parser.parse_word_document(input_docx)
        
        if not messages:
            print("❌ Не найдено сообщений для обработки")
            return
        
        # Группировка вопросов и ответов
        grouper = QAGrouper(messages)
        qa_pairs = grouper.group_questions_answers()
        
        if not qa_pairs:
            print("❌ Не найдено пар вопрос-ответ для обработки")
            return
        
        # Сохранение в различные форматы
        db_manager.save_to_sqlite(messages, qa_pairs)
        json_file = db_manager.create_json_database(qa_pairs)
        
        # Создаем веб-приложение
        html_file, data_json_file = create_interactive_html(qa_pairs, "src")
        
        # Вывод статистики
        all_tags = set()
        for qa in qa_pairs:
            all_tags.update(qa.get('tags', []))
        
        print(f"""
✅ Приложение успешно создано!

📊 Статистика:
   - Обработано сообщений: {len(messages)}
   - Найдено пар вопрос-ответ: {len(qa_pairs)}
   - Собрано уникальных тегов: {len(all_tags)}

📁 Созданные файлы в папке src/:
   • index.html - приложение со встроенными данными
   • styles.css - стили
   • data.json - резервная копия данных

🚀 КАК ИСПОЛЬЗОВАТЬ:

1. 📂 ДЛЯ GITHUB (залить всё):
   - Папку src/ целиком (index.html, styles.css, data.json)

2. 💻 ЛОКАЛЬНЫЙ ЗАПУСК:
   - Просто откройте src/index.html в браузере
   - Или запустите локальный сервер в папке src/

3. 🔄 ОБНОВЛЕНИЕ ДАННЫХ:
   - Положите новый Word файл
   - Запустите этот скрипт заново
   - Новые данные автоматически встроятся в HTML

🌐 Преимущества:
   • Не требует отдельных JSON файлов
   • Работает офлайн
   • Нет проблем с CORS
   • Можно разместить на GitHub Pages

📝 Примечание: файл data.json создается как резервная копия, 
   но приложение использует данные встроенные в HTML
        """)
        
    except Exception as e:
        print(f"❌ Произошла ошибка: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()