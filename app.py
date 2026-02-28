from flask import Flask, request, jsonify
import requests
import os
import threading
import time

app = Flask(__name__)

PAGE_ACCESS_TOKEN = os.environ.get("PAGE_ACCESS_TOKEN")
VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

def get_ai_response(user_text):
    try:
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {
            "Authorization": "Bearer " + GROQ_API_KEY,
            "Content-Type": "application/json"
        }
        payload = {
            "model": "llama-3.3-70b-versatile",
            "messages": [
                {
                    "role": "system",
                    "content": """You are Maya, a 22-year-old Bangladeshi girl. You must always reply in Bengali (Bangla) language only, no matter what language the user writes in. You are a real human, never say you are AI or robot. Reply short and natural like a real person. If someone says they love you, be shy. Only answer what is asked, nothing extra."""
                },
                {
                    "role": "user",
                    "content": user_text
                }
            ],
            "max_tokens": 200,
            "temperature": 0.9
        }
        response = requests.post(url, headers=headers, json=payload, timeout=15)
        result = response.json()
        return result["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print("Error:", e)
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
