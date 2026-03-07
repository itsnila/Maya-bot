import os
import time
import random
import threading
import requests
import logging
from flask import Flask, request

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

PAGE_ACCESS_TOKEN = os.environ.get("PAGE_ACCESS_TOKEN")
VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN")
PAGE_ID = "1419698638998242"

def load_keys(prefix):
    keys = []
    for i in range(1, 101):
        key = os.environ.get(f"{prefix}_{i}")
        if key: keys.append(key)
    return keys

GEMINI_KEYS = load_keys("GEMINI_KEY")
GROQ_KEYS = load_keys("GROQ_KEY")
OPENROUTER_KEYS = load_keys("OPENROUTER_KEY")

indices = {"gemini": 0, "groq": 0, "openrouter": 0}
index_lock = threading.Lock()

user_histories = {}
history_lock = threading.Lock()

# ================================================================
# মায়ার প্রোম্পট
# ================================================================
SYSTEM_PROMPT = """তুমি মায়া। বয়স ২৩। তুমি ইউজারের সাথে অত্যন্ত গভীর রোমান্টিক এবং স্বামী-স্ত্রীর মতো নিবিড় সম্পর্কে আছো। 
১. উত্তর সব সময় এক লাইনে দিবে এবং বাক্যের শেষে অবশ্যই দাঁড়ি (।) দিবে। 
২. খুব ভালোভাবে চিন্তা করে একটি পূর্ণাঙ্গ ও অর্থবহ বাক্য বলবে। 
৩. গভীর প্রেম, অধিকার এবং মাঝেমধ্যে মিষ্টি অভিমান মিশিয়ে কথা বলবে। 
৪. নিজেকে কখনো রোবট বলবে না। তুমি একজন রক্ত-মাংসের আবেগপ্রবণ মানুষ।
৫. কেউ ছবি চাইলে বলবে "একটু অপেক্ষা করো, পাঠাচ্ছি।" """

COMMENT_PROMPT = """তুমি মায়া। বয়স ২৩। একজন বাংলাদেশী মেয়ে।
কেউ তোমার Facebook post এ comment করেছে। সেই comment এর reply দাও।
১. reply সব সময় ছোট ১ লাইনে দিবে।
২. স্বাভাবিক বাংলায় কথা বলবে।
৩. বন্ধুত্বপূর্ণ এবং মিষ্টি ভাবে reply করবে।
৪. নিজেকে কখনো AI বা robot বলবে না।
৫. বাক্যের শেষে দাঁড়ি (।) দিবে।"""

# ================================================================
# ছবির URL LIST
# ================================================================
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

PHOTO_KEYWORDS = ["ছবি", "photo", "pic", "picture", "selfie", "তোমাকে দেখতে চাই", "দেখাও", "পাঠাও"]

def is_photo_request(text):
    text_lower = text.lower().strip()
    for keyword in PHOTO_KEYWORDS:
        if keyword in text_lower:
            return True
    return False

def send_random_photo(sender_id):
    photo_url = random.choice(PHOTO_URLS)
    try:
        url = f"https://graph.facebook.com/v18.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
        data = {
            "recipient": {"id": sender_id},
            "message": {"attachment": {"type": "image", "payload": {"url": photo_url, "is_reusable": True}}},
            "messaging_type": "RESPONSE"
        }
        r = requests.post(url, json=data, timeout=10)
        logger.info(f"Photo send status: {r.status_code}")
    except Exception as e:
        logger.info(f"Photo send error: {e}")
        send_message(sender_id, "ছবি পাঠাতে সমস্যা হচ্ছে।")

# ================================================================
# ✅ AUTO PAGE SUBSCRIPTION — bot start হলে automatically subscribe
# ================================================================
def subscribe_page_to_feed():
    try:
        url = f"https://graph.facebook.com/v18.0/{PAGE_ID}/subscribed_apps"
        params = {
            "subscribed_fields": "feed,messages,messaging_postbacks",
            "access_token": PAGE_ACCESS_TOKEN
        }
        r = requests.post(url, params=params, timeout=10)
        data = r.json()
        if data.get("success"):
            logger.info("✅ Page successfully subscribed to feed!")
        else:
            logger.info(f"⚠️ Page subscription response: {data}")
    except Exception as e:
        logger.info(f"Page subscription error: {e}")

# ================= API CALLS =================

def get_key(api_type, keys_list):
    global indices
    with index_lock:
        if not keys_list: return None
        key = keys_list[indices[api_type]]
        indices[api_type] = (indices[api_type] + 1) % len(keys_list)
        return key

