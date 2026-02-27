import difflib
import json
import math
import statistics
import urllib.parse
import urllib.request
from datetime import datetime

from openai import OpenAI
from openai import AuthenticationError, OpenAIError


PAIR_ALIASES = {
    "биткоин": "BTC",
    "биток": "BTC",
    "btc": "BTC",
    "эфир": "ETH",
    "эфириум": "ETH",
    "eth": "ETH",
    "линк": "LINK",
    "link": "LINK",
    "апт": "APT",
    "apt": "APT",
    "оп": "OP",
    "optimism": "OP",
    "op": "OP",
    "арб": "ARB",
    "arbitrum": "ARB",
    "arb": "ARB",
    "bnb": "BNB",
    "sol": "SOL",
    "сол": "SOL",
}


def resolve_binance_pair_input(user_text: str) -> dict:
    text = (user_text or "").strip().lower().replace(" ", "")
    if not text:
        return {"ok": False, "error": "Пустой запрос.", "suggestions": ["BTC/USDT", "ETH/USDT", "LINK/USDT", "APT/USDT", "OP/USDT", "ARB/USDT"]}

    if "/" in text:
        base, quote = text.split("/", 1)
        base = PAIR_ALIASES.get(base, base).upper()
        quote = quote.upper()
        if not base or not quote:
            return {"ok": False, "error": "Неверный формат пары.", "suggestions": ["BTC/USDT", "ETH/USDT"]}
        return {"ok": True, "pair": f"{base}/{quote}"}

    if text.endswith("usdt") and len(text) > 4:
        base = text[:-4]
        base = PAIR_ALIASES.get(base, base).upper()
        return {"ok": True, "pair": f"{base}/USDT"}

    alias = PAIR_ALIASES.get(text)
    if alias:
        return {"ok": True, "pair": f"{alias}/USDT"}

    suggestions_pool = [
        "BTC/USDT",
        "ETH/USDT",
        "LINK/USDT",
        "APT/USDT",
        "OP/USDT",
        "ARB/USDT",
        "BNB/USDT",
        "SOL/USDT",
    ]
    close = difflib.get_close_matches(text.upper(), [x.split("/")[0] for x in suggestions_pool], n=3, cutoff=0.3)
    suggestions = [f"{x}/USDT" for x in close] if close else suggestions_pool[:4]
    return {"ok": False, "error": "Не понял тикер.", "suggestions": suggestions}


def clean_ai_text(text: str) -> str:
    cleaned = (text or "").replace("#", "").replace("*", "")
    cleaned = cleaned.replace("```", "")
    lines = [line.strip() for line in cleaned.splitlines() if line.strip()]
    return "\n".join(lines).strip()


