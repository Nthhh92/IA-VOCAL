from flask import Flask, request, Response, jsonify
from twilio.rest import Client
from dotenv import load_dotenv
import openai
import os
import json
from datetime import datetime

load_dotenv()

app = Flask(__name__)

twilio_client = Client(os.getenv("TWILIO_ACCOUNT_SID"), os.getenv("TWILIO_AUTH_TOKEN"))
openai_client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

RESTAURANT = os.getenv("RESTAURANT_NAME", "Casa Napoli")
MANAGER_WA = os.getenv("MANAGER_WHATSAPP")

def extraire_infos(transcription):
    response = openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": """Analyse cette transcription d'appel restaurant et extrais les informations.
Reponds UNIQUEMENT en JSON :
{
  "type": "reservation ou takeaway ou delivery",
  "nom": "nom du client",
  "telephone": "numero du client ou vide",
  "details": "description complete de la commande ou reservation",
  "total": "total en MAD ou vide"
}"""
            },
            {"role": "user", "content": f"Transcription:\n{transcription}"}
        ],
        response_format={"type": "json_object"}
    )
    return json.loads(response.choices[0].message.content)

@app.route("/whatsapp", methods=["POST"])
def whatsapp_webhook():
    data = request.json
    print(f"Webhook recu type: {data.get('type', 'unknown')}")

    # Extraire la transcription depuis le format ElevenLabs post-call
    transcription = ""
    
    # Le transcript est dans data['transcript'] pour ElevenLabs
    transcript_list = data.get("transcript", [])
    
    if not transcript_list:
        # Essaie dans data['data']['transcript']
        transcript_list = data.get("data", {}).get("transcript", [])
    
    if transcript_list and isinstance(transcript_list, list):
        lines = []
        for t in transcript_list:
            role = t.get("role", "")
            message = t.get("message", "")
            if message and message != "...":
                lines.append(f"{role}: {message}")
        transcription = "\n".join(lines)
    
    print(f"Transcription extraite ({len(transcription)} chars): {transcription[:200]}")

    if transcription and len(transcription) > 20:
        try:
            infos = extraire_infos(transcription)
            print(f"Infos extraites: {infos}")
        except Exception as e:
            print(f"Erreur extraction GPT: {e}")
            infos = {"type": "appel", "nom": "", "telephone": "", "details": transcription[:300], "total": ""}
    else:
        # Utiliser le résumé si pas de transcription
        summary = data.get("analysis", {}).get("transcript_summary", "")
        infos = {
            "type": data.get("type", "appel"),
            "nom": "",
            "telephone": "",
            "details": summary or "Voir transcription",
            "total": ""
        }

    msg = f"""🍕 *{RESTAURANT} — {infos.get('type', 'Appel').upper()}*

👤 Nom : {infos.get('nom', 'Non renseigne')}
📞 Tel : {infos.get('telephone', 'Non renseigne')}
📝 Details : {infos.get('details', 'Non renseigne')}
💰 Total : {infos.get('total', 'A confirmer')} MAD

⏰ Recu a {datetime.now().strftime('%H:%M')}"""

    try:
        twilio_client.messages.create(
            from_=os.getenv("TWILIO_WHATSAPP_FROM"),
            to=MANAGER_WA,
            body=msg
        )
        print("WhatsApp envoye avec succes!")
        return jsonify({"status": "ok"})
    except Exception as e:
        print(f"Erreur WhatsApp: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/", methods=["GET"])
def health():
    return jsonify({"status": "ok", "restaurant": RESTAURANT})

if __name__ == "__main__":
    app.run(debug=True, port=5000)
