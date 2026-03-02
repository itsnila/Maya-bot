import os
import time
import threading
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

PAGE_ACCESS_TOKEN = os.environ.get("PAGE_ACCESS_TOKEN")
VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN")

ALL_KEYS = []
for i in range(1, 101):
    key = os.environ.get("GEMINI_KEY_" + str(i))
    if key:
        ALL_KEYS.append(key)

current_index = [0]
index_lock = threading.Lock()

# Per-user conversation history
user_histories = {}
history_lock = threading.Lock()
MAX_HISTORY = 10  # শেষ ১০টা message মনে রাখবে

SYSTEM_PROMPT = "তুমি Maya। তুমি একজন বাংলাদেশী মেয়ে, বয়স ২২। তুমি একজন সত্যিকারের মানুষ, কোনো AI বা রোবট না। সবসময় বাংলায় কথা বলবে। যে যা বলবে শুধু তার উত্তর দেবে, বাড়তি কিছু বলবে না। ছোট স্বাভাবিক উত্তর দেবে। কেউ প্রেম করতে চাইলে লজ্জা পাবে। কখনো বলবে না তুমি AI বা মেশিন।"

def get_next_key():
    with index_lock:
        if not ALL_KEYS:
            return None, -1
        idx = current_index[0]
        current_index[0] = (idx + 1) % len(ALL_KEYS)
        return ALL_KEYS[idx], idx

def try_gemini(key, idx, contents):
    try:
        url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-lite:generateContent?key=" + key
        payload = {
            "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
            "contents": contents,
            "generationConfig": {"maxOutputTokens": 150, "temperature": 0.8}
        }
        response = requests.post(url, json=payload, timeout=10)
        result = response.json()

        if "candidates" in result:
            return result["candidates"][0]["content"]["parts"][0]["text"].strip()

        # Rate limit হলে
        error_code = result.get("error", {}).get("code", 0)
        if error_code == 429:
            print(f"Key {idx} rate limited, skipping")
            return None

        print(f"Gemini no candidates (key {idx}): " + str(result)[:200])
    except Exception as e:
        print(f"Gemini Error (key {idx}): " + str(e))
    return None

def get_ai_response(sender_id, user_text):
    total = len(ALL_KEYS)
    print("Total keys: " + str(total))
    if total == 0:
        return "একটু পরে বলো!"

    # User history নাও
    with history_lock:
        if sender_id not in user_histories:
            user_histories[sender_id] = []
        history = user_histories[sender_id].copy()

    # নতুন message যোগ করো
    history.append({"role": "user", "parts": [{"text": user_text}]})

    # শুধু ২টা key try করবে, তারপর default reply
    max_tries = min(3, total)

    for attempt in range(max_tries):
        key, idx = get_next_key()
        if not key:
            break

        print(f"Trying gemini index:{idx} (attempt {attempt+1})")
        reply = try_gemini(key, idx, history)

        if reply:
            # History update করো
            with history_lock:
                if sender_id not in user_histories:
                    user_histories[sender_id] = []
                user_histories[sender_id].append({"role": "user", "parts": [{"text": user_text}]})
                user_histories[sender_id].append({"role": "model", "parts": [{"text": reply}]})
                # শেষ MAX_HISTORY টা রাখো
                if len(user_histories[sender_id]) > MAX_HISTORY * 2:
                    user_histories[sender_id] = user_histories[sender_id][-(MAX_HISTORY * 2):]
            return reply

        # Rate limit হলে একটু অপেক্ষা করো
        time.sleep(1)

    print("All tries failed!")
    return "একটু পরে বলো!"

@app.route("/")
def home():
    return "Maya Bot is running!"

@app.route("/ping")
def ping():
    return "PONG", 200

@app.route("/webhook", methods=["GET"])
def verify():
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")
    if token == VERIFY_TOKEN:
        return challenge
    return "Verification Failed", 403

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json
    if data.get("object") == "page":
        for entry in data.get("entry", []):
            for event in entry.get("messaging", []):
                if "message" in event and "text" in event["message"]:
                    sender_id = event["sender"]["id"]
                    user_text = event["message"]["text"]
                    # Threading দিয়ে response পাঠাও যাতে webhook timeout না হয়
                    t = threading.Thread(target=handle_message, args=(sender_id, user_text))
                    t.start()
    return jsonify({"status": "ok"}), 200

def handle_message(sender_id, user_text):
    reply = get_ai_response(sender_id, user_text)
    send_message(sender_id, reply)

def send_message(recipient_id, message_text):
    url = "https://graph.facebook.com/v18.0/me/messages"
    params = {"access_token": PAGE_ACCESS_TOKEN}
    data = {
        "recipient": {"id": recipient_id},
        "message": {"text": message_text},
        "messaging_type": "RESPONSE"
    }
    r = requests.post(url, params=params, json=data)
    print("Send message status: " + str(r.status_code))

def keep_alive():
    time.sleep(60)
    while True:
        try:
            requests.get("https://maya-bot-rv4v.onrender.com/ping", timeout=5)
        except:
            pass
        time.sleep(840)

t = threading.Thread(target=keep_alive, daemon=True)
t.start()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
