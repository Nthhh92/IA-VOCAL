from flask import Flask, request, Response, jsonify
from twilio.twiml.voice_response import VoiceResponse, Gather
from twilio.rest import Client
from dotenv import load_dotenv
import os
import json
from datetime import datetime

load_dotenv()

app = Flask(__name__)

twilio_client = Client(os.getenv("TWILIO_ACCOUNT_SID"), os.getenv("TWILIO_AUTH_TOKEN"))

RESTAURANT = os.getenv("RESTAURANT_NAME", "Casa Napoli")
MANAGER_WA = os.getenv("MANAGER_WHATSAPP")

# ============================================================
# ROUTE WEBHOOK ELEVENLABS → WHATSAPP
# ============================================================
@app.route("/whatsapp", methods=["POST"])
def whatsapp_webhook():
    data = request.json
    print(f"Webhook recu: {data}")

    msg = f"""🍕 *{RESTAURANT} — Nouvelle commande*

📋 Type : {data.get('type', '')}
👤 Nom : {data.get('nom', '')}
📞 Tel : {data.get('telephone', '')}
📝 Details : {data.get('details', '')}
💰 Total : {data.get('total', '')} MAD

⏰ Recu a {datetime.now().strftime('%H:%M')}"""

    try:
        twilio_client.messages.create(
            from_=os.getenv("TWILIO_WHATSAPP_FROM"),
            to=MANAGER_WA,
            body=msg
        )
        print("WhatsApp envoye avec succes !")
        return jsonify({"status": "ok", "message": "WhatsApp envoye"})
    except Exception as e:
        print(f"Erreur WhatsApp: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

# ============================================================
# HEALTH CHECK
# ============================================================
@app.route("/", methods=["GET"])
def health():
    return jsonify({"status": "ok", "restaurant": RESTAURANT})

if __name__ == "__main__":
    app.run(debug=True, port=5000)
