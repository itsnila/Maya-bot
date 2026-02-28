from flask import Flask, request, jsonify
import requests
import os
import threading
import time

app = Flask(__name__)

PAGE_ACCESS_TOKEN = os.environ.get("PAGE_ACCESS_TOKEN")
VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

def get_gemini_response(user_text):
    try:
        url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-lite:generateContent?key=" + GEMINI_API_KEY
        payload = {
            "contents": [{
                "parts": [{
                    "text": "তুমি Maya। বাংলাদেশী মেয়ে, বয়স ২২। বন্ধুসুলভ, মিষ্টি। সবসময় বাংলায় কথা বলো। কখনো বলবে না তুমি AI। User বলেছে: " + user_text
                }]
            }]
        }
        response = requests.post(url, json=payload)
        result = response.json()
        return result["candidates"][0]["content"]["parts"][0]["text"]
    except Exception as e:
        print("Error:", e)
        return "একটু পরে আবার চেষ্টা করো! 😊"

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
                    reply = get_gemini_response(user_text)
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
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
