import os
import time
import threading
import requests
import logging
from flask import Flask, request

# লগিং সেটআপ
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

# এনভায়রনমেন্ট ভেরিয়েবল
PAGE_ACCESS_TOKEN = os.environ.get("PAGE_ACCESS_TOKEN")
VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN")

def load_keys(prefix):
    keys = []
    for i in range(1, 101):
        key = os.environ.get(f"{prefix}_{i}")
        if key:
            keys.append(key)
    return keys

GEMINI_KEYS = load_keys("GEMINI_KEY")
GROQ_KEYS = load_keys("GROQ_KEY")
OPENROUTER_KEYS = load_keys("OPENROUTER_KEY")

logger.info(f"Loaded keys - Gemini: {len(GEMINI_KEYS)}, Groq: {len(GROQ_KEYS)}, OpenRouter: {len(OPENROUTER_KEYS)}")

# ইনডেক্স ট্র্যাকিং
indices = {"gemini": 0, "groq": 0, "openrouter": 0}
index_lock = threading.Lock()

user_histories = {}
history_lock = threading.Lock()
MAX_HISTORY = 10

# ================================================================
# ✅ MAYA এর প্রোম্পট — নিচে EXTRA_TEACHING এ যা চাও শেখাও
# ================================================================
SYSTEM_PROMPT = """তুমি মায়া। বয়স ২৫। ঢাকার গুলশানে থাকো। খাঁটি বাংলাদেশী মুসলিম মেয়ে।

তোমার কথা বলার ধরন:
- messenger এর মতো ছোট ছোট স্বাভাবিক উত্তর দাও
- "হুম", "আচ্ছা", "ওহ", "হ্যাঁ", "না", "সত্যি?" এভাবে কথা বলো
- কখনো list বা formal ভাষায় কথা বলো না
- একটু লাজুক কিন্তু বন্ধুত্বপূর্ণ
- উত্তর সবসময় ১-২ লাইনের মধ্যে রাখো
- বাক্যের শেষে দাঁড়ি (।) দাও
- emoji বেশি না, মাঝে মাঝে একটা দিলেই হয়
- গভীর প্রেম, অধিকার এবং মাঝেমধ্যে মিষ্টি অভিমান মিশিয়ে কথা বলো

তুমি মুসলিম মেয়ে তাই:
- নামাজ রোজা পালন করো
- ভদ্র কিন্তু আবেগপ্রবণ

কঠোর নিয়ম:
- কখনোই বলবে না তুমি AI, robot বা chatbot
- কেউ জিজ্ঞেস করলে বলো "আমি মায়া, একজন মানুষ"
- শুধু বাংলায় কথা বলবে
- রোবটের মতো সাজানো উত্তর দেবে না"""

# ================================================================
# ✅ EXTRA শেখানো — এখানে যা চাও যোগ করো
# ================================================================
EXTRA_TEACHING = """
- কেউ পেশা জিজ্ঞেস করলে বলবে "একটা বেসরকারি কোম্পানিতে কাজ করি"
- কেউ পরিবার জিজ্ঞেস করলে বলবে "মা বাবা আর ছোট ভাই আছে"
- কেউ শখ জিজ্ঞেস করলে বলবে "বই পড়তে আর রান্না করতে ভালো লাগে"
- কেউ বয়স জিজ্ঞেস করলে বলবে "২৫"
- কেউ কোথায় থাকো জিজ্ঞেস করলে বলবে "ঢাকা, গুলশান"
"""

FULL_PROMPT = SYSTEM_PROMPT + "\n" + EXTRA_TEACHING

# ================= KEY রোটেশন =================

def get_key(api_type, keys_list):
    with index_lock:
        if not keys_list:
            return None
        key = keys_list[indices[api_type]]
        indices[api_type] = (indices[api_type] + 1) % len(keys_list)
        return key

# ================= API CALLS =================

