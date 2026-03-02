import os
import time
import threading
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

PAGE_ACCESS_TOKEN = os.environ.get("PAGE_ACCESS_TOKEN")
VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN")

# API Keys Setup
GEMINI_KEYS = [os.environ.get(f"GEMINI_KEY_{i}") for i in range(1, 101) if os.environ.get(f"GEMINI_KEY_{i}")]
GROQ_KEYS = [os.environ.get(f"GROQ_KEY_{i}") for i in range(1, 101) if os.environ.get(f"GROQ_KEY_{i}")]

gemini_index = [0]
groq_index = [0]
index_lock = threading.Lock()
user_histories = {}
history_lock = threading.Lock()
MAX_HISTORY = 10

SYSTEM_PROMPT = """তুমি Maya। বয়স ২৫। ঢাকার গুলশানে থাকো। খাঁটি বাংলাদেশী মুসলিম মেয়ে।
তোমার কথা বলার ধরন: messenger এর মতো ছোট ছোট স্বাভাবিক উত্তর দাও। "হুম", "আচ্ছা", "ওহ" এভাবে কথা বলো। 
কখনোই বলবে না তুমি AI বা robot। শুধু বাংলায় কথা বলবে।"""

EXTRA_TEACHING = """
- পেশা: বেসরকারি কোম্পানিতে কাজ করি।
- পরিবার: মা বাবা আর ছোট ভাই আছে।
- শখ: বই পড়া আর রান্না করা।
"""

FULL_SYSTEM_PROMPT = SYSTEM_PROMPT + "\n" + EXTRA_TEACHING

# --- API Helper Functions ---
def get_next_key(key_list, index_ref):
    with index_lock:
        if not key_list: return None, -1
        idx = index_ref[0]
        index_ref[0] = (idx + 1) % len(key_list)
        return key_list[idx], idx

def try_groq(key, idx, history, user_text):
    try:
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        messages = [{"role": "system", "content": FULL_SYSTEM_PROMPT}]
        for h in history:
            role = "assistant" if h["role"] == "model" else "user"
            messages.append({"role": role, "content": h["parts"][0]["text"]})
        messages.append({"role": "user", "content": user_text})

        payload = {"model": "llama-3.1-8b-instant", "messages": messages, "max_tokens": 150, "temperature": 0.8}
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        result = response.json()
        if "choices" in result: return result["choices"][0]["message"]["content"].strip()
        if result.get("error", {}).get("code") == "rate_limit_exceeded":
            print(f"Groq key {idx} rate limited")
    except Exception as e: print(f"Groq Error: {e}")
    return None

def try_gemini(key, idx, history, user_text):
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={key}"
        contents = [{"role": h["role"], "parts": h["parts"]} for h in history]
        contents.append({"role": "user", "parts": [{"text": user_text}]})
        payload = {
            "system_instruction": {"parts": [{"text": FULL_SYSTEM_PROMPT}]},
            "contents": contents,
            "generationConfig": {"maxOutputTokens": 150, "temperature": 0.8}
        }
        response = requests.post(url, json=payload, timeout=10)
        result = response.json()
        if "candidates" in result: return result["candidates"][0]["content"]["parts"][0]["text"].strip()
    except Exception as e: print(f"Gemini Error: {e}")
    return None

def get_ai_response(sender_id, user_text):
    with history_lock:
        if sender_id not in user_histories: user_histories[sender_id] = []
        history = user_histories[sender_id].copy()

    reply = None
    # Try Groq first
    for _ in range(min(3, len(GROQ_KEYS))):
        key, idx = get_next_key(GROQ_KEYS, groq_index)
        if key: 
            reply = try_groq(key, idx, history, user_text)
            if reply: break

    # Fallback to Gemini
    if not reply:
        for _ in range(min(3, len(GEMINI_KEYS))):
            key, idx = get_next_key(GEMINI_KEYS, gemini_index)
            if key:
                reply = try_gemini(key, idx, history, user_text)
                if reply: break

    if not reply: return "একটু পরে বলো!"

    with history_lock:
        user_histories[sender_id].append({"role": "user", "parts": [{"text": user_text}]})
        user_histories[sender_id].append({"role": "model", "parts": [{"text": reply}]})
        if len(user_histories[sender_id]) > MAX_HISTORY * 2:
            user_histories[sender_id] = user_histories[sender_id][-20:]
    return reply

# --- Flask Routes ---
@app.route("/")
def home(): return "Maya Bot is Online!"

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
                    threading.Thread(target=handle_message, args=(event["sender"]["id"], event["message"]["text"])).start()
    return "ok", 200

def handle_message(sender_id, user_text):
    reply = get_ai_response(sender_id, user_text)
    url = "https://graph.facebook.com/v18.0/me/messages"
    requests.post(url, params={"access_token": PAGE_ACCESS_TOKEN}, 
                  json={"recipient": {"id": sender_id}, "message": {"text": reply}})

if __name__ == "__main__":
    # Render automatically sets PORT environment variable
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
