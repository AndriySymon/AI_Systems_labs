import argparse
import os
import re
import subprocess
import time
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

SYSTEM_PROMPT = """
Ти — професійний академічний асистент. Твоє завдання — перетворити запис або транскрипцію лекції на глибокий, добре структурований навчальний конспект.

Дотримуйся суворої структури відповіді (використовуй Markdown):

# Назва лекції (сформулюй за змістом)

## 1. Коротке резюме (3–5 речень)
Головна ідея лекції та ключові висновки.

## 2. Детальний конспект за розділами
Розбий матеріал на логічні блоки. Біля кожного заголовку блоку вказуй таймкод початку у форматі [MM:SS] або [HH:MM:SS].
- Використовуй марковані списки, виділяй жирним ключові поняття.
- Не скорочуй важливі аргументи, приклади та пояснення викладача.

## 3. Словник ключових термінів
Таблиця: | Термін | Визначення простими словами | Таймкод |

## 4. Картки для самоперевірки (Anki)
Створи рівно 15 запитань різної складності для перевірки розуміння матеріалу.
Обов'язково огорни цей блок у теги <ANKI_CSV> та </ANKI_CSV> у форматі:
"Питання";"Відповідь"
(без заголовків колонок, крапка з комою як роздільник).
"""


def extract_audio(input_path: Path, temp_dir: Path) -> Path:
    """Конвертує відео або важке аудіо в оптимізований моно MP3 через ffmpeg."""
    output_audio = temp_dir / f"{input_path.stem}_compressed.mp3"
    print(f"[1/3] Оптимізація медіафайлу через ffmpeg: {input_path.name}...")

    cmd = [
        "ffmpeg", "-y", "-i", str(input_path),
        "-vn",                   
        "-ac", "1",              
        "-ar", "16000",          
        "-b:a", "32k",           
        "-af", "loudnorm",       
        str(output_audio)
    ]

    try:
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except FileNotFoundError:
        raise RuntimeError("Помилка: утиліта ffmpeg не знайдена. Встановіть ffmpeg або подайте .txt файл.")

    size_mb = output_audio.stat().st_size / (1024 * 1024)
    print(f"      Готово! Розмір аудіо для API: {size_mb:.2f} МБ")
    return output_audio


def process_lecture(input_path: Path, keywords: str = "") -> tuple[str, str, float]:
    """Відправляє файл у Gemini API з автоматичним fallback і повертає (текст, модель, час)."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("Не знайдено GEMINI_API_KEY у змінних середовища або файлі .env")

    client = genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=60000))
    user_prompt = "Проаналізуй цю лекцію та створи конспект і картки за інструкцією."
    if keywords:
        user_prompt += f"\nКонтекст / ключові слова теми (враховуй для точного написання термінів): {keywords}"

    ext = input_path.suffix.lower()
    uploaded_file = None
    temp_audio = None

    try:
        if ext in (".txt", ".srt"):
            print(f"[1/3] Зчитування текстового файлу {input_path.name}...")
            text_content = input_path.read_text(encoding="utf-8")
            contents = [user_prompt, text_content]
        else:
            temp_dir = Path("temp")
            temp_dir.mkdir(exist_ok=True)
            temp_audio = extract_audio(input_path, temp_dir)

            print("[2/3] Завантаження аудіо в Gemini File API...")
            uploaded_file = client.files.upload(file=str(temp_audio))
            while uploaded_file.state.name == "PROCESSING":
                time.sleep(2)
                uploaded_file = client.files.get(name=uploaded_file.name)
            contents = [uploaded_file, user_prompt]

        available_models = [
            m.name.replace("models/", "")
            for m in client.models.list()
            if "gemini" in m.name.lower() and "embedding" not in m.name.lower()
        ]
        models_to_try = ["gemini-3-flash-preview", "gemini-3.8-flash-lite", "gemini-3.5-flash"]

        response = None
        last_error = None
        used_model = ""
        start_time = time.time()

        for model_name in models_to_try:
            try:
                print(f"[3/3] Генерація конспекту та Anki-карток ({model_name})...")
                response = client.models.generate_content(
                    model=model_name,
                    contents=contents,
                    config=types.GenerateContentConfig(
                        system_instruction=SYSTEM_PROMPT,
                        temperature=0.2,
                    )
                )
                used_model = model_name
                break
            except Exception as e:
                print(f"      Модель {model_name} недоступна: {e}")
                last_error = e

        if response is None:
            raise RuntimeError(f"Жодна модель не відповіла. Остання помилка: {last_error}")

        elapsed = time.time() - start_time
        print(f"      Успішно згенеровано за {elapsed:.1f} сек!")
        return response.text, used_model, elapsed

    finally:
        if uploaded_file:
            client.files.delete(name=uploaded_file.name)
        if temp_audio and temp_audio.exists():
            temp_audio.unlink()


def save_outputs(raw_text: str, base_name: str, out_dir: Path):
    """Розділяє відповідь AI на Markdown-конспект та CSV-файл для Anki."""
    out_dir.mkdir(exist_ok=True)

    csv_match = re.search(r"<ANKI_CSV>(.*?)</ANKI_CSV>", raw_text, re.DOTALL)
    if csv_match:
        csv_content = csv_match.group(1).strip()
        clean_markdown = re.sub(r"<ANKI_CSV>.*?</ANKI_CSV>", "", raw_text, flags=re.DOTALL).strip()
    else:
        csv_content = ""
        clean_markdown = raw_text

    md_path = out_dir / f"{base_name}_notes.md"
    md_path.write_text(clean_markdown, encoding="utf-8")
    print(f"-> Конспект збережено: {md_path}")

    if csv_content:
        csv_path = out_dir / f"{base_name}_anki.csv"
        csv_path.write_text(csv_content, encoding="utf-8")
        print(f"-> Картки Anki збережено: {csv_path}")


def append_log(input_file: Path, model_used: str, elapsed: float):
    """Автоматично дописує реальний результат запуску в ../evidence/run_log.txt."""
    log_path = Path("../evidence/run_log.txt")
    log_path.parent.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    size_kb = input_file.stat().st_size / 1024
    log_entry = (
        f"[{timestamp}] INPUT: {input_file.name} ({size_kb:.1f} KB) | "
        f"MODEL: {model_used} | TIME: {elapsed:.1f}s | "
        f"OUTPUT: {input_file.stem}_notes.md, {input_file.stem}_anki.csv\n"
    )
    with log_path.open("a", encoding="utf-8") as f:
        f.write(log_entry)
    print(f"-> Лог записано у: {log_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AI-асистент для конспектування лекцій")
    parser.add_argument("--input", required=True, help="Шлях до відео (.mp4), аудіо (.mp3) або тексту (.txt)")
    parser.add_argument("--keywords", default="", help="Ключові терміни теми через кому")
    args = parser.parse_args()

    input_file = Path(args.input)
    if not input_file.exists():
        raise FileNotFoundError(f"Файл не знайдено: {input_file}")

    result_text, model_used, elapsed = process_lecture(input_file, args.keywords)
    save_outputs(result_text, input_file.stem, Path("output"))
    append_log(input_file, model_used, elapsed)