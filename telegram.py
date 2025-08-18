import requests

def get_latest_offset(bot_token):
    updates = get_updates(bot_token=bot_token)
    if "result" in updates and updates["result"]:
        last_update_id = updates["result"][-1]["update_id"]
        return last_update_id + 1
    return None

def get_updates(offset=None,bot_token=None):
    url = f'https://api.telegram.org/bot{bot_token}/getUpdates'
    params = {'timeout': 100, 'offset': offset}
    response = requests.get(url, params=params)
    return response.json()

def send_message(chat_id, text,bot_token):
    url = f'https://api.telegram.org/bot{bot_token}/sendMessage'
    payload = {"chat_id": chat_id, "text": text}
    requests.post(url, json=payload)

def send_to_telegram(bot_token: str, chat_id: str, message: str):
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML"
    }
    response = requests.post(url, data=payload)
    if response.status_code != 200:
        print(f"⚠️ Telegram error: {response.text}")
    else:
        print("📬 Sent to Telegram.")

