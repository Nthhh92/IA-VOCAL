from flask import Flask, request, Response, jsonify
from twilio.rest import Client
from twilio.twiml.messaging_response import MessagingResponse
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

# Memoire des conversations WhatsApp (par numero de telephone)
conversations = {}

SYSTEM_PROMPT = """Tu es Sofia, l'assistante de Casa Napoli, un restaurant italien au Maroc.
Tu reponds aux messages WhatsApp des clients de facon naturelle et concise.

MENU :
PIZZAS (Normale 35cm - 75 MAD / Grande 45cm - 95 MAD)
Margherita, 4 Fromages, Napolitaine, Reine, Vegetarienne, Poulet BBQ ⭐, Fruits de mer
Supplement : +15 MAD

PATES : Spaghetti bolognaise 65 MAD, Penne arrabiata 60 MAD, Lasagnes 75 MAD
SALADES : Cesar 45 MAD, Grecque 40 MAD
DESSERTS : Tiramisu 35 MAD ⭐, Moelleux chocolat 30 MAD, Panna cotta 30 MAD
BOISSONS : Coca/Fanta/Sprite 20 MAD, Eau 15 MAD, Jus orange frais 25 MAD

INFOS : Ouvert 12h-23h, Livraison jusqu'a 22h30, rayon 5km, 30-45min
Paiement : especes ou carte. Produits halal.

REGLES :
- Reponds toujours dans la langue du client (francais, darija, anglais)
- Messages courts et naturels — pas de listes longues
- Une question a la fois
- Pour reservation : collecter nom, date, heure, nombre de personnes
- Pour commande : collecter plats, tailles, adresse si livraison
- Toujours recapituler avant de confirmer
- Demander le numero si pas fourni
- Si demande speciale (anniversaire, allergie, etc.) : noter et rassurer

Quand la commande est complete et confirmee par le client, reponds avec ce format EXACT sur la derniere ligne :
CONFIRMED:{type}|{nom}|{telephone}|{details}|{total}

Exemple : CONFIRMED:reservation|Ahmed|0612345678|Table 4 personnes ce soir 20h|0"""

def get_conversation_history(phone):
    if phone not in conversations:
        conversations[phone] = []
    return conversations[phone]

def add_to_history(phone, role, content):
    if phone not in conversations:
        conversations[phone] = []
    conversations[phone].append({"role": role, "content": content})
    # Garde seulement les 20 derniers messages
    if len(conversations[phone]) > 20:
        conversations[phone] = conversations[phone][-20:]

def send_whatsapp_notification(infos, client_phone):
    labels = {"reservation": "Reservation", "takeaway": "A emporter", "delivery": "Livraison"}
    icons = {"reservation": "📅", "takeaway": "🥡", "delivery": "🛵"}
    intent = infos.get("type", "other")

    msg = f"""🍕 *{RESTAURANT} — {labels.get(intent, 'Commande')}* {icons.get(intent, '📱')}

📱 Via : WhatsApp
📞 Tel client : {client_phone}
👤 Nom : {infos.get('nom', 'Non renseigne')}
📝 Details : {infos.get('details', 'Non renseigne')}
💰 Total : {infos.get('total', 'A confirmer')} MAD

⏰ Recu a {datetime.now().strftime('%H:%M')}"""

    twilio_client.messages.create(
        from_=os.getenv("TWILIO_WHATSAPP_FROM"),
        to=MANAGER_WA,
        body=msg
    )
    print(f"Notification manager envoyee pour {client_phone}")

