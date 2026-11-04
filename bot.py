import os
import json
import asyncio
import feedparser
import telegram
from telegram.error import TelegramError

# --- КОНФИГУРАЦИЯ ---
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

RSS_FEED_URL = "https://www.sport-express.ru/services/materials/news/football/se/"
KEYWORDS = ["родин", "rodina"]

# ВАЖНО: имя файла изменено, чтобы старый «грязный» кэш не подхватился
STATE_FILE = "sent_news_v2.json"


def load_sent_links():
    if not os.path.exists(STATE_FILE):
        return set()
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    except (json.JSONDecodeError, OSError):
        return set()


def save_sent_links(links):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted(links), f, ensure_ascii=False, indent=2)


def fetch_news():
    """Скачивает и разбирает RSS-ленту «Спорт-Экспресс»."""
    feed = feedparser.parse(RSS_FEED_URL)
    if feed.bozo and not feed.entries:
        print(f"Ошибка при чтении RSS: {feed.bozo_exception}")
        return []

    items = []
    for entry in feed.entries:
        title = entry.get("title", "").strip()
        link = entry.get("link", "").strip()
        summary = entry.get("summary", "")
        if title and link:
            items.append({"title": title, "link": link, "summary": summary})
    return items


def filter_news(items, sent_links):
    """Фильтрует по ключевым словам и по списку уже отправленных ссылок."""
    result = []
    for item in items:
        haystack = (item["title"] + " " + item["summary"]).lower()
        if any(kw.lower() in haystack for kw in KEYWORDS) and item["link"] not in sent_links:
            result.append(item)
    return result


async def send_to_telegram(items):
    """
    Отправляет новости в Telegram.
    Возвращает список ссылок, которые РЕАЛЬНО ушли в чат.
    Если отправка новости упала — её ссылка в результат не попадёт,
    и при следующем запуске бот попробует снова.
    """
    if not items:
        print("Новых новостей не найдено.")
        return []

    sent = []
    bot = telegram.Bot(token=TELEGRAM_BOT_TOKEN)
    async with bot:
        for item in items:
            message = (
                f"📰 Новость о «Родине»\n\n"
                f"{item['title']}\n\n"
                f"{item['link']}"
            )
            try:
                await bot.send_message(
                    chat_id=TELEGRAM_CHAT_ID,
                    text=message,
                    disable_web_page_preview=False,
                )
                print(f"Отправлено: {item['title']}")
                sent.append(item["link"])
            except TelegramError as e:
                print(f"Ошибка Telegram: {e}")
    return sent


def main():
    print("Запуск проверки новостей...")
    sent_links = load_sent_links()
    print(f"Ранее отправлено ссылок: {len(sent_links)}")

    all_news = fetch_news()
    print(f"Найдено в RSS: {len(all_news)}")

    fresh = filter_news(all_news, sent_links)
    print(f"Подходящих новых: {len(fresh)}")

    # Запоминаем ТОЛЬКО реально отправленные ссылки
    successfully_sent = asyncio.run(send_to_telegram(fresh))

    sent_links.update(successfully_sent)
    if len(sent_links) > 5000:
        sent_links = set(sorted(sent_links)[-5000:])
    save_sent_links(sent_links)

    print("Готово.")


if __name__ == "__main__":
    main()