def ask_llm(client: OpenAI, model: str, api_key: str, system_prompt: str, user_prompt: str, max_tokens: int = 550) -> str:
    if not api_key:
        return "⚠️ OPENROUTER_API_KEY не настроен. Добавь ключ в .env"

    now = datetime.now()
    current_dt = now.strftime("%d.%m.%Y %H:%M")
    current_year = now.year
    wrapped_system = (
        f"{system_prompt}\n\n"
        f"Текущее время: {current_dt} (локальное). Текущий год: {current_year}. "
        "Если пользователь не указал другой период, анализируй относительно текущего времени и текущего года. "
        "Не подставляй прошлые годы по умолчанию.\n\n"
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


def _fetch_binance_klines(symbol: str, interval: str, limit: int = 200, api_key: str = "") -> tuple[list[float], list[float]]:
    params = urllib.parse.urlencode({"symbol": symbol, "interval": interval, "limit": str(limit)})
    url = f"https://api.binance.com/api/v3/klines?{params}"
    req = urllib.request.Request(url)
    if api_key:
        req.add_header("X-MBX-APIKEY", api_key)
    with urllib.request.urlopen(req, timeout=20) as resp:
        rows = json.loads(resp.read().decode("utf-8"))
    closes = [float(r[4]) for r in rows]
    volumes = [float(r[5]) for r in rows]
    return closes, volumes


def _fetch_binance_price(symbol: str, api_key: str = "") -> float:
    params = urllib.parse.urlencode({"symbol": symbol})
    url = f"https://api.binance.com/api/v3/ticker/price?{params}"
    req = urllib.request.Request(url)
    if api_key:
        req.add_header("X-MBX-APIKEY", api_key)
    with urllib.request.urlopen(req, timeout=20) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    return float(payload.get("price"))


def _fetch_binance_24h(symbol: str, api_key: str = "") -> dict:
    params = urllib.parse.urlencode({"symbol": symbol})
    url = f"https://api.binance.com/api/v3/ticker/24hr?{params}"
    req = urllib.request.Request(url)
    if api_key:
        req.add_header("X-MBX-APIKEY", api_key)
    with urllib.request.urlopen(req, timeout=20) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    return payload




def _fmt_price(v: float) -> str:
    a = abs(v)
    if a >= 100:
        return f"{v:,.2f}"
    if a >= 1:
        return f"{v:,.3f}"
    if a >= 0.1:
        return f"{v:,.4f}"
    if a >= 0.01:
        return f"{v:,.5f}"
    return f"{v:,.6f}"

def analyze_binance_pair(pair: str, api_key: str = "") -> str:
    raw = (pair or "").upper().replace(" ", "")
    symbol = raw.replace("/", "")
    if "/" not in raw and raw.endswith("USDT"):
        pretty = f"{raw[:-4]}/USDT"
    elif "/" in raw:
        pretty = raw
    else:
        return "⚠️ Формат пары: BTC/USDT или ETH/USDT"

    try:
        closes_15, vols_15 = _fetch_binance_klines(symbol, "15m", 200, api_key=api_key)
        closes_1h, vols_1h = _fetch_binance_klines(symbol, "1h", 200, api_key=api_key)
        closes_4h, _ = _fetch_binance_klines(symbol, "4h", 200, api_key=api_key)
        price = _fetch_binance_price(symbol, api_key=api_key)
        ticker24 = _fetch_binance_24h(symbol, api_key=api_key)
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
    vol_pct_vs_avg = (vol_ratio - 1) * 100
    price_change_24h = float(ticker24.get("priceChangePercent", 0.0))
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
        rec = f"Бычий наклон. Пробой ${_fmt_price(bb_u)} может усилить рост. Следить за объёмом."
    elif bias_score >= 1:
        rec = f"Нейтрально-бычий наклон. Следить за пробоем ${_fmt_price(bb_u)} для подтверждения роста."
    elif bias_score <= -3:
        rec = f"Медвежий наклон. Потеря ${_fmt_price(bb_l)} может ускорить снижение. Нужен контроль риска."
    else:
        rec = f"Нейтральный сценарий. Ключевой диапазон: ${_fmt_price(bb_l)} — ${_fmt_price(bb_u)}."

    return (
        f"{pretty}: ${_fmt_price(price)}\n\n"
        "Технический анализ:\n"
        f"• RSI {rsi_15:.2f} - {rsi_text}\n"
        f"• Цена {'выше' if above_ema_15 else 'ниже'} EMA(50) на 15м и {'выше' if above_ema_1h else 'ниже'} на 1ч\n"
        f"• Изменение цены за 24ч: {price_change_24h:+.2f}%\n"
        f"• Объем {'ниже' if vol_ratio < 1 else 'выше'} среднего ({vol_ratio:.2f}x, {vol_pct_vs_avg:+.1f}%)\n"
        f"• MACD {macd_text}\n"
        f"• Bollinger Bands: цена в {'верхней' if bb_pos >= 0.5 else 'нижней'} половине канала ({bb_pos:.2f})\n\n"
        "Ключевые уровни:\n"
        f"• Сопротивление: ${_fmt_price(bb_u)} (верхняя полоса BB)\n"
        f"• Поддержка: ${_fmt_price(bb_l)} (нижняя полоса BB)\n"
        f"• EMA(50) 4ч: ${_fmt_price(ema50_4h)} (ближайший уровень)\n\n"
        "Рекомендация:\n"
        f"{rec}"
    )



def _extract_pair_from_free_text(text: str, fallback_pair: str = "BTC/USDT") -> str:
    raw = (text or "").lower().replace("\n", " ")
    tokens = [t.strip(" ,.!?;:()[]{}") for t in raw.split() if t.strip()]
    for t in tokens:
        resolved = resolve_binance_pair_input(t)
        if resolved.get("ok"):
            return resolved["pair"]
    resolved = resolve_binance_pair_input(raw)
    if resolved.get("ok"):
        return resolved["pair"]
    return fallback_pair


def _extract_rr(text: str) -> tuple[int, int]:
    raw = (text or "").lower().replace(" ", "")
    variants = ["r:r", "rr", "рр", "riskreward", "рискревард"]
    for v in variants:
        raw = raw.replace(v, "")
    for sep in [":", "к", "x", "х", "/", "to"]:
        if sep in raw:
            parts = raw.split(sep)
            for i in range(len(parts) - 1):
                a = "".join(ch for ch in parts[i] if ch.isdigit())
                b = "".join(ch for ch in parts[i + 1] if ch.isdigit())
                if a and b and int(a) > 0 and int(b) > 0:
                    return int(a), int(b)
    return 1, 2


def generate_trade_setup(user_text: str, default_pair: str = "BTC/USDT", api_key: str = "") -> str:
    pair = _extract_pair_from_free_text(user_text, fallback_pair=default_pair)
    symbol = pair.replace("/", "")
    text = (user_text or "").lower()
    direction = (
        "LONG"
        if any(k in text for k in ["лонг", "long", "buy", "покуп"])
        else "SHORT"
        if any(k in text for k in ["шорт", "short", "sell", "продаж"])
        else "LONG"
    )
    rr_risk, rr_reward = _extract_rr(text)

    try:
        price = _fetch_binance_price(symbol, api_key=api_key)
        closes_4h, _ = _fetch_binance_klines(symbol, "4h", 220, api_key=api_key)
        closes_1h, _ = _fetch_binance_klines(symbol, "1h", 220, api_key=api_key)
    except Exception as e:
        return f"⚠️ Не удалось собрать сетап: {e}"

    atr_base = statistics.pstdev(closes_4h[-30:]) if len(closes_4h) >= 30 else max(price * 0.02, 1e-8)
    stop_pct = max(2.5, min(7.5, (atr_base / price) * 100 * 1.8))
    take_pct = stop_pct * (rr_reward / rr_risk)

    if direction == "LONG":
        sl = price * (1 - stop_pct / 100)
        tp = price * (1 + take_pct / 100)
        header = f"🎯 ЛОНГ {symbol} с R:R {rr_risk}:{rr_reward}"
    else:
        sl = price * (1 + stop_pct / 100)
        tp = price * (1 - take_pct / 100)
        header = f"🎯 ШОРТ {symbol} с R:R {rr_risk}:{rr_reward}"

    ema50_1h = _ema(closes_1h, 50)[-1]
    ema200_1h = _ema(closes_1h, 200)[-1] if len(closes_1h) >= 200 else _ema(closes_1h, 50)[-1]
    rsi_1h = _rsi(closes_1h, 14)
    trend = "бычий" if ema50_1h > ema200_1h else "медвежий"

    return (
        f"{header}\n\n"
        f"💰 Вход: {_fmt_price(price)} USDT\n"
        f"⏱ ТФ: 4h (свинг-трейдинг)\n"
        f"🎯 Стоп-лосс: {stop_pct:.1f}% → {_fmt_price(sl)}\n"
        f"🎯 Тейк-профит: {take_pct:.1f}% → {_fmt_price(tp)}\n"
        f"📊 Риск-ревард: {rr_risk}:{rr_reward}\n\n"
        "📈 Технические факторы:\n"
        f"• RSI 1h: {rsi_1h:.2f}\n"
        f"• Тренд 1h: EMA50 {'>' if ema50_1h > ema200_1h else '<'} EMA200 ({trend})\n"
        "• Контроль: вход только после подтверждения импульса по свечам и объёму"
    )
