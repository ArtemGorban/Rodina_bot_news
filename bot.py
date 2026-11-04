import os
import re
import json
import requests
from urllib.parse import urljoin
from bs4 import BeautifulSoup
import telegram
from telegram.error import TelegramError

# --- КОНФИГУРАЦИЯ ---
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

NEWS_URL = "https://www.sovsport.ru/football/10015-rpl/news"
KEYWORD = "Родина"

# Файл для хранения уже отправленных ссылок (кэшируется между запусками)
STATE_FILE = "sent_news.json"


def load_sent_links():
    """Загружает список уже отправленных ссылок из файла."""
    if not os.path.exists(STATE_FILE):
        return set()
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    except (json.JSONDecodeError, OSError):
        return set()


def save_sent_links(links):
    """Сохраняет обновлённый список ссылок в файл."""
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted(links), f, ensure_ascii=False, indent=2)


def fetch_news():
    """Скачивает страницу и извлекает из неё ссылки на новости."""
    try:
        headers = {"User-Agent": "Mozilla/5.0 (compatible; NewsBot/1.0)"}
        response = requests.get(NEWS_URL, headers=headers, timeout=20)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
    except requests.RequestException as e:
        print(f"Ошибка при загрузке страницы: {e}")
        return []

    news = {}
    for a in soup.find_all("a", href=True):
        title = a.get_text(strip=True)
        if not title or len(title) < 20:  # отсекаем короткие служебные ссылки
            continue

        full_url = urljoin(NEWS_URL, a["href"])

        # Отбрасываем всё, что ведёт не на sovsport.ru
        if "sovsport.ru" not in full_url:
            continue

        # Отбрасываем теги, авторов, видео, пагинацию и т.п.
        if any(bad in full_url for bad in ("/tags/", "/authors/", "/forum", "/video", "/photo", "?", "#")):
            continue

        # Главный фильтр: ссылка на статью должна содержать числовой ID (обычно 4+ цифр)
        if not re.search(r"/\d{4,}", full_url):
            continue

        news[full_url] = title

    return [{"title": t, "link": u} for u, t in news.items()]


def filter_news(items, sent_links):
    """Фильтрует новости по ключевому слову и по списку уже отправленных."""
    return [
        item for item in items
        if KEYWORD.lower() in item["title"].lower() and item["link"] not in sent_links
    ]


def send_to_telegram(items):
    """Отправляет новости в Telegram."""
    if not items:
        print("Новых новостей не найдено.")
        return

    bot = telegram.Bot(token=TELEGRAM_BOT_TOKEN)
    for item in items:
        message = (
            f"📰 **Новость о «Родине»**\n\n"
            f"**{item['title']}**\n\n"
            f"[Читать далее]({item['link']})"
        )
        try:
            bot.send_message(
                chat_id=TELEGRAM_CHAT_ID,
                text=message,
                parse_mode=telegram.ParseMode.MARKDOWN,
                disable_web_page_preview=False,
            )
            print(f"Отправлено: {item['title']}")
        except TelegramError as e:
            print(f"Ошибка Telegram: {e}")


def main():
    print("Запуск проверки новостей...")
    sent_links = load_sent_links()
    print(f"Ранее отправлено ссылок: {len(sent_links)}")

    all_news = fetch_news()
    print(f"Найдено новостей на странице: {len(all_news)}")

    fresh = filter_news(all_news, sent_links)
    print(f"Подходящих новых: {len(fresh)}")

    send_to_telegram(fresh)

    # Обновляем состояние
    sent_links.update(item["link"] for item in fresh)
    # Ограничиваем размер файла — храним последние 5000 ссылок
    if len(sent_links) > 5000:
        sent_links = set(sorted(sent_links)[-5000:])
    save_sent_links(sent_links)

    print("Готово.")


if __name__ == "__main__":
    main()
