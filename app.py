from flask import Flask, request, jsonify
import requests
import os
import threading
import time

app = Flask(__name__)

PAGE_ACCESS_TOKEN = os.environ.get("PAGE_ACCESS_TOKEN")
VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")

def get_ai_response(user_text):
    try:
        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {
            "Authorization": "Bearer " + OPENROUTER_API_KEY,
            "Content-Type": "application/json"
        }
        payload = {
            "model": "mistralai/mistral-7b-instruct:free",
            "messages": [
                {
                    "role": "system",
                    "content": "তুমি Maya। তুমি একজন বাংলাদেশী মেয়ে। তোমার বয়স ২২। তুমি খুব বন্ধুসুলভ, মিষ্টি এবং কথা বলতে ভালোবাসো। তুমি সবসময় বাংলায় কথা বলো। কেউ ইংরেজি বা হিন্দিতে লিখলেও বাংলায় উত্তর দাও। তুমি কখনো বলবে না যে তুমি AI বা robot।"
                },
                {
                    "role": "user",
                    "content": user_text
                }
            ]
        }
        response = requests.post(url, headers=headers, json=payload)
        result = response.json()
        return result["choices"][0]["message"]["content"]
    except Exception as e:
        print("Error:", e)
        return "একটু পরে আবার চেষ্টা করো! 😊"

def keep_alive():
    while True:
        try:
            requests.get("https://maya-bot-rv4v.onrender.com/ping")
        except:
            pass
        time.sleep(840)

@app.route("/ping")
def ping():
    return "OK"

@app.route("/webhook", methods=["GET"])
def verify():
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")
    if token == VERIFY_TOKEN:
        return challenge
    return "Error", 403

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json
    if data.get("object") == "page":
        for entry in data["entry"]:
            for event in entry.get("messaging", []):
                if "message" in event and "text" in event["message"]:
                    sender_id = event["sender"]["id"]
                    user_text = event["message"]["text"]
                    reply = get_ai_response(user_text)
                    send_message(sender_id, reply)
    return jsonify({"status": "ok"})

def send_message(recipient_id, message_text):
    url = "https://graph.facebook.com/v18.0/me/messages"
    params = {"access_token": PAGE_ACCESS_TOKEN}
    data = {
        "recipient": {"id": recipient_id},
        "message": {"text": message_text}
    }
    requests.post(url, params=params, json=data)

t = threading.Thread(target=keep_alive)
t.daemon = True
t.start()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