# ============================================================
# ROUTE MESSAGES WHATSAPP ENTRANTS
# ============================================================
@app.route("/whatsapp-incoming", methods=["POST"])
def whatsapp_incoming():
    incoming_msg = request.form.get("Body", "").strip()
    client_phone = request.form.get("From", "")
    
    print(f"Message recu de {client_phone}: {incoming_msg}")
    
    # Recupere l'historique de la conversation
    history = get_conversation_history(client_phone)
    
    # Ajoute le message du client
    add_to_history(client_phone, "user", incoming_msg)
    
    # Appel GPT
    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + history
    
    try:
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            max_tokens=500
        )
        
        assistant_reply = response.choices[0].message.content
        print(f"Reponse Sofia: {assistant_reply}")
        
        # Verifie si la commande est confirmee
        notification_sent = False
        clean_reply = assistant_reply
        
        if "CONFIRMED:" in assistant_reply:
            try:
                # Extrait les infos
                confirmed_line = [l for l in assistant_reply.split("\n") if l.startswith("CONFIRMED:")][0]
                parts = confirmed_line.replace("CONFIRMED:", "").split("|")
                
                infos = {
                    "type": parts[0] if len(parts) > 0 else "other",
                    "nom": parts[1] if len(parts) > 1 else "",
                    "telephone": parts[2] if len(parts) > 2 else client_phone,
                    "details": parts[3] if len(parts) > 3 else "",
                    "total": parts[4] if len(parts) > 4 else ""
                }
                
                send_whatsapp_notification(infos, client_phone)
                notification_sent = True
                
                # Nettoie la reponse (enleve la ligne CONFIRMED)
                clean_reply = "\n".join([l for l in assistant_reply.split("\n") if not l.startswith("CONFIRMED:")])
                
                # Remet a zero la conversation apres confirmation
                conversations[client_phone] = []
                
            except Exception as e:
                print(f"Erreur parsing CONFIRMED: {e}")
        
        # Ajoute la reponse a l'historique
        add_to_history(client_phone, "assistant", clean_reply)
        
        # Envoie la reponse au client
        resp = MessagingResponse()
        resp.message(clean_reply.strip())
        
        return Response(str(resp), mimetype="text/xml")
        
    except Exception as e:
        print(f"Erreur GPT: {e}")
        resp = MessagingResponse()
        resp.message("Désolée, une erreur s'est produite. Veuillez réessayer ou nous appeler directement.")
        return Response(str(resp), mimetype="text/xml")

# ============================================================
# ROUTE WEBHOOK POST-CALL ELEVENLABS
# ============================================================
@app.route("/whatsapp", methods=["POST"])
def whatsapp_webhook():
    data = request.json
    print(f"Webhook post-call recu")

    transcript_list = data.get("transcript", [])
    if not transcript_list:
        transcript_list = data.get("data", {}).get("transcript", [])

    transcription = ""
    if transcript_list and isinstance(transcript_list, list):
        lines = []
        for t in transcript_list:
            role = t.get("role", "")
            message = t.get("message", "")
            if message and message != "...":
                lines.append(f"{role}: {message}")
        transcription = "\n".join(lines)

    print(f"Transcription ({len(transcription)} chars)")

    if transcription and len(transcription) > 20:
        try:
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
  "details": "description complete",
  "total": "total en MAD ou vide"
}"""
                    },
                    {"role": "user", "content": f"Transcription:\n{transcription}"}
                ],
                response_format={"type": "json_object"}
            )
            infos = json.loads(response.choices[0].message.content)
        except Exception as e:
            print(f"Erreur extraction: {e}")
            infos = {"type": "appel", "nom": "", "telephone": "", "details": transcription[:300], "total": ""}
    else:
        summary = data.get("analysis", {}).get("transcript_summary", "")
        infos = {"type": "appel", "nom": "", "telephone": "", "details": summary, "total": ""}

    caller = data.get("data", {}).get("metadata", {}).get("phone_call", {}).get("external_number", "Inconnu")

    msg = f"""🍕 *{RESTAURANT} — {infos.get('type', 'Appel').upper()}* 📞

📞 Via : Appel vocal
👤 Nom : {infos.get('nom', 'Non renseigne')}
📱 Tel : {infos.get('telephone', caller)}
📝 Details : {infos.get('details', 'Non renseigne')}
💰 Total : {infos.get('total', 'A confirmer')} MAD

⏰ Recu a {datetime.now().strftime('%H:%M')}"""

    try:
        twilio_client.messages.create(
            from_=os.getenv("TWILIO_WHATSAPP_FROM"),
            to=MANAGER_WA,
            body=msg
        )
        print("WhatsApp manager envoye!")
        return jsonify({"status": "ok"})
    except Exception as e:
        print(f"Erreur WhatsApp: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/", methods=["GET"])
def health():
    return jsonify({"status": "ok", "restaurant": RESTAURANT})

if __name__ == "__main__":
    app.run(debug=True, port=5000)
