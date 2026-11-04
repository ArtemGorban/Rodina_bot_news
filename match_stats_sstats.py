import os
import asyncio
import requests
import telegram
from telegram.error import TelegramError
from telegram.request import HTTPXRequest
from telegram.constants import ParseMode
from datetime import datetime

# --- КОНФИГУРАЦИЯ ---
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

TEAM_ID = 6822
BASE_URL = "https://api.sstats.net"
STATE_FILE = "last_match_id_v3.txt"


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


def get_next_match():
    """Возвращает информацию о ближайшем будущем матче «Родины»."""
    url = f"{BASE_URL}/Games/list"
    params = {
        "team": TEAM_ID,
        "upcoming": "true",
        "order": 1,          # 1 = по возрастанию даты (ближайший матч будет первым)
        "limit": 1,
        "timeZone": 3,
    }
    try:
        resp = requests.get(url, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        games = data.get("data", [])
        if not games:
            return None

        game = games[0]
        # В ответе список игр может быть вложен в "game"
        game_info = game.get("game", game)

        home = game_info.get("homeTeam", {}).get("name", "Хозяева")
        away = game_info.get("awayTeam", {}).get("name", "Гости")
        
        # Ищем дату матча в разных возможных полях
        match_date = game_info.get("date") or game_info.get("startTime") or game_info.get("gameDate")
        
        if not match_date:
            return None

        return {
            "home": home,
            "away": away,
            "date": match_date
        }
    except Exception as e:
        print(f"Ошибка при поиске следующего матча: {e}")
        return None


def get_match_stats(match_id):
    """Загружает полную статистику матча по его ID."""
    url = f"{BASE_URL}/Games/{match_id}"
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        return data
    except Exception as e:
        print(f"Ошибка при загрузке статистики матча: {e}")
        return None


def build_message(data):
    """Формирует сообщение из реальной структуры ответа API."""
    if not data:
        return "Не удалось получить данные о матче."

    payload = data.get("data", data)
    game = payload.get("game", payload)

    home_team_obj = game.get("homeTeam") or game.get("home_team") or {}
    away_team_obj = game.get("awayTeam") or game.get("away_team") or {}

    home_team = home_team_obj.get("name", "Хозяева").replace("Rodina Moskva", "Родина")
    away_team = away_team_obj.get("name", "Гости")
    home_team_id = home_team_obj.get("id")

    home_score = game.get("homeFTResult") or game.get("home_ft_result") or game.get("homeScore") or 0
    away_score = game.get("awayFTResult") or game.get("away_ft_result") or game.get("awayScore") or 0

    round_name = game.get("roundName") or game.get("round") or "?"
    if "Regular Season - " in str(round_name):
        round_name = str(round_name).replace("Regular Season - ", "") + "-й тур"

    lineup_players = payload.get("lineupPlayers") or payload.get("lineup_players") or []
    player_stats_list = payload.get("playerStats") or payload.get("player_stats") or []

    player_names = {}
    player_teams = {}

    if isinstance(lineup_players, list):
        for p in lineup_players:
            pid = p.get("playerId") or p.get("player_id")
            if pid:
                player_names[pid] = p.get("playerName") or p.get("player_name") or f"Игрок {pid}"
                player_teams[pid] = p.get("teamId") or p.get("team_id")

    home_goals, away_goals = [], []
    home_yellow, away_yellow = [], []
    home_red, away_red = [], []

    stats_items = []
    if isinstance(player_stats_list, list):
        stats_items = player_stats_list
    elif isinstance(player_stats_list, dict):
        stats_items = player_stats_list.values()

    for stats in stats_items:
        player_id = stats.get("playerId") or stats.get("player_id")
        name = player_names.get(player_id) or stats.get("playerName") or stats.get("player_name") or f"Игрок {player_id}"
        team_id = player_teams.get(player_id) or stats.get("teamId") or stats.get("team_id")
        
        is_home = (team_id == home_team_id)

        goals = stats.get("goalsTotal") or stats.get("goals_total") or stats.get("goals") or 0
        if goals > 0:
            (home_goals if is_home else away_goals).append(name)

        yellow = stats.get("cardsYellow") or stats.get("cards_yellow") or stats.get("yellow_cards") or 0
        if yellow > 0:
            (home_yellow if is_home else away_yellow).append(name)

        red = stats.get("cardsRed") or stats.get("cards_red") or stats.get("red_cards") or 0
        if red > 0:
            (home_red if is_home else away_red).append(name)

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
            lines.append(f"  [ЖК] {name} ({home_team})")
        for name in away_yellow:
            lines.append(f"  [ЖК] {name} ({away_team})")
        for name in home_red:
            lines.append(f"  [КК] {name} ({home_team})")
        for name in away_red:
            lines.append(f"  [КК] {name} ({away_team})")

    # --- БЛОК СЛЕДУЮЩЕГО МАТЧА ---
    next_match = get_next_match()
    if next_match:
        home = next_match["home"].replace("Rodina Moskva", "Родина")
        away = next_match["away"]
        if "Rodina" in home or "Родина" in home:
            next_title = f"Родина — {away}"
        else:
            next_title = f"{home} — Родина"

        # Парсим дату из ISO формата (например, "2026-11-08T19:00:00Z")
        raw_date = next_match["date"]
        try:
            dt = datetime.fromisoformat(raw_date.replace("Z", "+00:00"))
            date_str = dt.strftime("%d.%m.%Y %H:%M")
        except Exception:
            date_str = raw_date  # если не удалось распарсить, выводим как есть

        lines.append("")
        lines.append("🗓 *Следующий матч:*")
        lines.append(f"  {next_title}")
        lines.append(f"  {date_str}")

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