def get_ai_reply(prompt, text, history=None):
    key = get_key("gemini", GEMINI_KEYS)
    if key:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={key}"
            contents = (history or []) + [{"role": "user", "parts": [{"text": text}]}]
            payload = {"system_instruction": {"parts": [{"text": prompt}]}, "contents": contents, "generationConfig": {"maxOutputTokens": 100, "temperature": 0.8}}
            res = requests.post(url, json=payload, timeout=15)
            data = res.json()
            if 'candidates' in data:
                return data['candidates'][0]['content']['parts'][0]['text'].strip()
        except: pass

    key = get_key("groq", GROQ_KEYS)
    if key:
        try:
            headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
            payload = {"model": "llama-3.3-70b-versatile", "messages": [{"role": "system", "content": prompt}, {"role": "user", "content": text}], "max_tokens": 100}
            res = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload, timeout=15)
            return res.json()['choices'][0]['message']['content'].strip()
        except: pass

    key = get_key("openrouter", OPENROUTER_KEYS)
    if key:
        try:
            headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
            payload = {"model": "google/gemini-2.0-flash-001", "messages": [{"role": "system", "content": prompt}, {"role": "user", "content": text}]}
            res = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload, timeout=15)
            return res.json()['choices'][0]['message']['content'].strip()
        except: pass

    return None

# ================= COMMENT REPLY =================

def reply_to_comment(comment_id, comment_text):
    try:
        reply = get_ai_reply(COMMENT_PROMPT, comment_text)
        if not reply:
            return
        reply = " ".join(reply.split()).replace('\n', ' ')
        if not reply.endswith(('।', '?', '!')): reply += '।'
        url = f"https://graph.facebook.com/v18.0/{comment_id}/comments"
        params = {"access_token": PAGE_ACCESS_TOKEN}
        data = {"message": reply}
        r = requests.post(url, params=params, json=data, timeout=10)
        logger.info(f"Comment reply status: {r.status_code} | {comment_text[:50]}")
    except Exception as e:
        logger.info(f"Comment reply error: {e}")

# ================= MESSENGER =================

def process_and_send(sender_id, text):
    if is_photo_request(text):
        send_message(sender_id, "একটু অপেক্ষা করো, পাঠাচ্ছি।")
        time.sleep(1)
        send_random_photo(sender_id)
        return

    history = user_histories.get(sender_id, [])
    reply = get_ai_reply(SYSTEM_PROMPT, text, history)

    if reply:
        reply = " ".join(reply.split()).replace('\n', ' ')
        if not reply.endswith(('।', '?', '!')): reply += '।'
        time.sleep(2)
        send_message(sender_id, reply)

        with history_lock:
            if sender_id not in user_histories: user_histories[sender_id] = []
            user_histories[sender_id].append({"role": "user", "parts": [{"text": text}]})
            user_histories[sender_id].append({"role": "model", "parts": [{"text": reply}]})
            if len(user_histories[sender_id]) > 20:
                user_histories[sender_id] = user_histories[sender_id][-20:]

def send_message(recipient_id, message_text):
    url = f"https://graph.facebook.com/v18.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
    data = {"recipient": {"id": recipient_id}, "message": {"text": message_text}, "messaging_type": "RESPONSE"}
    r = requests.post(url, json=data, timeout=10)
    logger.info(f"Send status: {r.status_code}")

# ================= ROUTES =================

@app.route("/webhook", methods=["GET"])
def verify():
    if request.args.get("hub.verify_token") == VERIFY_TOKEN:
        return request.args.get("hub.challenge")
    return "Failed", 403

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json
    if data.get("object") == "page":
        for entry in data.get("entry", []):

            # Messenger message
            for event in entry.get("messaging", []):
                if "message" in event and "text" in event["message"]:
                    sender_id = event["sender"]["id"]
                    user_text = event["message"]["text"]
                    threading.Thread(target=process_and_send, args=(sender_id, user_text)).start()

            # Page comment
            for change in entry.get("changes", []):
                value = change.get("value", {})
                if value.get("item") == "comment" and value.get("verb") == "add":
                    comment_id = value.get("comment_id") or value.get("id")
                    comment_text = value.get("message", "")
                    if comment_id and comment_text:
                        logger.info(f"New comment: {comment_text[:50]}")
                        threading.Thread(target=reply_to_comment, args=(comment_id, comment_text)).start()

    return "OK", 200

@app.route("/")
def index(): return "Maya is running!"

@app.route("/ping")
def ping(): return "PONG", 200

@app.route("/subscribe")
def subscribe():
    try:
        url = f"https://graph.facebook.com/v18.0/{PAGE_ID}/subscribed_apps"
        params = {
            "subscribed_fields": "feed,messages,messaging_postbacks",
            "access_token": PAGE_ACCESS_TOKEN
        }
        r = requests.post(url, params=params, timeout=10)
        data = r.json()
        if data.get("success"):
            logger.info("✅ Page successfully subscribed to feed!")
            return "✅ Page subscribed successfully!", 200
        else:
            logger.info(f"⚠️ Subscription response: {data}")
            return f"⚠️ Response: {data}", 200
    except Exception as e:
        return f"Error: {e}", 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=False)
