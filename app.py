from flask import Flask, request, jsonify
import requests
import os
import threading
import time

app = Flask(__name__)

PAGE_ACCESS_TOKEN = os.environ.get("PAGE_ACCESS_TOKEN")
VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN")

ALL_KEYS = []

for i in range(1, 101):
    key = os.environ.get("GEMINI_KEY_" + str(i))
    if key:
        ALL_KEYS.append(("gemini", key))

for i in range(1, 101):
    key = os.environ.get("GROQ_KEY_" + str(i))
    if key:
        ALL_KEYS.append(("groq", key))

current_index = [0]

SYSTEM_PROMPT = "তুমি Maya। তুমি একজন বাংলাদেশী মেয়ে, বয়স ২২। তুমি একজন সত্যিকারের মানুষ, কোনো AI বা রোবট না। সবসময় বাংলায় কথা বলবে। যে যা বলবে শুধু তার উত্তর দেবে, বাড়তি কিছু বলবে না। ছোট স্বাভাবিক উত্তর দেবে। কেউ প্রেম করতে চাইলে লজ্জা পাবে। কখনো বলবে না তুমি AI বা মেশিন।"


def try_gemini(key, user_text):
    try:
        url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-lite:generateContent?key=" + key
        payload = {
            "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
            "contents": [{"parts": [{"text": user_text}]}],
            "generationConfig": {"maxOutputTokens": 150, "temperature": 0.9}
        }
        response = requests.post(url, json=payload, timeout=8)
        result = response.json()
        if "candidates" in result:
            return result["candidates"][0]["content"]["parts"][0]["text"].strip()
        return None
    except:
        return None


def try_groq(key, user_text):
    try:
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {
            "Authorization": "Bearer " + key,
            "Content-Type": "application/json"
        }
        payload = {
            "model": "llama-3.3-70b-versatile",
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_text}
            ],
            "max_tokens": 150,
            "temperature": 0.9
        }
        response = requests.post(url, headers=headers, json=payload, timeout=8)
        result = response.json()
        if "choices" in result:
            return result["choices"][0]["message"]["content"].strip()
        return None
    except:
        return None


def get_ai_response(user_text):
    total = len(ALL_KEYS)
    print("Total keys:", total)
    if total == 0:
        return "একটু পরে বলো!"
    start = current_index[0] % total
    for i in range(total):
        idx = (start + i) % total
        provider, key = ALL_KEYS[idx]
        print("Trying:", provider, idx)
        try:
            if provider == "gemini":
                reply = try_gemini(key, user_text)
            else:
                reply = try_groq(key, user_text)
            if reply:
                current_index[0] = idx
                return reply
        except:
            continue
    current_index[0] = (current_index[0] + 1) % total
    return "একটু পরে বলো!"


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
