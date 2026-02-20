import json
import math
import statistics
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


def _ema(values: list[float], period: int) -> list[float]:
    if not values:
        return []
    k = 2 / (period + 1)
    out = [values[0]]
    for val in values[1:]:
        out.append(val * k + out[-1] * (1 - k))
    return out


def _rsi(values: list[float], period: int = 14) -> float:
    if len(values) < period + 1:
        return 50.0
    gains, losses = [], []
    for i in range(1, len(values)):
        d = values[i] - values[i - 1]
        gains.append(max(d, 0))
        losses.append(abs(min(d, 0)))
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def _bb(values: list[float], period: int = 20, dev: float = 2.0) -> tuple[float, float, float]:
    if len(values) < period:
        m = values[-1]
        return m, m, m
    window = values[-period:]
    mean = statistics.mean(window)
    std = statistics.pstdev(window) if len(window) > 1 else 0.0
    return mean + dev * std, mean, mean - dev * std


def _macd(values: list[float]) -> tuple[float, float, float]:
    if len(values) < 35:
        return 0.0, 0.0, 0.0
    ema12 = _ema(values, 12)
    ema26 = _ema(values, 26)
    macd_line = [a - b for a, b in zip(ema12, ema26)]
    signal = _ema(macd_line, 9)
    return macd_line[-1], signal[-1], macd_line[-1] - signal[-1]


def _fetch_binance_klines(symbol: str, interval: str, limit: int = 200) -> tuple[list[float], list[float]]:
    params = urllib.parse.urlencode({"symbol": symbol, "interval": interval, "limit": str(limit)})
    url = f"https://api.binance.com/api/v3/klines?{params}"
    with urllib.request.urlopen(url, timeout=20) as resp:
        rows = json.loads(resp.read().decode("utf-8"))
    closes = [float(r[4]) for r in rows]
    volumes = [float(r[5]) for r in rows]
    return closes, volumes


def _fetch_binance_price(symbol: str) -> float:
    params = urllib.parse.urlencode({"symbol": symbol})
    url = f"https://api.binance.com/api/v3/ticker/price?{params}"
    with urllib.request.urlopen(url, timeout=20) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    return float(payload.get("price"))


def analyze_binance_pair(pair: str) -> str:
    raw = (pair or "").upper().replace(" ", "")
    symbol = raw.replace("/", "")
    if "/" not in raw and raw.endswith("USDT"):
        pretty = f"{raw[:-4]}/USDT"
    elif "/" in raw:
        pretty = raw
    else:
        return "⚠️ Формат пары: BTC/USDT или ETH/USDT"

    try:
        closes_15, vols_15 = _fetch_binance_klines(symbol, "15m", 200)
        closes_1h, vols_1h = _fetch_binance_klines(symbol, "1h", 200)
        closes_4h, _ = _fetch_binance_klines(symbol, "4h", 200)
        price = _fetch_binance_price(symbol)
    except Exception as e:
        return f"⚠️ Ошибка Binance API: {e}"

    rsi_15 = _rsi(closes_15, 14)
    ema50_15 = _ema(closes_15, 50)[-1]
    ema50_1h = _ema(closes_1h, 50)[-1]
    ema50_4h = _ema(closes_4h, 50)[-1]
    macd, signal, hist = _macd(closes_1h)
    bb_u, _, bb_l = _bb(closes_1h, 20, 2)

    avg_vol = statistics.mean(vols_1h[-20:]) if len(vols_1h) >= 20 else max(vols_1h[-1], 1)
    vol_ratio = vols_1h[-1] / avg_vol if avg_vol else 1.0
    bb_pos = 0.5 if bb_u == bb_l else (price - bb_l) / (bb_u - bb_l)
    bb_pos = max(0.0, min(1.0, bb_pos))

    rsi_text = (
        "перекупленность, риск коррекции"
        if rsi_15 >= 70
        else "перепроданность, возможен отскок"
        if rsi_15 <= 30
        else "нейтральный, умеренный бычий импульс"
        if rsi_15 >= 50
        else "нейтральный, умеренный медвежий импульс"
    )

    above_ema_15 = price > ema50_15
    above_ema_1h = price > ema50_1h

    macd_text = (
        "положительный на 1ч, гистограмма растет"
        if macd > 0 and hist > 0
        else "положительный на 1ч, но импульс слабеет"
        if macd > 0
        else "отрицательный на 1ч, но сходится"
        if hist > 0
        else "отрицательный на 1ч, давление продавцов сохраняется"
    )

    bias_score = 0
    bias_score += 1 if rsi_15 >= 55 else -1 if rsi_15 < 45 else 0
    bias_score += 1 if above_ema_15 else -1
    bias_score += 1 if above_ema_1h else -1
    bias_score += 1 if macd > signal else -1
    bias_score += 1 if bb_pos >= 0.55 else -1 if bb_pos <= 0.45 else 0

    if bias_score >= 3:
        rec = f"Бычий наклон. Пробой ${bb_u:,.2f} может усилить рост. Следить за объёмом."
    elif bias_score >= 1:
        rec = f"Нейтрально-бычий наклон. Следить за пробоем ${bb_u:,.2f} для подтверждения роста."
    elif bias_score <= -3:
        rec = f"Медвежий наклон. Потеря ${bb_l:,.2f} может ускорить снижение. Нужен контроль риска."
    else:
        rec = f"Нейтральный сценарий. Ключевой диапазон: ${bb_l:,.2f} — ${bb_u:,.2f}."

    return (
        f"{pretty}: ${price:,.2f}\n\n"
        "Технический анализ:\n"
        f"• RSI {rsi_15:.2f} - {rsi_text}\n"
        f"• Цена {'выше' if above_ema_15 else 'ниже'} EMA(50) на 15м и {'выше' if above_ema_1h else 'ниже'} на 1ч\n"
        f"• Объем {'ниже' if vol_ratio < 1 else 'выше'} среднего ({vol_ratio:.2f}x)\n"
        f"• MACD {macd_text}\n"
        f"• Bollinger Bands: цена в {'верхней' if bb_pos >= 0.5 else 'нижней'} половине канала ({bb_pos:.2f})\n\n"
        "Ключевые уровни:\n"
        f"• Сопротивление: ${bb_u:,.2f} (верхняя полоса BB)\n"
        f"• Поддержка: ${bb_l:,.2f} (нижняя полоса BB)\n"
        f"• EMA(50) 4ч: ${ema50_4h:,.2f} (ближайший уровень)\n\n"
        "Рекомендация:\n"
        f"{rec}"
    )
