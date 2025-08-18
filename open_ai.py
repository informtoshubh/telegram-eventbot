import json
from groq import Groq

#extracting event query details and generating the formatted url
def extract_event_filters_and_generate_url(prompt_text: str, openai_api_key: str, model: str):
    system_prompt = """
You are a helpful assistant. Convert a user's natural language event query into a formatted Eventbrite URL. 
If the month and year are not mentioned in the prompt, assume the next upcoming ones. 

Example:
User: Find free yoga events next week in Paris
Response:
{
  "location": "paris",
  "country": "france",
  "keywords": "yoga",
  "date": "next-week",
  "price": "free",
  "formatted_url": "https://www.eventbrite.com/d/france--paris/yoga--events/?price=free&date=next-week"
}
Only respond with a valid JSON object.
"""

    try:
        client = Groq(api_key=openai_api_key)
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt_text}
            ],
            temperature=0.2
        )

        # Extract string content from the response
        content = response.choices[0].message.content.strip()

        # Try parsing to JSON
        try:
            result = json.loads(content)
            if "formatted_url" not in result:
                raise KeyError("formatted_url not found in response")
            return result

        except json.JSONDecodeError:
            print("❌ GPT response was not valid JSON.")
            print("🔎 Raw response:\n", content)
            return {"error": "Invalid JSON from GPT", "raw": content}
        except KeyError as ke:
            print(f"❌ Missing key: {ke}")
            print("🔎 Raw parsed response:\n", content)
            return {"error": str(ke), "raw": content}

    except Exception as e:
        print(f"❌ Exception while calling Groq: {e}")
        return {"error": str(e)}

#summerizing the details of events
def summarize_event(event_data: dict, openai_api_key: str, model:str) -> str:
    # openai.api_key = openai_api_key

    prompt = f"""
                You are an assistant helping users quickly understand event listings.

                Summarize the following event details into a friendly, A description suitable for sending over Telegram. Include the title, date, location (if any), and organizer name, Here is a event url from the event url read the 'About thi event' section. Keep it under 5000 words.

                Event data:
                Title: {event_data.get("title")}
                URL: {event_data.get("url")}
                Start Time: {event_data.get("start_local")}
                Location: {event_data.get("venue_address") or "Online"}
                Organizer: {event_data.get("organizer_name")}
                Description: {event_data.get("description_text")}
                    """

    try:
        # client = openai.OpenAI(api_key=openai_api_key)
        client = Groq(api_key=openai_api_key)
        response = client.chat.completions.create(
            # model="gpt-4o",
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7
        )
        gpt_summary = response.choices[0].message.content.strip()
        print(f'Chat GPT Summary: {gpt_summary}')
        return gpt_summary
    except Exception as e:
        print(f"❌ OpenAI Error: {e}")
        return "Summary not available due to an error."