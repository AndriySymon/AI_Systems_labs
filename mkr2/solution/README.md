# Інструкція із запуску AI Lecture Processor

## 1. Вимоги
- Python 3.10+ (бібліотека `imageio-ffmpeg` встановлює виконуваний `ffmpeg` автоматично разом із залежностями, ручне налаштування системного `PATH` не потрібне)
- API-ключ Google Gemini (`GEMINI_API_KEY`)

## 2. Встановлення залежностей
```bash
pip install -r requirements.txt
```

## 3. Налаштування ключа
Створіть файл `.env` у папці `solution/` або задайте змінну оточення:
```bash
export GEMINI_API_KEY="ваш_api_ключ"
```

## 4. Запуск

**Варіант А: Обробка відео або аудіо лекції**
```bash
python lecture_processor.py --input path/to/lecture.mp4 --keywords "Бази даних, SQL, індекси"
```

**Варіант Б: Швидкий тест на текстовому прикладі (без медіафайлу)**
```bash
python lecture_processor.py --input sample_transcript.txt --keywords "Архітектура ПЗ, мікросервіси"
```

Результат зберігається у папку `output/` у вигляді двох файлів: `*_notes.md` (конспект) та `*_anki.csv` (картки).