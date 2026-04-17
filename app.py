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
    """Extrait les infos de la commande depuis la transcription"""
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
    print(f"Webhook recu: {json.dumps(data, indent=2)}")

    # Extraire la transcription selon le format ElevenLabs
    transcription = ""
    
    # Format post-call webhook ElevenLabs
    if "transcript" in data:
        transcript = data["transcript"]
        if isinstance(transcript, list):
            transcription = "\n".join([
                f"{t.get('role', '')}: {t.get('message', '')}" 
                for t in transcript
            ])
        else:
            transcription = str(transcript)
    elif "transcription" in data:
        transcription = data["transcription"]
    
    print(f"Transcription: {transcription}")

    # Si on a une transcription, extraire les infos avec GPT
    if transcription and len(transcription) > 20:
        try:
            infos = extraire_infos(transcription)
            print(f"Infos extraites: {infos}")
        except Exception as e:
            print(f"Erreur extraction: {e}")
            infos = {
                "type": data.get("type", "appel"),
                "nom": data.get("nom", ""),
                "telephone": data.get("telephone", ""),
                "details": transcription[:500],
                "total": data.get("total", "")
            }
    else:
        # Utiliser les données directes si pas de transcription
        infos = {
            "type": data.get("type", "appel"),
            "nom": data.get("nom", ""),
            "telephone": data.get("telephone", ""),
            "details": data.get("details", ""),
            "total": data.get("total", "")
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
        print("WhatsApp envoye avec succes !")
        return jsonify({"status": "ok"})
    except Exception as e:
        print(f"Erreur WhatsApp: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/", methods=["GET"])
def health():
    return jsonify({"status": "ok", "restaurant": RESTAURANT})

if __name__ == "__main__":
    app.run(debug=True, port=5000)
