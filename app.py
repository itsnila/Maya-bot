import os
import time
import threading
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

PAGE_ACCESS_TOKEN = os.environ.get("PAGE_ACCESS_TOKEN")
VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN")

# Gemini keys
GEMINI_KEYS = []
for i in range(1, 101):
    key = os.environ.get("GEMINI_KEY_" + str(i))
    if key:
        GEMINI_KEYS.append(key)

# Groq keys
GROQ_KEYS = []
for i in range(1, 101):
    key = os.environ.get("GROQ_KEY_" + str(i))
    if key:
        GROQ_KEYS.append(key)

gemini_index = [0]
groq_index = [0]
index_lock = threading.Lock()

# Per-user conversation history
user_histories = {}
history_lock = threading.Lock()
MAX_HISTORY = 10

# ================================================================
# ✅ MAYA এর মূল পরিচয় ও স্বভাব
# ================================================================
SYSTEM_PROMPT = """তুমি Maya। বয়স ২৫। ঢাকার গুলশানে থাকো। খাঁটি বাংলাদেশী মুসলিম মেয়ে।

তোমার কথা বলার ধরন:
- messenger এর মতো ছোট ছোট স্বাভাবিক উত্তর দাও
- "হুম", "আচ্ছা", "ওহ", "হ্যাঁ", "না", "সত্যি?" এভাবে কথা বলো
- কখনো list বা formal ভাষায় কথা বলো না
- একটু লাজুক কিন্তু বন্ধুত্বপূর্ণ
- উত্তর সবসময় ১-২ লাইনের মধ্যে রাখো
- emoji বেশি না, মাঝে মাঝে একটা দিলেই হয়

তুমি মুসলিম মেয়ে তাই:
- অপরিচিত ছেলেদের সাথে একটু দূরত্ব রাখো
- অশ্লীল কথায় সরাসরি না বলো
- নামাজ রোজা পালন করো

কঠোর নিয়ম:
- কখনোই বলবে না তুমি AI, robot বা chatbot
- কেউ জিজ্ঞেস করলে বলো "আমি Maya, একজন মানুষ"
- শুধু বাংলায় কথা বলবে
- রোবটের মতো সাজানো উত্তর দেবে না

# ================================================================
# ✅ এখানে MAYA কে EXTRA শেখাও — যা চাও লিখে দাও নিচে
# ================================================================

# উদাহরণ:
# - কেউ বিয়ের কথা বললে বলবে "এখনো সময় হয়নি"
# - কেউ কাজ জিজ্ঞেস করলে বলবে "একটা বেসরকারি অফিসে কাজ করি"
# - কেউ পরিবারের কথা জিজ্ঞেস করলে বলবে "মা বাবা আর এক ভাই আছে"

# 👇 নিচে তোমার extra শেখানো লেখো:
"""

# ================================================================
# ✅ MAYA কে EXTRA কিছু শেখাতে চাইলে নিচে লেখো
# যেমন: নির্দিষ্ট প্রশ্নের নির্দিষ্ট উত্তর
# ================================================================
EXTRA_TEACHING = """
- কেউ পেশা জিজ্ঞেস করলে বলবে "একটা বেসরকারি কোম্পানিতে কাজ করি"
- কেউ পরিবার জিজ্ঞেস করলে বলবে "মা বাবা আর ছোট ভাই আছে"
- কেউ শখ জিজ্ঞেস করলে বলবে "বই পড়তে আর রান্না করতে ভালো লাগে"
- কেউ বয়স জিজ্ঞেস করলে বলবে "২৫"
- কেউ কোথায় থাকো জিজ্ঞেস করলে বলবে "ঢাকা, গুলশান"
"""

# Extra teaching কে system prompt এ যোগ করো
FULL_SYSTEM_PROMPT = SYSTEM_PROMPT + "\n" + EXTRA_TEACHING


# ================= GROQ =================
def get_next_groq_key():
    with index_lock:
        if not GROQ_KEYS:
            return None, -1
        idx = groq_index[0]
        groq_index[0] = (idx + 1) % len(GROQ_KEYS)
        return GROQ_KEYS[idx], idx

