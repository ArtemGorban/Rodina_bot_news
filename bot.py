import os
import json
import asyncio
import html
import requests
import feedparser
import telegram
from bs4 import BeautifulSoup
from telegram.error import TelegramError
from telegram.request import HTTPXRequest
from telegram.constants import ParseMode

# --- КОНФИГУРАЦИЯ ---
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

RSS_FEED_URL = "https://www.sport-express.ru/services/materials/news/football/se/"
# ВАЖНО: не забудьте вернуть сюда "родин", если меняли на "футбол" для теста!
KEYWORDS = ["футбол",]
#["родин", "rodina"]
STATE_FILE = "sent_news_v3.json" # тут поменять с v3 на v2


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


def get_og_image(url):
    """Скачивает страницу новости и ищет картинку в мета-теге og:image."""
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        meta = soup.find("meta", property="og:image")
        if meta and meta.get("content"):
            return meta.get("content")
    except Exception as e:
        print(f"Не удалось получить картинку с сайта: {e}")
    return None


def fetch_news():
    feed = feedparser.parse(RSS_FEED_URL)
    if feed.bozo and not feed.entries:
        print(f"Ошибка при чтении RSS: {feed.bozo_exception}")
        return []

    items = []
    for entry in feed.entries:
        title = entry.get("title", "").strip()
        link = entry.get("link", "").strip()
        summary_html = entry.get("summary", "")
        
        if not (title and link):
            continue

        soup = BeautifulSoup(summary_html, "html.parser")
        img_tag = soup.find("img")
        image_url = img_tag.get("src") if img_tag else None

        clean_text = soup.get_text(strip=True)
        clean_text = " ".join(clean_text.split())

        items.append({
            "title": title,
            "link": link,
            "text": clean_text,
            "image_url": image_url
        })
    return items


def filter_news(items, sent_links):
    result = []
    for item in items:
        haystack = (item["title"] + " " + item["text"]).lower()
        if any(kw.lower() in haystack for kw in KEYWORDS) and item["link"] not in sent_links:
            result.append(item)
    return result


async def send_to_telegram(items):
    if not items:
        print("Новых новостей не найдено.")
        return []

    sent = []
    request = HTTPXRequest(
        connect_timeout=30.0, read_timeout=30.0,
        write_timeout=30.0, pool_timeout=30.0,
    )
    bot = telegram.Bot(token=TELEGRAM_BOT_TOKEN, request=request)

    try:
        for item in items:
            # Если в RSS картинки не было — идем за ней на сайт
            if not item["image_url"]:
                print(f"Картинка в RSS не найдена, ищем на сайте: {item['link']}")
                item["image_url"] = get_og_image(item["link"])

            safe_title = html.escape(item["title"])
            safe_link = html.escape(item["link"])
            
            # Ограничиваем длину текста (лимит подписи к фото — 1024 символа)
            short_text = item["text"][:800] + "..." if len(item["text"]) > 800 else item["text"]
            safe_text = html.escape(short_text)

            caption = (
                f"<b>{safe_title}</b>\n\n"
                f"{safe_text}\n\n"
            )

            delivered = False
            for attempt in range(3):
                try:
                    if item["image_url"]:
                        # Отправляем как ФОТО с подписью
                        await bot.send_photo(
                            chat_id=TELEGRAM_CHAT_ID,
                            photo=item["image_url"],
                            caption=caption,
                            parse_mode=ParseMode.HTML,
                        )
                    else:
                        # Если картинки вообще нигде нет, отправляем текст
                        # disable_web_page_preview=True скроет тот самый серый блок
                        await bot.send_message(
                            chat_id=TELEGRAM_CHAT_ID,
                            text=caption,
                            parse_mode=ParseMode.HTML,
                            disable_web_page_preview=True,
                        )
                    
                    print(f"Отправлено: {item['title']}")
                    sent.append(item["link"])
                    delivered = True
                    break
                    
                except telegram.error.NetworkError as e:
                    print(f"Сетевая ошибка (попытка {attempt + 1}/3): {e}")
                    if attempt < 2:
                        await asyncio.sleep(5)
                except TelegramError as e:
                    print(f"Ошибка Telegram: {e}")
                    break
                    
            if not delivered:
                print(f"Не удалось отправить: {item['title']}")
    finally:
        try:
            await bot.shutdown()
        except Exception as e:
            print(f"Ошибка при закрытии соединения: {e}")
    return sent


def main():
    print("Запуск проверки новостей...")
    sent_links = load_sent_links()
    print(f"Ранее отправлено ссылок: {len(sent_links)}")

    all_news = fetch_news()
    print(f"Найдено в RSS: {len(all_news)}")

    fresh = filter_news(all_news, sent_links)
    print(f"Подходящих новых: {len(fresh)}")

    successfully_sent = asyncio.run(send_to_telegram(fresh))

    sent_links.update(successfully_sent)
    if len(sent_links) > 5000:
        sent_links = set(sorted(sent_links)[-5000:])
    save_sent_links(sent_links)

    print("Готово.")


if __name__ == "__main__":
    main()
