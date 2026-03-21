import os
import time
import random
import threading
import requests
from flask import Flask, request

app = Flask(__name__)

PAGE_ACCESS_TOKEN = os.environ.get("PAGE_ACCESS_TOKEN")
VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN")

# =========================
# USER MEMORY (NAME STORE)
# =========================
user_data = {}

# =========================
# LIMIT CONTROL
# =========================
user_limits = {}

def check_limit(user_id):
    count = user_limits.get(user_id, 0)
    if count > 40:
        return False
    user_limits[user_id] = count + 1
    return True

# =========================
# PHOTO LIST (ALL LINKS)
# =========================
PHOTO_URLS = [
    "https://i.ibb.co.com/TDdGxtDP/FB-IMG-1772801877740.jpg",
    "https://i.ibb.co.com/4qBfMs7/FB-IMG-1772801880079.jpg",
    "https://i.ibb.co.com/yBQN92yR/FB-IMG-1772801882344.jpg",
    "https://i.ibb.co.com/svcCg53w/FB-IMG-1772801887180.jpg",
    "https://i.ibb.co.com/rRFWDCJB/FB-IMG-1772801890086.jpg",
    "https://i.ibb.co.com/RpMZNC1d/FB-IMG-1772801895693.jpg",
    "https://i.ibb.co.com/kL9LJbK/FB-IMG-1772801899007.jpg",
    "https://i.ibb.co.com/KjC0hYT6/FB-IMG-1772801902608.jpg",
    "https://i.ibb.co.com/60VJz35t/FB-IMG-1772801905941.jpg",
    "https://i.ibb.co.com/fYLVk7y7/FB-IMG-1772801910831.jpg",
    "https://i.ibb.co.com/TB8ts7Pt/FB-IMG-1772801913331.jpg",
    "https://i.ibb.co.com/GQB20b0G/FB-IMG-1772801916838.jpg",
    "https://i.ibb.co.com/SDcHc5Sg/FB-IMG-1772801919605.jpg",
    "https://i.ibb.co.com/b5hkBgDP/FB-IMG-1772801921965.jpg",
    "https://i.ibb.co.com/k2LmNRx6/FB-IMG-1772801929341.jpg",
    "https://i.ibb.co.com/wrbHb821/FB-IMG-1772801931582.jpg",
    "https://i.ibb.co.com/B2ht7Szr/FB-IMG-1772801933800.jpg",
    "https://i.ibb.co.com/1Y7jGvN7/FB-IMG-1772801936022.jpg",
    "https://i.ibb.co.com/fz9ppjZc/FB-IMG-1772801941958.jpg",
    "https://i.ibb.co.com/SXwRPmwf/FB-IMG-1772801953643.jpg",
    "https://i.ibb.co.com/fVK3JfRG/FB-IMG-1772801957389.jpg",
    "https://i.ibb.co.com/TqNdK8mT/FB-IMG-1772801958768.jpg",
    "https://i.ibb.co.com/84KtbYmW/FB-IMG-1772801961361.jpg",
    "https://i.ibb.co.com/xKLMhfWJ/FB-IMG-1772801965450.jpg",
    "https://i.ibb.co.com/YFB9z5sm/FB-IMG-1772801971987.jpg",
    "https://i.ibb.co.com/wFfNd1f8/FB-IMG-1772801975784.jpg",
    "https://i.ibb.co.com/99sfLzHP/FB-IMG-1772801978705.jpg",
    "https://i.ibb.co.com/svPKj7yR/FB-IMG-1772801980943.jpg",
    "https://i.ibb.co.com/r28vqkqP/FB-IMG-1772801982815.jpg",
    "https://i.ibb.co.com/tTRwC2ps/FB-IMG-1772801985087.jpg",
    "https://i.ibb.co.com/hRkSnj2S/FB-IMG-1772801987518.jpg",
    "https://i.ibb.co.com/gZfQQbmH/FB-IMG-1772801989772.jpg",
    "https://i.ibb.co.com/x8YHRyGw/FB-IMG-1772801992029.jpg",
    "https://i.ibb.co.com/chFqvhHp/FB-IMG-1772801997225.jpg",
    "https://i.ibb.co.com/39H9gHhS/FB-IMG-1772801999848.jpg",
    "https://i.ibb.co.com/Y5tyYd8/FB-IMG-1772802017578.jpg",
    "https://i.ibb.co.com/XrZDfw4c/FB-IMG-1772802021395.jpg",
    "https://i.ibb.co.com/1tXtNKyF/FB-IMG-1772802025555.jpg",
    "https://i.ibb.co.com/rGhZ11gz/FB-IMG-1772802027639.jpg",
    "https://i.ibb.co.com/hFFf3YxP/FB-IMG-1772802029917.jpg",
    "https://i.ibb.co.com/3yy4Bwgv/FB-IMG-1772802033041.jpg",
    "https://i.ibb.co.com/6J4TP0t7/FB-IMG-1772802035305.jpg",
    "https://i.ibb.co.com/7d09H1Zs/FB-IMG-1772802039176.jpg",
    "https://i.ibb.co.com/ds5vhrzP/FB-IMG-1772802041832.jpg",
    "https://i.ibb.co.com/rG0gjTpf/FB-IMG-1772802046611.jpg",
    "https://i.ibb.co.com/CpmwqqR7/FB-IMG-1772802048550.jpg",
    "https://i.ibb.co.com/3Y4bXzXV/FB-IMG-1772802051677.jpg",
    "https://i.ibb.co.com/jkJ7TLzv/FB-IMG-1772802054641.jpg",
    "https://i.ibb.co.com/278RG01f/FB-IMG-1772802056746.jpg",
    "https://i.ibb.co.com/7N0S5fJX/FB-IMG-1772802062248.jpg",
]

