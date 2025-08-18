import time
import logging
import json
import base64
from re import search

from playwright.sync_api import sync_playwright, TimeoutError
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from event_api import get_eventbrite_event_details
from event_api import insert_into_google_sheet
from dotenv import load_dotenv
from open_ai import extract_event_filters_and_generate_url
from telegram import get_updates, send_message, get_latest_offset
import os

# Load variables from .env file into environment
load_dotenv()

# Access the environment variables
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
TELEGRAM_TOKEN:str = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
MODEL_NAME = os.getenv("MODEL_NAME")
FILE_NAME1 = os.getenv("FILE_NAME1")
FILE_NAME2 = os.getenv("FILE_NAME2")
#CREDENTIALS_FILE = os.getenv("CREDENTIALS_FILE")
EVENTBRITE_TOKEN = os.getenv("EVENTBRITE_TOKEN")

# Read Base64 string from environment variable
creds_b64 = os.getenv("GOOGLE_CREDENTIALS")
creds_b64 = creds_b64.strip()

# Fix padding
missing_padding = len(creds_b64) % 4
if missing_padding:
    creds_b64 += '=' * (4 - missing_padding)
# Decode Base64 back to JSON
creds_json = base64.b64decode(creds_b64).decode("utf-8")
creds_dict = json.loads(creds_json)

HELP_MESSAGE = """
🤖 I can help you find events from Eventbrite.

<b>Example Query:</b>
Find free yoga events next week in Paris

<b>Format:</b>
[Event type] [Date/Time] [Location]
Example: "Find tech meetups in New York this weekend"

You can also send:
- "Help" → to see this message again
"""

# ---------------- GOOGLE SHEETS SETUP ----------------
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
#creds = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE, scope)
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)
sheet = client.open(FILE_NAME1).sheet1


# Write headers (once)
if sheet.row_count < 1 or sheet.cell(1, 1).value != "Title":
    sheet.resize(rows=1)
    sheet.insert_row(["Title", "URL", "Event ID"], 1)

# ---------------- LOGGING SETUP ----------------
class WhiteFormatter(logging.Formatter):
    WHITE = '\033[97m'
    RESET = '\033[0m'

    def format(self, record):
        msg = super().format(record)
        return f"{self.WHITE}{msg}{self.RESET}"

formatter = WhiteFormatter('%(asctime)s - %(levelname)s - %(message)s')
handler = logging.StreamHandler()
handler.setFormatter(formatter)

logger = logging.getLogger()
logger.setLevel(logging.INFO)
logger.addHandler(handler)

# ---------------- CONFIGURATION ----------------
SEARCH_KEYWORDS = ["wellbeing"]
LOCATION = "france--paris"
MAX_SCROLL_ATTEMPTS = 5

# Running the Telegram Bot
formatted_url = ""

