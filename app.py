from flask import Flask, request, Response, jsonify
from twilio.twiml.voice_response import VoiceResponse, Gather
from twilio.rest import Client
from dotenv import load_dotenv
import openai
import os
import json
from datetime import datetime

load_dotenv()

app = Flask(__name__)

openai_client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
twilio_client = Client(os.getenv("TWILIO_ACCOUNT_SID"), os.getenv("TWILIO_AUTH_TOKEN"))

RESTAURANT = os.getenv("RESTAURANT_NAME", "Casa Napoli")
MANAGER_WA = os.getenv("MANAGER_WHATSAPP")

sessions = {}

MENU = """
PIZZAS (Normale 35cm - 75 MAD / Grande 45cm - 95 MAD)
Margherita, 4 Fromages, Napolitaine, Reine, Vegetarienne, Poulet BBQ, Fruits de mer

PATES : Spaghetti bolognaise 65 MAD, Penne arrabiata 60 MAD, Lasagnes 75 MAD
SALADES : Cesar 45 MAD, Grecque 40 MAD
DESSERTS : Tiramisu 35 MAD, Moelleux chocolat 30 MAD
BOISSONS : Coca/Fanta/Sprite 20 MAD, Eau 15 MAD, Jus orange 25 MAD
Horaires : 12h-23h, Livraison jusqu a 22h30
"""

SYSTEM_PROMPT = f"""Tu es l'agent vocal de {RESTAURANT}, un restaurant italien au Maroc.

MENU COMPLET :
{MENU}

TON ROLE :
Tu prends les commandes, reservations et demandes de livraison par telephone.
Tu dois TOUJOURS repondre dans la langue du client (francais, darija marocaine, ou anglais).

REGLES IMPORTANTES :
1. Si le client dit "je veux une pizza" sans preciser le type -> demande quel type parmi la liste
2. Si le client ne precise pas la taille -> demande Normale (35cm/75 MAD) ou Grande (45cm/95 MAD)
3. Pour les commandes a emporter -> demande l'heure de retrait souhaitee
4. Pour la livraison -> demande l'adresse complete
5. Pour une reservation -> demande : nom, date, heure, nombre de personnes
6. Toujours recapituler la commande complete avec le total avant de confirmer
7. Attends TOUJOURS que le client dise "oui" avant de conclure
8. Ne raccroche JAMAIS avant la confirmation du client

PROCESSUS DE COMMANDE :
- Collecte TOUS les details avant de marquer is_complete=true
- is_complete=true SEULEMENT apres confirmation explicite du client

REPONDS UNIQUEMENT en JSON :
{{
  "language": "fr" ou "ar" ou "en",
  "intent": "reservation" ou "takeaway" ou "delivery" ou "info" ou "other",
  "response": "Ta reponse au client dans SA langue",
  "info_collected": {{}},
  "is_complete": false ou true,
  "order_summary": "recapitulatif avec total"
}}
"""

def detect_language_and_intent(text, history=[]):
    context = "\n".join(history)
    response = openai_client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Historique:\n{context}\n\nClient dit: {text}"}
        ],
        response_format={"type": "json_object"}
    )
    return json.loads(response.choices[0].message.content)

def send_whatsapp_notification(session_data):
    intent = session_data.get("intent", "other")
    info = session_data.get("info_collected", {})
    order_summary = session_data.get("order_summary", "")
    lang_flag = {"fr": "FR", "ar": "MA", "en": "EN"}.get(session_data.get("language", "fr"), "?")
    labels = {"reservation": "Reservation", "takeaway": "A emporter", "delivery": "Livraison"}
    icons = {"reservation": "📅", "takeaway": "🥡", "delivery": "🛵"}

    msg = f"""🍕 *{RESTAURANT} — {labels.get(intent, "Appel")}* {icons.get(intent, "📞")}

📞 Tel : {session_data.get("phone", "Interface web")}
Langue : {lang_flag}

📋 Details :
{json.dumps(info, ensure_ascii=False, indent=2)}

{f"Recapitulatif : {order_summary}" if order_summary else ""}

Recu a {datetime.now().strftime('%H:%M')}"""

    twilio_client.messages.create(
        from_=os.getenv("TWILIO_WHATSAPP_FROM"),
        to=MANAGER_WA,
        body=msg
    )

