import os
import requests
from datetime import datetime

# --- КОНФИГУРАЦИЯ ---
API_KEY = os.environ.get("API_FOOTBALL_KEY")
TEAM_NAME = "Rodina"
LEAGUE_ID = 235          # Российская Премьер-Лига в API-Football[reference:2]
SEASON = 2026
BASE_URL = "https://v3.football.api-sports.io"

HEADERS = {"x-apisports-key": API_KEY}


def find_team_id():
    """Ищет ID команды «Родина» по названию."""
    url = f"{BASE_URL}/teams"
    params = {"search": TEAM_NAME}
    resp = requests.get(url, headers=HEADERS, params=params, timeout=20)
    resp.raise_for_status()
    data = resp.json()

    for team in data.get("response", []):
        if "Rodina" in team["team"]["name"]:
            return team["team"]["id"]
    return None


def get_last_match(team_id):
    """Возвращает последний завершённый матч команды в указанном турнире."""
    url = f"{BASE_URL}/fixtures"
    params = {
        "league": LEAGUE_ID,
        "season": SEASON,
        "team": team_id,
        "status": "FT",   # только завершённые
    }
    resp = requests.get(url, headers=HEADERS, params=params, timeout=20)
    resp.raise_for_status()
    data = resp.json()

    fixtures = data.get("response", [])
    if not fixtures:
        return None

    # API отдаёт в хронологическом порядке — берём последний
    return fixtures[-1]


def get_match_events(fixture_id):
    """Возвращает события матча (голы, карточки)."""
    url = f"{BASE_URL}/fixtures/events"
    params = {"fixture": fixture_id}
    resp = requests.get(url, headers=HEADERS, params=params, timeout=20)
    resp.raise_for_status()
    return resp.json().get("response", [])


def format_card_emoji(card_type):
    """Превращает тип карточки API в emoji."""
    mapping = {
        "Yellow Card": "🟨",
        "Red Card": "🟥",
        "Yellow Red Card": "🟨🟥",
    }
    return mapping.get(card_type, "🟨")


def build_message(match, events):
    """Формирует текст сообщения в заданном формате."""
    home = match["teams"]["home"]["name"]
    away = match["teams"]["away"]["name"]
    home_goals = match["goals"]["home"]
    away_goals = match["goals"]["away"]
    round_num = match["league"]["round"]

    # Определяем порядок: Родина — Соперник или Соперник — Родина
    if "Rodina" in home:
        match_title = f"Родина — {away}"
    else:
        match_title = f"{home} — Родина"

    lines = [
        f"⚽ *Матч {round_num}*",
        f"*{match_title}*",
        f"Счёт: *{home_goals} : {away_goals}*",
        "",
    ]

    # События: голы и карточки
    goal_lines = []
    card_lines = []

    for ev in events:
        minute = ev.get("time", {}).get("elapsed")
        player = ev.get("player", {}).get("name", "Неизвестный")
        team = ev.get("team", {}).get("name", "")
        ev_type = ev.get("type", "")
        detail = ev.get("detail", "")

        if ev_type == "Goal":
            goal_lines.append(f"  ⚽ {minute}' — {player} ({team})")
        elif ev_type == "Card":
            emoji = format_card_emoji(detail)
            card_lines.append(f"  {emoji} {player} ({team})")

    if goal_lines:
        lines.append("🔹 *Голы:*")
        lines.extend(goal_lines)
        lines.append("")

    if card_lines:
        lines.append("🔸 *Карточки:*")
        lines.extend(card_lines)

    return "\n".join(lines).strip()


def main():
    if not API_KEY:
        print("Ошибка: не задан API_FOOTBALL_KEY")
        return

    print("Поиск команды...")
    team_id = find_team_id()
    if not team_id:
        print("Команда «Родина» не найдена.")
        return

    print(f"ID команды: {team_id}")

    print("Поиск последнего матча...")
    match = get_last_match(team_id)
    if not match:
        print("Завершённых матчей в текущем сезоне не найдено.")
        return

    fixture_id = match["fixture"]["id"]
    print(f"Последний матч: {fixture_id} — {match['teams']['home']['name']} vs {match['teams']['away']['name']}")

    print("Загрузка событий...")
    events = get_match_events(fixture_id)

    message = build_message(match, events)
    print("\n" + "=" * 40)
    print(message)
    print("=" * 40)


if __name__ == "__main__":
    main()
