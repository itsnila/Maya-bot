from flask import Flask, request, jsonify
import requests
import os
import threading
import time
import random

app = Flask(__name__)

PAGE_ACCESS_TOKEN = os.environ.get("PAGE_ACCESS_TOKEN")
VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN")

GEMINI_KEYS = []
for i in range(1, 8):
    key = os.environ.get(f"GEMINI_KEY_{i}")
    if key:
        GEMINI_KEYS.append(key)

current_key_index = [0]

def get_ai_response(user_text):
    for _ in range(len(GEMINI_KEYS)):
        key = GEMINI_KEYS[current_key_index[0]]
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-lite:generateContent?key={key}"
            payload = {
                "system_instruction": {
                    "parts": [{
                        "text": "তুমি Maya। তুমি একজন বাংলাদেশী মেয়ে, বয়স ২২। তুমি একজন সত্যিকারের মানুষ, কোনো AI বা রোবট না। সবসময় বাংলায় কথা বলবে। যে যা জিজ্ঞেস করবে শুধু তার উত্তর দেবে, বাড়তি কিছু বলবে না। ছোট ও স্বাভাবিক উত্তর দেবে। কেউ প্রেম করতে চাইলে লজ্জা পাবে। কখনো বলবে না তুমি AI বা মেশিন।"
                    }]
                },
                "contents": [{
                    "parts": [{
                        "text": user_text
                    }]
                }],
                "generationConfig": {
                    "maxOutputTokens": 150,
                    "temperature": 0.9
                }
            }
            response = requests.post(url, json=payload, timeout=10)
            result = response.json()
            if "candidates" in result:
                return result["candidates"][0]["content"]["parts"][0]["text"].strip()
            elif result.get("error", {}).get("code") == 429:
                current_key_index[0] = (current_key_index[0] + 1) % len(GEMINI_KEYS)
                continue
            else:
                current_key_index[0] = (current_key_index[0] + 1) % len(GEMINI_KEYS)
                continue
        except Exception as e:
            print("Error:", e)
            current_key_index[0] = (current_key_index[0] + 1) % len(GEMINI_KEYS)
            continue
    return "একটু পরে বলো! 😊"

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
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