def run_telegram_bot():
    offset = get_latest_offset(TELEGRAM_TOKEN)  # skip old messages
    #offset = None
    print("🤖 Bot is running...")

    while True:
        updates = get_updates(offset,TELEGRAM_TOKEN)
        if "result" in updates:
            for update in updates["result"]:
                offset = update["update_id"] + 1
                message = update.get("message", {}).get("text")
                chat_id = update.get("message", {}).get("chat", {}).get("id")

                if message:
                    print(f"📨 Received: {message}")
                     # If greeting/help keyword
                    if message.lower() in ["help", "/help", "hi", "hello"]:
                        send_message(chat_id, HELP_MESSAGE, TELEGRAM_TOKEN)
                        continue
                    try:
                        response = extract_event_filters_and_generate_url(message,OPENAI_API_KEY,MODEL_NAME)
                        #print(response)
                        # If response is invalid or missing formatted_url
                        if not response or 'formatted_url' not in response or not response['formatted_url']:
                            send_message(chat_id, HELP_MESSAGE, TELEGRAM_TOKEN)
                            continue
                        send_message(chat_id, response,TELEGRAM_TOKEN)
                        formatted_url = response['formatted_url']
                        print(f"<UNK> Received: {formatted_url}")
                    except Exception as e:
                        print(f"⚠️ Parsing error: {e}")
                        send_message(chat_id, HELP_MESSAGE, TELEGRAM_TOKEN)
                        continue

                    #Start to find the events
                    if formatted_url:

                        def get_existing_event_ids():
                            try:
                                col = sheet.col_values(3)  # Column C (event_id), 1-indexed
                                return set(col[1:])  # Skip header
                            except Exception as e:
                                logging.error(f"Failed to get existing event IDs: {e}")
                                return set()

                        def extract_event_data(card):
                            event_data = {}
                            title_element = card.query_selector('[target="_blank"]')
                            try:
                                if title_element:
                                    title = title_element.get_attribute('aria-label')
                                    if title and title.startswith("View"):
                                        title = title[4:].strip()
                                    url = title_element.get_attribute('href')
                                    event_id = title_element.get_attribute('data-event-id')
                                    event_data = {
                                        'title': title,
                                        'url': url,
                                        'event_id': event_id
                                    }
                                    print(f'✅ Title: {title}')
                                    print(f'✅ URL: {url}')
                                    print(f'✅ Event ID: {event_id}')
                                    time.sleep(1)
                                else:
                                    event_data = {'title': 'N/A', 'url': 'N/A', 'event_id': 'N/A'}
                            except Exception as e:
                                logging.error(f"Error: {e}")
                            return event_data

                        def scrape_eventbrite(playwright):
                            browser = playwright.chromium.launch(headless=True)
                            context = browser.new_context(user_agent="Mozilla/5.0 ...")
                            page = context.new_page()

                            for keyword in SEARCH_KEYWORDS:
                                existing_ids = get_existing_event_ids()

                                print(f"--- Starting search for keyword: '{keyword}' ---")
                                #formatted_keyword = keyword.replace(" ", "-")
                                #search_url = f"https://www.eventbrite.com/d/{LOCATION}/{formatted_keyword}--events/"
                                search_url = formatted_url
                                try:
                                    logging.info(f"Navigating to: {search_url}")
                                    page.goto(search_url, wait_until="domcontentloaded", timeout=90000)
                                    page.wait_for_selector('header[class="search-header"]', timeout=60000)
                                    logging.info("Event list container loaded.")
                                except TimeoutError:
                                    logging.warning(f"Timeout for '{keyword}', skipping.")
                                    continue

                                # Scroll and load more
                                for i in range(MAX_SCROLL_ATTEMPTS):
                                    try:
                                        logging.info(f"Scrolling attempt {i + 1}")
                                        page.keyboard.press("End")
                                        time.sleep(3)
                                        show_more = page.query_selector('button[data-testid="load-more-events-button"]')
                                        if show_more and show_more.is_visible():
                                            show_more.click()
                                            time.sleep(5)
                                        else:
                                            break
                                    except Exception as e:
                                        logging.warning(f"Scroll error: {e}")
                                        break

                                event_cards = page.query_selector_all(
                                    'li > div[class*="SearchResultPanelContentEventCardList"]')
                                print(f"Total visible events: {len(event_cards)}")

                                for card in event_cards:
                                    try:
                                        event = extract_event_data(card)
                                        if event['url'] != 'N/A' and event['event_id'] not in existing_ids:
                                            sheet.append_row([event['title'], event['url'], event['event_id']])
                                            logging.info(f"Inserted event into Google Sheet: {event['title']}")
                                            existing_ids.add(event['event_id'])  # update in memory
                                            event_id = event['event_id']
                                            try:
                                                data = get_eventbrite_event_details(event_id, EVENTBRITE_TOKEN)
                                                insert_into_google_sheet(FILE_NAME2, creds_dict, data,
                                                                         TELEGRAM_TOKEN, TELEGRAM_CHAT_ID,
                                                                         OPENAI_API_KEY, MODEL_NAME)
                                                '''
                                                for k, v in data.items():
                                                    print(f"{k}: {v}\n")
                                                '''
                                            except Exception as e:
                                                print("❌ Error:", str(e))
                                        else:
                                            logging.info(f"Duplicate event skipped: {event['event_id']}")
                                    except Exception as e:
                                        logging.error(f"Extraction error: {e}")

                            context.close()
                            browser.close()

                        logging.info("Starting Eventbrite scraper...")
                        with sync_playwright() as playwright:
                            scrape_eventbrite(playwright)

                    time.sleep(1)

if __name__ == "__main__":
    run_telegram_bot()
   
