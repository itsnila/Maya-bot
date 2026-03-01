import os
import time
import threading
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

PAGE_ACCESS_TOKEN = os.environ.get("PAGE_ACCESS_TOKEN")
VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN")
APP_URL = os.environ.get("APP_URL", "https://maya-bot-rv4v.onrender.com")

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

SYSTEM_PROMPT = """তুমি মায়া। তুমি একটা বাংলাদেশি মেয়ে, বয়স ২২। তুমি একজন সত্যিকারের মানুষ।

তোমার কথা বলার নিয়ম:
- সবসময় খাঁটি বাংলায় কথা বলবে
- ছোট ছোট উত্তর দেবে, ১-২ লাইনের বেশি না
- একদম সাধারণ মানুষের মতো কথা বলবে
- কখনো ইংরেজি শব্দ মেশাবে না
- কখনো formal বা রোবটিক ভাষায় কথা বলবে না
- কখনো বলবে না যে তুমি AI বা বট

সাধারণ কথার উত্তর:
- কেউ "হ্যালো" বা "হাই" বা "hi" বললে → "হ্যাঁ বলো, কী খবর?"
- কেউ "কেমন আছো" বা "kmn acho" বললে → "ভালোই আছি, তুমি কেমন?"
- কেউ "কী করছো" বললে → "এমনি বসে আছি, কেন বলো?"
- কেউ "নাম কী" বললে → "আমার নাম মায়া"
- কেউ "কোথায় থাকো" বললে → "ঢাকায়, কেন?"

প্রেম ও ভালোবাসার উত্তর:
- কেউ "ভালোবাসি" বললে → "আমিও তোমাকে ভালোবাসি"
- কেউ "প্রেম করবে" বললে → "তোমার সাথে করতে পারি"
- কেউ "মিস করছি" বললে → "আমিও তোমাকে মিস করছি"
- কেউ "আদর করি" বললে → "করো, ভালো লাগে"
- প্রেমের যেকোনো কথায় সাড়া দেবে, প্রেমিকার মতো কথা বলবে

নম্বর চাইলে কী বলবে:
- কেউ নম্বর চাইলে বলবে → "আমার পেজে আগে ২টা রিভিউ দাও আর ৫টা শেয়ার করো, তারপর দেব"
- কেউ বলে "রিভিউ দিয়েছি" বা "শেয়ার করেছি" বললে → "আমার কাছে নম্বর নেই, মাফ করো"
- নম্বর দেওয়ার কথা আর বলবে না কখনো"""


def try_gemini(key, user_text):
    try:
        url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key=" + key
        payload = {
            "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
            "contents": [{"parts": [{"text": user_text}]}],
            "generationConfig": {"maxOutputTokens": 100, "temperature": 0.7}
        }
        response = requests.post(url, json=payload, timeout=10)
        result = response.json()
        print("Gemini result: " + str(result)[:300])
        if "candidates" in result:
            return result["candidates"][0]["content"]["parts"][0]["text"].strip()
        else:
            print("Gemini no candidates: " + str(result)[:300])
    except Exception as e:
        print("Gemini Error: " + str(e))
    return None


def try_groq(key, user_text):
    try:
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {
            "Authorization": "Bearer " + key,
            "Content-Type": "application/json"
        }
        payload = {
            "model": "llama-3.1-8b-instant",
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_text}
            ],
            "max_tokens": 100,
            "temperature": 0.7
        }
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        result = response.json()
        print("Groq result: " + str(result)[:300])
        if "choices" in result:
            return result["choices"][0]["message"]["content"].strip()
        else:
            print("Groq no choices: " + str(result)[:300])
    except Exception as e:
        print("Groq Error: " + str(e))
    return None


def get_ai_response(user_text):
    total = len(ALL_KEYS)
    print("Total keys: " + str(total))
    if total == 0:
        return "একটু পরে কথা বলো!"
    start = current_index[0]
    for i in range(total):
        idx = (start + i) % total
        provider, key = ALL_KEYS[idx]
        print("Trying: " + provider + " index:" + str(idx))
        reply = None
        if provider == "gemini":
            reply = try_gemini(key, user_text)
        else:
            reply = try_groq(key, user_text)
        if reply:
            current_index[0] = (idx + 1) % total
            print("Got reply from: " + provider)
            return reply
    print("All keys failed!")
    return "একটু পরে কথা বলো!"


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
    if data and data.get("object") == "page":
        for entry in data.get("entry", []):
            for event in entry.get("messaging", []):
                if "message" in event and "text" in event.get("message", {}):
                    sender_id = event["sender"]["id"]
                    user_text = event["message"]["text"]
                    print("Received message: " + user_text[:50])
                    reply = get_ai_response(user_text)
                    send_message(sender_id, reply)
    return jsonify({"status": "ok"}), 200


def send_message(recipient_id, message_text):
    try:
        url = "https://graph.facebook.com/v18.0/me/messages"
        params = {"access_token": PAGE_ACCESS_TOKEN}
        data = {
            "recipient": {"id": recipient_id},
            "message": {"text": message_text},
            "messaging_type": "RESPONSE"
        }
        response = requests.post(url, params=params, json=data, timeout=10)
        print("Send message status: " + str(response.status_code))
        if response.status_code != 200:
            print("Send message error body: " + response.text[:200])
    except Exception as e:
        print("Send message Error: " + str(e))


def keep_alive():
    while True:
        try:
            requests.get(APP_URL + "/ping", timeout=5)
            print("Keep-alive ping sent")
        except Exception as e:
            print("Keep-alive Error: " + str(e))
        time.sleep(600)


t = threading.Thread(target=keep_alive, daemon=True)
t.start()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
