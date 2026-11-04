import os
import json
import asyncio
import requests
import telegram
from telegram.error import TelegramError
from telegram.request import HTTPXRequest
from telegram.constants import ParseMode

# --- КОНФИГУРАЦИЯ ---
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

TEAM_ID = 6822
BASE_URL = "https://api.sstats.net"
STATE_FILE = "last_match_id.txt"


def get_last_sent_match_id():
    if not os.path.exists(STATE_FILE):
        return None
    try:
        with open(STATE_FILE, "r") as f:
            return f.read().strip()
    except Exception:
        return None


def save_last_sent_match_id(match_id):
    with open(STATE_FILE, "w") as f:
        f.write(str(match_id))


def get_last_match_id():
    """Возвращает ID последнего завершённого матча «Родины»."""
    url = f"{BASE_URL}/Games/list"
    params = {
        "team": TEAM_ID,
        "ended": "true",
        "order": -1,
        "limit": 1,
        "timeZone": 3,
    }
    try:
        resp = requests.get(url, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        games = data.get("data", [])
        if not games:
            print("Завершённых матчей не найдено.")
            return None
        return games[0]["id"]
    except requests.HTTPError as e:
        print(f"HTTP-ошибка {e.response.status_code}: {e.response.text}")
        return None
    except Exception as e:
        print(f"Ошибка при поиске матча: {e}")
        return None


def get_match_stats(match_id):
    """Загружает статистику матча по его ID."""
    url = f"{BASE_URL}/Games/{match_id}"
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        
        # --- ВРЕМЕННАЯ ОТЛАДКА ---
        print("=== СЫРЫЕ ДАННЫЕ ОТ API (первые 5000 символов) ===")
        print(json.dumps(data, indent=2, ensure_ascii=False)[:5000])
        print("===================================================")
        # --------------------------
        
        return data
    except Exception as e:
        print(f"Ошибка при загрузке статистики матча: {e}")
        return None


def build_message(data):
    if not data:
        return "Не удалось получить данные о матче."

    home_team = data.get("homeTeam", {}).get("name", "Хозяева")
    away_team = data.get("awayTeam", {}).get("name", "Гости")
    home_score = data.get("homeFTResult", 0)
    away_score = data.get("awayFTResult", 0)
    round_name = data.get("roundName", "?")

    if "Rodina" in home_team or "Родина" in home_team:
        match_title = f"Родина — {away_team}"
    else:
        match_title = f"{home_team} — Родина"

    lines = [
        f"⚽ *{round_name}*",
        f"*{match_title}*",
        f"Счёт: *{home_score} : {away_score}*",
        "",
    ]

    player_stats = data.get("playerStats", {})
    home_team_id = data.get("homeTeam", {}).get("id")

    home_goals, away_goals = [], []
    home_yellow, away_yellow = [], []
    home_red, away_red = [], []

    for p_id, stats in player_stats.items():
        name = stats.get("playerName", "Неизвестный")
        team_id = stats.get("teamId")
        is_home = (team_id == home_team_id)

        if stats.get("goalsTotal", 0) > 0:
            (home_goals if is_home else away_goals).append(name)
        if stats.get("cardsYellow", 0) > 0:
            (home_yellow if is_home else away_yellow).append(name)
        if stats.get("cardsRed", 0) > 0:
            (home_red if is_home else away_red).append(name)

    if home_goals or away_goals:
        lines.append("🔹 *Голы:*")
        if home_goals:
            lines.append(f"  {home_team}: {', '.join(home_goals)}")
        if away_goals:
            lines.append(f"  {away_team}: {', '.join(away_goals)}")
        lines.append("")

    if home_yellow or away_yellow or home_red or away_red:
        lines.append("🔸 *Карточки:*")
        for name in home_yellow:
            lines.append(f"  🟨 {name} ({home_team})")
        for name in away_yellow:
            lines.append(f"  🟨 {name} ({away_team})")
        for name in home_red:
            lines.append(f"  🟥 {name} ({home_team})")
        for name in away_red:
            lines.append(f"  🟥 {name} ({away_team})")

    return "\n".join(lines).strip()


async def send_to_telegram(text):
    if not text:
        return

    request = HTTPXRequest(
        connect_timeout=30.0, read_timeout=30.0,
        write_timeout=30.0, pool_timeout=30.0,
    )
    bot = telegram.Bot(token=TELEGRAM_BOT_TOKEN, request=request)

    try:
        await bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=text,
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True,
        )
        print("Сообщение отправлено в Telegram.")
    except Exception as e:
        print(f"Ошибка при отправке: {e}")
    finally:
        try:
            await bot.shutdown()
        except Exception:
            pass


def main():
    last_sent_id = get_last_sent_match_id()
    print(f"Последний отправленный матч: {last_sent_id}")

    print("Поиск последнего завершённого матча...")
    match_id = get_last_match_id()

    if not match_id:
        print("Матч не найден. Выход.")
        return

    if str(match_id) == last_sent_id:
        print(f"Матч {match_id} уже был отправлен ранее. Пропускаем.")
        return

    print(f"Новый матч! ID: {match_id}")
    data = get_match_stats(match_id)

    if not data:
        print("Не удалось загрузить статистику.")
        return

    message = build_message(data)
    print("\n" + "=" * 40)
    print(message)
    print("=" * 40)

    print("Отправка в Telegram...")
    asyncio.run(send_to_telegram(message))

    save_last_sent_match_id(match_id)


if __name__ == "__main__":
    main()
