import sys
from openai import OpenAI, APIConnectionError

client = OpenAI(
    base_url="http://localhost:11434/v1",
    api_key="local"
)

MODEL = "qwen2.5:3b"

SYSTEM_PROMPT = """Ти - Senior .NET розробник.
Твоє завдання: допомагати з C#, ASP.NET Core, SignalR та PostgreSQL.
Відповідай виключно українською мовою, коротко і по суті.
Коментарі в коді пиши англійською."""

def chat():
    print(f"--- .NET Code Assistant ({MODEL}) ---")
    print("Напишіть 'вихід' для завершення.\n")
    
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    
    while True:
        try:
            user_input = input("Ви: ").strip()
            if not user_input:
                continue
            if user_input.lower() in ['вихід', 'exit', 'quit']:
                break
                
            messages.append({"role": "user", "content": user_input})
            
            response = client.chat.completions.create(
                model=MODEL,
                messages=messages,
                temperature=0.3,
                max_tokens=600,
                stream=True
            )
            
            print("Асистент: ", end="")
            full_reply = ""
            for chunk in response:
                content = chunk.choices[0].delta.content
                if content:
                    print(content, end="", flush=True)
                    full_reply += content
            print("\n" + "-"*50)
            
            messages.append({"role": "assistant", "content": full_reply})
            
            if len(messages) > 7:
                messages = [messages[0]] + messages[-6:]
                
        except APIConnectionError:
            print("\n[Помилка] Сервер Ollama не запущено. Виконайте 'ollama serve' у терміналі.")
            sys.exit(1)
        except Exception as e:
            print(f"\n[Помилка] Виникла проблема: {e}")
            messages.pop()

if __name__ == "__main__":
    chat()