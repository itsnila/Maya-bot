from flask import Flask, request, jsonify
import requests
import os
import google.generativeai as genai

app = Flask(__name__)

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
PAGE_ACCESS_TOKEN = os.environ.get("PAGE_ACCESS_TOKEN")
VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN")

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-1.5-flash")

@app.route("/webhook", methods=["GET"])
def verify():
    if request.args.get("hub.verify_token") == VERIFY_TOKEN:
        return request.args.get("hub.challenge")
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
                    try:
                        response = model.generate_content(
                            f"তুমি একজন বন্ধুসুলভ AI। বাংলায় উত্তর দাও। User বলেছে: {user_text}"
                        )
                        reply = response.text
                    except:
                        reply = "দুঃখিত, এখন উত্তর দিতে পারছি না।"
                    send_message(sender_id, reply)
    return jsonify({"status": "ok"})

def send_message(recipient_id, message_text):
    url = f"https://graph.facebook.com/v18.0/me/messages"
    params = {"access_token": PAGE_ACCESS_TOKEN}
    data = {
        "recipient": {"id": recipient_id},
        "message": {"text": message_text}
    }
    requests.post(url, params=params, json=data)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.g