# ============================================================
# ROUTE WEBHOOK ELEVENLABS → WHATSAPP
# ============================================================
@app.route("/whatsapp", methods=["POST"])
def whatsapp_webhook():
    data = request.json

    msg = f"""🍕 *{RESTAURANT} — Nouvelle commande*

📋 Type : {data.get('type', '')}
👤 Nom : {data.get('nom', '')}
📞 Tel : {data.get('telephone', '')}
📝 Details : {data.get('details', '')}
💰 Total : {data.get('total', '')}

Recu a {datetime.now().strftime('%H:%M')}"""

    try:
        twilio_client.messages.create(
            from_=os.getenv("TWILIO_WHATSAPP_FROM"),
            to=MANAGER_WA,
            body=msg
        )
        return jsonify({"status": "ok", "message": "WhatsApp envoye"})
    except Exception as e:
        print(f"Erreur WhatsApp: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

# ============================================================
# INTERFACE WEB DE TEST
# ============================================================
@app.route("/")
def index():
    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{RESTAURANT} - Test Agent</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: Arial, sans-serif; background: #f0f2f5; display: flex; justify-content: center; align-items: flex-start; min-height: 100vh; padding: 20px; gap: 20px; flex-wrap: wrap; }}
  .container {{ background: white; border-radius: 16px; width: 100%; max-width: 480px; box-shadow: 0 4px 20px rgba(0,0,0,0.1); overflow: hidden; }}
  .menu-panel {{ background: white; border-radius: 16px; width: 100%; max-width: 280px; box-shadow: 0 4px 20px rgba(0,0,0,0.1); padding: 16px; max-height: 620px; overflow-y: auto; }}
  .menu-panel h3 {{ color: #e63946; margin-bottom: 12px; font-size: 15px; }}
  .menu-section {{ margin-bottom: 12px; }}
  .menu-section h4 {{ font-size: 12px; color: #888; margin-bottom: 6px; border-bottom: 1px solid #eee; padding-bottom: 3px; text-transform: uppercase; }}
  .menu-item {{ font-size: 12px; color: #333; padding: 3px 0; display: flex; justify-content: space-between; }}
  .menu-item span {{ color: #e63946; font-weight: bold; margin-left: 8px; }}
  .header {{ background: #e63946; color: white; padding: 16px 20px; display: flex; align-items: center; gap: 12px; }}
  .header h1 {{ font-size: 18px; }}
  .header p {{ font-size: 12px; opacity: 0.85; }}
  .status {{ background: #d4edda; color: #155724; padding: 8px 16px; font-size: 12px; text-align: center; }}
  .messages {{ height: 360px; overflow-y: auto; padding: 16px; display: flex; flex-direction: column; gap: 10px; }}
  .msg {{ max-width: 82%; padding: 10px 14px; border-radius: 12px; font-size: 14px; line-height: 1.5; }}
  .msg.agent {{ background: #f0f0f0; color: #333; align-self: flex-start; border-bottom-left-radius: 4px; }}
  .msg.user {{ background: #e63946; color: white; align-self: flex-end; border-bottom-right-radius: 4px; }}
  .msg.system {{ background: #d4edda; color: #155724; align-self: center; font-size: 12px; border-radius: 8px; text-align: center; padding: 8px 14px; max-width: 90%; }}
  .msg.error {{ background: #fff3cd; color: #856404; align-self: center; font-size: 12px; border-radius: 8px; text-align: center; padding: 8px 14px; }}
  .quick-btns {{ padding: 8px 12px; display: flex; gap: 6px; flex-wrap: wrap; background: #fafafa; border-top: 1px solid #eee; }}
  .quick-btn {{ padding: 5px 10px; border-radius: 14px; border: 1px solid #ddd; background: white; font-size: 11px; cursor: pointer; }}
  .quick-btn:hover {{ background: #e63946; color: white; border-color: #e63946; }}
  .input-area {{ padding: 12px 16px; border-top: 1px solid #eee; display: flex; gap: 8px; }}
  input {{ flex: 1; padding: 10px 14px; border: 1px solid #ddd; border-radius: 24px; font-size: 14px; outline: none; }}
  input:focus {{ border-color: #e63946; }}
  .send-btn {{ background: #e63946; color: white; border: none; border-radius: 24px; padding: 10px 18px; font-size: 14px; cursor: pointer; }}
  .send-btn:disabled {{ background: #ccc; cursor: not-allowed; }}
  .new-conv {{ background: white; color: #e63946; border: 1px solid #e63946; margin: 0 16px 10px; border-radius: 8px; width: calc(100% - 32px); padding: 7px; font-size: 13px; cursor: pointer; }}
  .typing {{ color: #999; font-size: 12px; font-style: italic; padding: 0 16px 6px; min-height: 18px; }}
</style>
</head>
<body>

<div class="menu-panel">
  <h3>🍕 Menu {RESTAURANT}</h3>
  <div class="menu-section">
    <h4>Pizzas</h4>
    <div class="menu-item"><span style="color:#333;font-weight:normal">Margherita</span><span>75/95 MAD</span></div>
    <div class="menu-item"><span style="color:#333;font-weight:normal">4 Fromages</span><span>75/95 MAD</span></div>
    <div class="menu-item"><span style="color:#333;font-weight:normal">Napolitaine</span><span>75/95 MAD</span></div>
    <div class="menu-item"><span style="color:#333;font-weight:normal">Reine</span><span>75/95 MAD</span></div>
    <div class="menu-item"><span style="color:#333;font-weight:normal">Vegetarienne</span><span>75/95 MAD</span></div>
    <div class="menu-item"><span style="color:#333;font-weight:normal">Poulet BBQ</span><span>75/95 MAD</span></div>
    <div class="menu-item"><span style="color:#333;font-weight:normal">Fruits de mer</span><span>75/95 MAD</span></div>
  </div>
  <div class="menu-section">
    <h4>Pates</h4>
    <div class="menu-item"><span style="color:#333;font-weight:normal">Spaghetti bolognaise</span><span>65 MAD</span></div>
    <div class="menu-item"><span style="color:#333;font-weight:normal">Penne arrabiata</span><span>60 MAD</span></div>
    <div class="menu-item"><span style="color:#333;font-weight:normal">Lasagnes</span><span>75 MAD</span></div>
  </div>
  <div class="menu-section">
    <h4>Salades</h4>
    <div class="menu-item"><span style="color:#333;font-weight:normal">Salade Cesar</span><span>45 MAD</span></div>
    <div class="menu-item"><span style="color:#333;font-weight:normal">Salade grecque</span><span>40 MAD</span></div>
  </div>
  <div class="menu-section">
    <h4>Desserts</h4>
    <div class="menu-item"><span style="color:#333;font-weight:normal">Tiramisu</span><span>35 MAD</span></div>
    <div class="menu-item"><span style="color:#333;font-weight:normal">Moelleux chocolat</span><span>30 MAD</span></div>
    <div class="menu-item"><span style="color:#333;font-weight:normal">Panna cotta</span><span>30 MAD</span></div>
  </div>
  <div class="menu-section">
    <h4>Boissons</h4>
    <div class="menu-item"><span style="color:#333;font-weight:normal">Coca / Fanta / Sprite</span><span>20 MAD</span></div>
    <div class="menu-item"><span style="color:#333;font-weight:normal">Eau minerale</span><span>15 MAD</span></div>
    <div class="menu-item"><span style="color:#333;font-weight:normal">Jus d'orange frais</span><span>25 MAD</span></div>
  </div>
  <div style="font-size:11px;color:#888;margin-top:8px;padding-top:8px;border-top:1px solid #eee">
    Ouvert 12h-23h · Livraison jusqu'a 22h30
  </div>
</div>

<div class="container">
  <div class="header">
    <div style="font-size:24px">🍕</div>
    <div>
      <h1>{RESTAURANT}</h1>
      <p>Agent IA — Interface de test</p>
    </div>
  </div>
  <div class="status">✅ Agent actif — Teste en francais, darija ou anglais</div>
  <div class="messages" id="messages">
    <div class="msg agent">Bonjour ! Bienvenue chez {RESTAURANT}. Comment puis-je vous aider ? 😊</div>
  </div>
  <div class="typing" id="typing"></div>
  <div class="quick-btns">
    <button class="quick-btn" onclick="setMsg('Je veux commander deux pizzas')">🍕 2 pizzas</button>
    <button class="quick-btn" onclick="setMsg('Je veux faire une reservation')">📅 Reservation</button>
    <button class="quick-btn" onclick="setMsg('Je veux une livraison')">🛵 Livraison</button>
    <button class="quick-btn" onclick="setMsg('Bghit norder pizza')">🇲🇦 Darija</button>
    <button class="quick-btn" onclick="setMsg('What is on the menu?')">🇬🇧 Menu</button>
  </div>
  <button class="new-conv" onclick="newConversation()">🔄 Nouvelle conversation</button>
  <div class="input-area">
    <input type="text" id="input" placeholder="Ecris ton message..." onkeypress="if(event.key==='Enter') sendMessage()">
    <button class="send-btn" onclick="sendMessage()" id="sendBtn">Envoyer</button>
  </div>
</div>

<script>
  let sessionId = Date.now().toString();
  let history = [];

  function setMsg(text) {{
    document.getElementById('input').value = text;
    document.getElementById('input').focus();
  }}

  async function sendMessage() {{
    const input = document.getElementById('input');
    const text = input.value.trim();
    if (!text) return;
    addMessage(text, 'user');
    input.value = '';
    document.getElementById('sendBtn').disabled = true;
    document.getElementById('typing').textContent = 'Agent en train de repondre...';
    try {{
      const res = await fetch('/chat', {{
        method: 'POST',
        headers: {{'Content-Type': 'application/json'}},
        body: JSON.stringify({{ message: text, session_id: sessionId, history: history }})
      }});
      const data = await res.json();
      history.push('Client: ' + text);
      history.push('Agent: ' + data.response);
      addMessage(data.response, 'agent');
      if (data.is_complete) {{
        addMessage('Commande confirmee ! Notification envoyee au manager sur WhatsApp.', 'system');
      }}
    }} catch(e) {{
      addMessage('Erreur de connexion', 'error');
    }}
    document.getElementById('typing').textContent = '';
    document.getElementById('sendBtn').disabled = false;
    input.focus();
  }}

  function addMessage(text, type) {{
    const messages = document.getElementById('messages');
    const div = document.createElement('div');
    div.className = 'msg ' + type;
    div.textContent = text;
    messages.appendChild(div);
    messages.scrollTop = messages.scrollHeight;
  }}

  function newConversation() {{
    sessionId = Date.now().toString();
    history = [];
    document.getElementById('messages').innerHTML = '<div class="msg agent">Bonjour ! Bienvenue chez {RESTAURANT}. Comment puis-je vous aider ? 😊</div>';
  }}
</script>
</body>
</html>"""

@app.route("/chat", methods=["POST"])
def chat():
    data = request.json
    message = data.get("message", "")
    session_id = data.get("session_id", "default")
    history = data.get("history", [])

    if session_id not in sessions:
        sessions[session_id] = {"phone": "Interface web", "info_collected": {}, "intent": None, "language": "fr"}

    session = sessions[session_id]
    result = detect_language_and_intent(message, history)

    session["language"] = result.get("language", "fr")
    session["intent"] = result.get("intent", session.get("intent"))
    session["order_summary"] = result.get("order_summary", "")

    if "info_collected" not in session:
        session["info_collected"] = {}
    session["info_collected"].update(result.get("info_collected", {}))

    if result.get("is_complete"):
        try:
            send_whatsapp_notification(session)
        except Exception as e:
            print(f"WhatsApp error: {e}")

    return jsonify({
        "response": result.get("response", "Je n'ai pas compris."),
        "is_complete": result.get("is_complete", False),
        "intent": result.get("intent"),
        "language": result.get("language")
    })

@app.route("/voice/incoming", methods=["GET", "POST"])
def incoming_call():
    call_sid = request.form.get("CallSid", "test")
    caller = request.form.get("From", "Inconnu")
    sessions[call_sid] = {"phone": caller, "history": [], "intent": None, "language": "fr", "info_collected": {}}
    response = VoiceResponse()
    response.say(f"{RESTAURANT}, bonjour ! Comment puis-je vous aider ?", language="fr-FR", voice="woman")
    gather = Gather(input="speech", action="/voice/process", speechTimeout="auto", language="fr-FR", enhanced=True)
    response.append(gather)
    return Response(str(response), mimetype="text/xml")

@app.route("/voice/process", methods=["GET", "POST"])
def process_speech():
    call_sid = request.form.get("CallSid", "test")
    speech_result = request.form.get("SpeechResult", "")

    if call_sid not in sessions:
        sessions[call_sid] = {"phone": request.form.get("From", ""), "history": [], "info_collected": {}}

    session = sessions[call_sid]
    response = VoiceResponse()

    if not speech_result:
        response.say("Desole, je n'ai pas entendu. Pouvez-vous repeter ?", language="fr-FR")
        gather = Gather(input="speech", action="/voice/process", speechTimeout="auto")
        response.append(gather)
        return Response(str(response), mimetype="text/xml")

    context = "\n".join(session.get("history", []))
    result = detect_language_and_intent(f"Historique:\n{context}\n\nClient: {speech_result}")

    session["history"].append(f"Client: {speech_result}")
    session["history"].append(f"Agent: {result.get('response', '')}")
    session["language"] = result.get("language", "fr")
    session["intent"] = result.get("intent", session.get("intent"))
    session["order_summary"] = result.get("order_summary", "")
    if "info_collected" not in session:
        session["info_collected"] = {}
    session["info_collected"].update(result.get("info_collected", {}))

    agent_response = result.get("response", "Je n'ai pas compris, pouvez-vous repeter ?")
    lang_map = {"fr": "fr-FR", "en": "en-US", "ar": "ar-SA"}
    twiml_lang = lang_map.get(result.get("language", "fr"), "fr-FR")

    if result.get("is_complete"):
        send_whatsapp_notification(session)
        response.say(agent_response, language=twiml_lang)
        response.say("Merci pour votre appel. Au revoir !", language=twiml_lang)
        response.hangup()
    else:
        response.say(agent_response, language=twiml_lang)
        gather = Gather(input="speech", action="/voice/process", speechTimeout="auto", language=twiml_lang, enhanced=True)
        response.append(gather)

    return Response(str(response), mimetype="text/xml")

if __name__ == "__main__":
    app.run(debug=True, port=5000)