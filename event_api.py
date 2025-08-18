import requests
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from telegram import send_to_telegram
from open_ai import summarize_event

def get_eventbrite_event_details(event_id: str, token: str) -> dict:
    headers = {
        "Authorization": f"Bearer {token}"
    }

    # --- 1. Event Info ---
    event_url = f"https://www.eventbriteapi.com/v3/events/{event_id}/"
    event_res = requests.get(event_url, headers=headers)
    if not event_res.ok:
        raise Exception(f"Failed to fetch event: {event_res.status_code} - {event_res.text}")
    event = event_res.json()

    # --- 2. Venue Info ---
    venue_data = {}
    if event.get("venue_id"):
        venue_url = f"https://www.eventbriteapi.com/v3/venues/{event['venue_id']}/"
        venue_res = requests.get(venue_url, headers=headers)
        if venue_res.ok:
            venue_data = venue_res.json()

    # --- 3. Organizer Info ---
    organizer_data = {}
    if event.get("organizer_id"):
        organizer_url = f"https://www.eventbriteapi.com/v3/organizers/{event['organizer_id']}/"
        organizer_res = requests.get(organizer_url, headers=headers)
        if organizer_res.ok:
            organizer_data = organizer_res.json()

    map_location = "NA"
    if venue_data.get("latitude") and venue_data.get("latitude"):
        lat = venue_data.get("latitude")
        lon = venue_data.get("longitude")
        map_location =  f"https://www.google.com/maps?q={lat},{lon}"

    # --- 4. Format and Return Combined Info ---
    details = {
        "title": event.get("name", {}).get("text"),
        #"summary": event.get("summary"),
        "description_text": event.get("description", {}).get("text"),
        #"description_html": event.get("description", {}).get("html"),
        "start_local": event.get("start", {}).get("local"),
        "end_local": event.get("end", {}).get("local"),
        "timezone": event.get("start", {}).get("timezone"),
        "created": event.get("created"),
        "changed": event.get("changed"),
        "status": event.get("status"),
        "currency": event.get("currency"),
        #"listed": event.get("listed"),
        "capacity": event.get("capacity"),
        "is_free": event.get("is_free"),
        "online_event": event.get("online_event"),
        "language": event.get("locale"),
        #"category_id": event.get("category_id"),
        #"subcategory_id": event.get("subcategory_id"),
        #"format_id": event.get("format_id"),
        "event_url": event.get("url"),
        #"logo_url": event.get("logo", {}).get("url") if event.get("logo") else None,
        "venue_name": venue_data.get("name"),
        "venue_address": venue_data.get("address", {}).get("localized_address_display"),
        "venue_lat": venue_data.get("latitude"),
        "venue_lon": venue_data.get("longitude"),
        "Google_map_location": map_location,
        "organizer_name": organizer_data.get("name"),
        "organizer_description": organizer_data.get("description", {}).get("text") if organizer_data else None,
        "organizer_url": organizer_data.get("url") if organizer_data else None

    }

    return details

def insert_into_google_sheet(sheet_name: str, credentials_path: str, data: dict, bot_token: str, chat_id: str,openai_api_key: str,model):
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds = ServiceAccountCredentials.from_json_keyfile_name(credentials_path, scope)
    client = gspread.authorize(creds)

    sheet = client.open(sheet_name).sheet1  # Opens the first sheet
    headers = sheet.row_values(1)

    if not headers:
        # Set headers if sheet is empty
        headers = list(data.keys())
        sheet.append_row(headers)

    row = [data.get(header, "") for header in headers]
    sheet.append_row(row)
    print("✅ Data inserted into Google Sheet.")

    # --- Send to Telegram if token and chat_id are provided ---
    if bot_token and chat_id:
        summary = data.get("title", "New event added")

        if openai_api_key:
            summary = summarize_event(data, openai_api_key,model)
        summary += f"\n🔗 {data.get('event_url', '')}"
        send_to_telegram(bot_token, chat_id, summary)