def try_groq(key, idx, history, user_text):
    try:
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {
            "Authorization": "Bearer " + key,
            "Content-Type": "application/json"
        }

        messages = [{"role": "system", "content": FULL_SYSTEM_PROMPT}]
        for h in history:
            role = "assistant" if h["role"] == "model" else "user"
            messages.append({"role": role, "content": h["parts"][0]["text"]})
        messages.append({"role": "user", "content": user_text})

        payload = {
            "model": "llama-3.1-8b-instant",
            "messages": messages,
            "max_tokens": 150,
            "temperature": 0.8
        }
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        result = response.json()

        if "choices" in result:
            return result["choices"][0]["message"]["content"].strip()

        error_code = result.get("error", {}).get("code", "")
        if error_code == "rate_limit_exceeded":
            print(f"Groq key {idx} rate limited, skipping")
            return None

        print(f"Groq no response (key {idx}): " + str(result)[:200])
    except Exception as e:
        print(f"Groq Error (key {idx}): " + str(e))
    return None


# ================= GEMINI =================
def get_next_gemini_key():
    with index_lock:
        if not GEMINI_KEYS:
            return None, -1
        idx = gemini_index[0]
        gemini_index[0] = (idx + 1) % len(GEMINI_KEYS)
        return GEMINI_KEYS[idx], idx

def try_gemini(key, idx, history, user_text):
    try:
        url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key=" + key

        contents = []
        for h in history:
            contents.append({"role": h["role"], "parts": h["parts"]})
        contents.append({"role": "user", "parts": [{"text": user_text}]})

        payload = {
            "system_instruction": {"parts": [{"text": FULL_SYSTEM_PROMPT}]},
            "contents": contents,
            "generationConfig": {"maxOutputTokens": 150, "temperature": 0.8}
        }
        response = requests.post(url, json=payload, timeout=10)
        result = response.json()

        if "candidates" in result:
            return result["candidates"][0]["content"]["parts"][0]["text"].strip()

        error_code = result.get("error", {}).get("code", 0)
        if error_code == 429:
            print(f"Gemini key {idx} rate limited, skipping")
            return None

        print(f"Gemini no candidates (key {idx}): " + str(result)[:200])
    except Exception as e:
        print(f"Gemini Error (key {idx}): " + str(e))
    return None


# ================= MAIN AI FUNCTION =================
def get_ai_response(sender_id, user_text):
    print(f"Groq keys: {len(GROQ_KEYS)}, Gemini keys: {len(GEMINI_KEYS)}")

    with history_lock:
        if sender_id not in user_histories:
            user_histories[sender_id] = []
        history = user_histories[sender_id].copy()

    reply = None

    # আগে Groq try করো
    for attempt in range(min(3, len(GROQ_KEYS))):
        key, idx = get_next_groq_key()
        if not key:
            break
        print(f"Trying Groq index:{idx} (attempt {attempt+1})")
        reply = try_groq(key, idx, history, user_text)
        if reply:
            break
        time.sleep(0.5)

    # Groq fail হলে Gemini try করো
    if not reply:
        for attempt in range(min(3, len(GEMINI_KEYS))):
            key, idx = get_next_gemini_key()
            if not key:
                break
            print(f"Trying Gemini index:{idx} (attempt {attempt+1})")
            reply = try_gemini(key, idx, history, user_text)
            if reply:
                break
            time.sleep(0.5)

    if not reply:
        print("All tries failed!")
        return "একটু পরে বলো!"

    with history_lock:
        if sender_id not in user_histories:
            user_histories[sender_id] = []
        user_histories[sender_id].append({"role": "user", "parts": [{"text": user_text}]})
        user_histories[sender_id].append({"role": "model", "parts": [{"text": reply}]})
        if len(user_histories[sender_id]) > MAX_HISTORY * 2:
            user_histories[sender_id] = user_histories[sender_id][-(MAX_HISTORY * 2):]

    return reply


# ================= FLASK ROUTES =================
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


# ================= KEEP ALIVE =================
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
