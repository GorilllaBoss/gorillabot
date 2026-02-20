import json
import urllib.parse
import urllib.request

from openai import OpenAI
from openai import AuthenticationError, OpenAIError


def clean_ai_text(text: str) -> str:
    cleaned = (text or "").replace("#", "").replace("*", "")
    cleaned = cleaned.replace("```", "")
    lines = [line.strip() for line in cleaned.splitlines() if line.strip()]
    return "\n".join(lines).strip()


def ask_llm(client: OpenAI, model: str, api_key: str, system_prompt: str, user_prompt: str, max_tokens: int = 550) -> str:
    if not api_key:
        return "⚠️ OPENROUTER_API_KEY не настроен. Добавь ключ в .env"

    wrapped_system = (
        f"{system_prompt}\n\n"
        "Формат вывода: без символов markdown-разметки # и *. "
        "Пиши красиво, живо и понятно, можно с эмодзи."
    )

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": wrapped_system},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.7,
            max_tokens=max_tokens,
        )
        return clean_ai_text(response.choices[0].message.content.strip())
    except AuthenticationError:
        return (
            "⚠️ Ошибка авторизации OpenRouter (401: User not found). "
            "Проверь OPENROUTER_API_KEY в .env: нужен действующий ключ формата sk-or-v1-..."
        )
    except OpenAIError as e:
        return f"⚠️ Ошибка LLM-сервиса: {e}"


def fetch_crypto_snapshot(coin: str) -> dict:
    params = urllib.parse.urlencode(
        {
            "ids": coin,
            "vs_currencies": "usd",
            "include_market_cap": "true",
            "include_24hr_vol": "true",
            "include_24hr_change": "true",
            "include_last_updated_at": "true",
        }
    )
    url = f"https://api.coingecko.com/api/v3/simple/price?{params}"
    with urllib.request.urlopen(url, timeout=20) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    return payload.get(coin, {})