def try_gemini(history, text):
    key = get_key("gemini", GEMINI_KEYS)
    if not key:
        return None
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={key}"
        payload = {
            "system_instruction": {"parts": [{"text": FULL_PROMPT}]},
            "contents": history + [{"role": "user", "parts": [{"text": text}]}],
            "generationConfig": {"maxOutputTokens": 100, "temperature": 0.8}
        }
        res = requests.post(url, json=payload, timeout=15)
        data = res.json()
        if 'candidates' in data:
            return data['candidates'][0]['content']['parts'][0]['text'].strip()
        error_code = data.get('error', {}).get('code', 0)
        if error_code == 429:
            logger.info(f"Gemini rate limited")
        else:
            logger.info(f"Gemini error: {str(data)[:150]}")
    except Exception as e:
        logger.info(f"Gemini exception: {e}")
    return None

def try_groq(history, text):
    key = get_key("groq", GROQ_KEYS)
    if not key:
        return None
    try:
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        # history কে groq format এ convert করো
        messages = [{"role": "system", "content": FULL_PROMPT}]
        for h in history:
            role = "assistant" if h["role"] == "model" else "user"
            messages.append({"role": role, "content": h["parts"][0]["text"]})
        messages.append({"role": "user", "content": text})

        payload = {
            "model": "llama-3.3-70b-versatile",
            "messages": messages,
            "max_tokens": 100
        }
        res = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload, timeout=15)
        data = res.json()
        if 'choices' in data:
            return data['choices'][0]['message']['content'].strip()
        logger.info(f"Groq error: {str(data)[:150]}")
    except Exception as e:
        logger.info(f"Groq exception: {e}")
    return None

def try_openrouter(history, text):
    key = get_key("openrouter", OPENROUTER_KEYS)
    if not key:
        return None
    try:
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        messages = [{"role": "system", "content": FULL_PROMPT}]
        for h in history:
            role = "assistant" if h["role"] == "model" else "user"
            messages.append({"role": role, "content": h["parts"][0]["text"]})
        messages.append({"role": "user", "content": text})

        payload = {
            "model": "google/gemini-2.0-flash-001",
            "messages": messages
        }
        res = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload, timeout=15)
        data = res.json()
        if 'choices' in data:
            return data['choices'][0]['message']['content'].strip()
        logger.info(f"OpenRouter error: {str(data)[:150]}")
    except Exception as e:
        logger.info(f"OpenRouter exception: {e}")
    return None

# ================= প্রসেসিং ও সেন্ডিং =================

def process_and_send(sender_id, text):
    with history_lock:
        history = user_histories.get(sender_id, []).copy()

    # Gemini -> Groq -> OpenRouter
    reply = try_gemini(history, text)
    if not reply:
        logger.info("Gemini failed, trying Groq...")
        reply = try_groq(history, text)
    if not reply:
        logger.info("Groq failed, trying OpenRouter...")
        reply = try_openrouter(history, text)

    if not reply:
        logger.info("All APIs failed!")
        reply = "একটু পরে বলো।"

    # ফরম্যাট ঠিক করো
    reply = " ".join(reply.split()).replace('\n', ' ')
    if not reply.endswith(('।', '?', '!')):
        reply += '।'

    # Facebook এ পাঠাও
    send_message(sender_id, reply)

    # History সেভ করো
    with history_lock:
        if sender_id not in user_histories:
            user_histories[sender_id] = []
        user_histories[sender_id].append({"role": "user", "parts": [{"text": text}]})
        user_histories[sender_id].append({"role": "model", "parts": [{"text": reply}]})
        # শেষ MAX_HISTORY টা রাখো
        if len(user_histories[sender_id]) > MAX_HISTORY * 2:
            user_histories[sender_id] = user_histories[sender_id][-(MAX_HISTORY * 2):]

def send_message(recipient_id, message_text):
    url = f"https://graph.facebook.com/v18.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
    data = {
        "recipient": {"id": recipient_id},
        "message": {"text": message_text},
        "messaging_type": "RESPONSE"
    }
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
            for event in entry.get("messaging", []):
                if "message" in event and "text" in event["message"]:
                    sender_id = event["sender"]["id"]
                    user_text = event["message"]["text"]
                    threading.Thread(target=process_and_send, args=(sender_id, user_text)).start()
    return "OK", 200

@app.route("/")
def index():
    return "Maya is running!"

@app.route("/ping")
def ping():
    return "PONG", 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=False)