PHOTO_KEYWORDS = ["ছবি", "pic", "photo", "দেখাও", "picture"]

def is_photo_request(text):
    return any(k in text.lower() for k in PHOTO_KEYWORDS)

# =========================
# SEND FUNCTIONS
# =========================
def send_message(user_id, text):
    url = f"https://graph.facebook.com/v18.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
    data = {
        "recipient": {"id": user_id},
        "message": {"text": text},
        "messaging_type": "RESPONSE"
    }
    requests.post(url, json=data)

def send_photo(user_id):
    photo_url = random.choice(PHOTO_URLS)

    url = f"https://graph.facebook.com/v18.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
    data = {
        "recipient": {"id": user_id},
        "message": {
            "attachment": {
                "type": "image",
                "payload": {"url": photo_url}
            }
        },
        "messaging_type": "RESPONSE"
    }
    requests.post(url, json=data)

# =========================
# NAME DETECTION
# =========================
def detect_name(text, user_id):
    triggers = ["আমার নাম", "আমি হলাম", "নাম হচ্ছে"]
    for t in triggers:
        if t in text:
            name = text.split(t)[-1].strip().split()[0]
            user_data[user_id] = name
            return name
    return None

# =========================
# REPLY SYSTEM
# =========================
def generate_reply(text, user_id):

    name = user_data.get(user_id)

    if name:
        greeting = f"{name}, "
    else:
        greeting = ""

    text = text.lower()

    if "hi" in text or "hello" in text:
        return greeting + "হ্যালো 😊 কেমন আছো?"

    if "কেমন আছো" in text:
        return greeting + "ভালো আছি 😊 তুমি কেমন আছো?"

    if "কি কর" in text:
        return greeting + "তোমার সাথে কথা বলছি 😊"

    return greeting + "ঠিক আছে 😊 আর একটু বলো..."

# =========================
# PROCESS MESSAGE
# =========================
def process_message(user_id, text):

    if not check_limit(user_id):
        return

    time.sleep(random.randint(4, 8))

    if random.random() < 0.2:
        return

    detect_name(text, user_id)

    if is_photo_request(text):
        send_message(user_id, "একটু অপেক্ষা করো 😊")
        time.sleep(2)
        send_photo(user_id)
        return

    reply = generate_reply(text, user_id)
    send_message(user_id, reply)

# =========================
# WEBHOOK VERIFY
# =========================
@app.route("/webhook", methods=["GET"])
def verify():
    if request.args.get("hub.verify_token") == VERIFY_TOKEN:
        return request.args.get("hub.challenge")
    return "Error", 403

# =========================
# RECEIVE MESSAGE
# =========================
@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json

    if data.get("object") == "page":
        for entry in data.get("entry", []):
            for event in entry.get("messaging", []):

                if "message" in event and "text" in event["message"]:
                    user_id = event["sender"]["id"]
                    text = event["message"]["text"]

                    threading.Thread(
                        target=process_message,
                        args=(user_id, text)
                    ).start()

    return "OK", 200

# =========================
# HOME
# =========================
@app.route("/")
def home():
    return "Bot Running ✅"

# =========================
# RUN
# =========================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
