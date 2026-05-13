from flask import Flask, request
import requests
import os
import json
import threading
import schedule
import time
from datetime import datetime
from dotenv import load_dotenv
from openpyxl import Workbook, load_workbook
from db import init_db, guardar_pedido_db, obtener_pedidos_por_numero_db
init_db()

load_dotenv()

app = Flask(__name__)

VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")
ACCESS_TOKEN = os.getenv("WHATSAPP_ACCESS_TOKEN")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")
CONFIG_FILE = "config.json"

ESTADOS_USUARIO = {}
CONFIG_DATA = {}


def cargar_config():
    if not os.path.exists(CONFIG_FILE):
        return {"clientes": {}}
    with open(CONFIG_FILE, encoding="utf-8") as f:
        return json.load(f)


CONFIG_DATA = cargar_config()

PALABRAS = CONFIG_DATA.get("palabras_clave", {})
MENSAJES = CONFIG_DATA.get("mensajes", {})
NEGOCIO  = CONFIG_DATA.get("negocio", {})


# =========================
# NORMALIZAR NUMERO
# =========================
def normalizar_numero(numero: str) -> str:
    numero = "".join(ch for ch in str(numero) if ch.isdigit())
    if numero.startswith("521") and len(numero) == 13:
        numero = "52" + numero[3:]
    return numero


# =========================
# ENVIAR MENSAJE DE TEXTO
# =========================
def enviar_mensaje(numero, mensaje):
    numero = normalizar_numero(numero)
    url = f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {ACCESS_TOKEN}", "Content-Type": "application/json"}
    data = {"messaging_product": "whatsapp", "to": numero, "type": "text", "text": {"body": mensaje}}
    response = requests.post(url, headers=headers, json=data)
    print(f"[WhatsApp API] To: {numero} | Status: {response.status_code} | Body: {response.text}")


# =========================
# DETECTAR PEDIDO DESDE CATALOGO WEB
# =========================
def es_pedido_web(texto):
    return "#PEDIDO_WEB" in texto


def procesar_pedido_web(numero, texto, estado):
    try:
        lineas = texto.strip().split("\n")

        def extraer(clave):
            for linea in lineas:
                if clave in linea:
                    partes = linea.split(":", 1)
                    if len(partes) > 1:
                        return partes[1].strip().replace("*", "")
            return ""

        ramo          = extraer("Ramo:")
        color         = extraer("Color:")
        flores        = extraer("Flores:")
        entrega       = extraer("Entrega:")
        direccion     = extraer("Dirección:") or "Recoger en tienda"
        fecha         = extraer("Fecha:")
        hora          = extraer("Hora:")
        receptor      = extraer("Recibe:")
        tel_receptor  = extraer("Tel. receptor:")
        dedicatoria   = extraer("Dedicatoria:")
        firma         = extraer("Firma:")
        observaciones = extraer("Observaciones:")
        precio_ramo_str = extraer("Precio ramo:")

        tipo_entrega = "domicilio" if "domicilio" in entrega.lower() else "recoger"
        pedido_desc  = f"{ramo} | {flores} | Color: {color}"

        guardar_pedido_db(numero, pedido_desc, direccion, fecha, hora, receptor, tel_receptor, tipo_entrega, dedicatoria, firma, observaciones)

        try:
            precio_ramo = float(precio_ramo_str.replace("$", "").strip()) if precio_ramo_str else 0
        except:
            precio_ramo = 0

        resumen = (
            "✅ *¡Pedido recibido!*\n\n"
            f"🌹 *{ramo}*\n"
            f"🎨 Color: {color}\n"
            f"💐 {flores}\n"
            f"📦 Entrega: {entrega}\n"
            f"📅 Fecha: {fecha}\n"
            f"🕐 Hora: {hora}\n"
            f"👤 Recibe: {receptor}\n"
            f"📞 Tel. receptor: {tel_receptor}\n"
        )

        if tipo_entrega == "domicilio":
            resumen += f"📍 Dirección: {direccion}\n"
        if dedicatoria:
            resumen += f"💌 Dedicatoria: {dedicatoria}\n"
            if firma:
                resumen += f"✍️ Firma: {firma}\n"
        if observaciones:
            resumen += f"📝 Observaciones: {observaciones}\n"

        if tipo_entrega == "domicilio":
            resumen += (
                f"\n🌹 Precio ramo: ${precio_ramo:.0f}\n"
                "🚚 Costo de envío: en breve te lo confirmamos\n\n"
                "En cuanto calculemos el envío te avisamos con el total completo y los datos para el anticipo 🌸"
            )
        else:
            anticipo = round(precio_ramo * 0.70)
            restante = precio_ramo - anticipo
            resumen += (
                f"\n🌹 Precio ramo: ${precio_ramo:.0f}\n"
                "🚚 Envío: Sin costo\n"
                "━━━━━━━━━━━━━━━━━━\n"
                f"💰 Total: ${precio_ramo:.0f}\n"
                f"✅ Anticipo (70%): ${anticipo:.0f}\n"
                f"🚪 Resto en entrega: ${restante:.0f}\n\n"
                "💳 Realiza tu anticipo a:\n"
                "*BANORTE* — Candelaria Silva\n"
                "Cuenta: 4189143146721652\n\n"
                "📸 Cuando hayas realizado el depósito, envía tu comprobante aquí."
            )

        enviar_mensaje(numero, resumen)
        estado["paso"] = "esperando_comprobante_pago"
        estado["tipo_entrega"] = tipo_entrega

    except Exception as e:
        print(f"Error procesando pedido web: {e}")
        enviar_mensaje(numero, "Recibimos tu pedido 🌸 En breve te confirmamos los detalles y los datos de pago.")
        estado["paso"] = "esperando_comprobante_pago"


# =========================
# GUARDAR PEDIDO EN EXCEL
# =========================
def guardar_pedido(numero, pedido, direccion, fecha="", hora="", nombre_receptor="",
                   tel_receptor="", tipo_entrega="", dedicatoria="", firma="", observaciones=""):
    guardar_pedido_db(numero, pedido, direccion, fecha, hora, nombre_receptor,
                      tel_receptor, tipo_entrega, dedicatoria, firma, observaciones)


# =========================
# RESUMEN DIARIO
# =========================
NUMERO_CANDELARIA = "15551778433"


def enviar_resumen_diario():
    try:
        archivo = NEGOCIO.get("archivo_pedidos", "pedidos.xlsx")
        if not os.path.exists(archivo):
            return

        wb = load_workbook(archivo)
        ws = wb.active
        headers = [cell.value for cell in ws[1]]
        hoy = datetime.now().strftime("%Y-%m-%d")
        pedidos_hoy = []

        for row in ws.iter_rows(min_row=2, values_only=True):
            pedido = dict(zip(headers, row))
            fecha_pedido = str(pedido.get("Fecha", "") or "")
            if hoy in fecha_pedido:
                pedidos_hoy.append(pedido)

        if not pedidos_hoy:
            mensaje = f"🌸 *Resumen del día {hoy}*\n\nNo hay pedidos programados para hoy. ¡Buen día! 💐"
        else:
            mensaje = f"🌸 *Resumen del día {hoy}*\n\nTienes *{len(pedidos_hoy)}* pedido(s) para hoy:\n\n"
            for i, p in enumerate(pedidos_hoy, 1):
                estado     = p.get("Estado", "⏳")
                tipo       = p.get("Tipo Entrega", "")
                hora_p     = p.get("Hora", "")
                receptor   = p.get("Nombre Receptor", "")
                pedido_desc = p.get("Pedido", "")
                mensaje += (
                    f"*{i}. {pedido_desc}*\n"
                    f"   👤 {receptor} | 🕐 {hora_p}\n"
                    f"   📦 {tipo} | {estado}\n\n"
                )

        numero_limpio = "".join(ch for ch in NUMERO_CANDELARIA if ch.isdigit())
        url = f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages"
        headers_wa = {"Authorization": f"Bearer {ACCESS_TOKEN}", "Content-Type": "application/json"}
        data = {"messaging_product": "whatsapp", "to": numero_limpio, "type": "text", "text": {"body": mensaje}}
        response = requests.post(url, headers=headers_wa, json=data)
        print(f"[Resumen diario] Status: {response.status_code}")

    except Exception as e:
        print(f"Error en resumen diario: {e}")


def iniciar_scheduler():
    schedule.every().day.at("06:00").do(enviar_resumen_diario)
    while True:
        schedule.run_pending()
        time.sleep(30)


scheduler_thread = threading.Thread(target=iniciar_scheduler, daemon=True)
scheduler_thread.start()

# =========================
# RASTREAR PEDIDOS
# =========================
def rastrear_pedidos(numero):
    try:
        numero_normalizado = normalizar_numero(numero)
        pedidos_cliente = obtener_pedidos_por_numero_db(numero_normalizado)
        if not pedidos_cliente:
            enviar_mensaje(numero, "No encontramos pedidos asociados a tu número 🌸\n\nVisita nuestro catálogo:\n👉 " + NEGOCIO.get("url_catalogo", ""))
            return
        mensaje = "🔍 *Tus pedidos:*\n\n"
        for i, p in enumerate(pedidos_cliente, 1):
            mensaje += (
                f"*{i}. {p.get('pedido', '')}*\n"
                f"📅 {p.get('fecha', '-')} | 🕐 {p.get('hora', '-')}\n"
                f"📦 {p.get('tipo_entrega', '-')}\n"
                f"Estado: {p.get('estado', '⏳ En espera de anticipo')}\n\n"
            )
        enviar_mensaje(numero, mensaje)
    except Exception as e:
        print(f"Error rastreando pedidos: {e}")
        enviar_mensaje(numero, "Hubo un error al buscar tus pedidos 🌸")

# =========================
# WEBHOOK
# =========================
@app.route("/webhook", methods=["GET", "POST"])
def webhook():
    if request.method == "GET":
        token = request.args.get("hub.verify_token")
        challenge = request.args.get("hub.challenge")
        if token == VERIFY_TOKEN:
            return challenge
        return "Error", 403

    data = request.get_json(silent=True) or {}

    try:
        entry   = data.get("entry", [])
        changes = entry[0].get("changes", []) if entry else []
        value   = changes[0].get("value", {}) if changes else {}
        mensajes = value.get("messages", [])

        if not mensajes:
            return "evento sin mensaje", 200

        mensaje = mensajes[0]
        numero  = mensaje.get("from")
        estado_usuario = ESTADOS_USUARIO.setdefault(numero, {})

        if not numero:
            return "remitente no encontrado", 200

        # TEXTO
        if mensaje.get("type") == "text":
            texto_original = mensaje.get("text", {}).get("body", "")
            texto = texto_original.lower().strip()

            # PEDIDO DESDE CATALOGO WEB
            if es_pedido_web(texto_original):
                procesar_pedido_web(numero, texto_original, estado_usuario)
                return "ok", 200

            # ESPERANDO COMPROBANTE
            if estado_usuario.get("paso") == "esperando_comprobante_pago":
                enviar_mensaje(numero, "Por favor, comparte la foto del comprobante de tu depósito 📸")
                return "ok", 200

            # AGRADECIMIENTO
            if "gracias" in texto:
                enviar_mensaje(numero, "De nada 😊 ¿Hay algo más en lo que pueda ayudarte?")
                return "ok", 200

            url_catalogo = NEGOCIO.get("url_catalogo", "http://localhost:5001/catalogo")

            if any(p in texto for p in PALABRAS.get("saludo", [])):
                enviar_mensaje(numero, MENSAJES.get("bienvenida", ""))

            elif any(p in texto for p in PALABRAS.get("pedido", [])):
                enviar_mensaje(numero, (
                    f"🌸 Visita nuestro catálogo para ver todos los ramos y hacer tu pedido:\n\n"
                    f"👉 {url_catalogo}\n\n"
                    "Ahí podrás elegir tu ramo, color, cantidad, fecha y horario de entrega. "
                    "Al finalizar, el pedido llegará aquí automáticamente 💐"
                ))

            elif any(p in texto for p in PALABRAS.get("como_agendar", [])):
                enviar_mensaje(numero, MENSAJES.get("como_agendar", ""))
                enviar_mensaje(numero, f"¿Listo para hacer tu pedido? Visita nuestro catálogo:\n👉 {url_catalogo}")

            elif any(p in texto for p in PALABRAS.get("pago", [])):
                enviar_mensaje(numero, MENSAJES.get("metodos_pago", ""))
                enviar_mensaje(numero, f"¿Listo para hacer tu pedido? Visita nuestro catálogo:\n👉 {url_catalogo}")

            elif any(p in texto for p in PALABRAS.get("rastrear", [])):
                rastrear_pedidos(numero)

            else:
                enviar_mensaje(numero, (
                    "No entendí tu mensaje 😅\n\n"
                    "Escribe *hola* para ver el menú principal 🌸\n\n"
                    f"O visita nuestro catálogo directo:\n👉 {url_catalogo}"
                ))

        # IMAGEN (COMPROBANTE)
        elif mensaje.get("type") == "image":
            if estado_usuario.get("paso") == "esperando_comprobante_pago":
                tipo_entrega = estado_usuario.get("tipo_entrega", "domicilio")
                if tipo_entrega == "recoger":
                    enviar_mensaje(numero, MENSAJES.get("comprobante_recoger",
                        "Se verificará tu comprobante y te avisaremos cuando esté listo para recoger 🌸"))
                else:
                    enviar_mensaje(numero, MENSAJES.get("comprobante_domicilio",
                        "Se verificará tu comprobante y te avisaremos cuando tu pedido esté en camino 🚚"))
                estado_usuario.clear()
            else:
                enviar_mensaje(numero, (
                    "Gracias por compartir la imagen 📸\n\n"
                    "Si quieres hacer un pedido visita:\n👉 "
                    + NEGOCIO.get("url_catalogo", "http://localhost:5001/catalogo")
                ))

    except Exception as e:
        print("Error:", e)

    return "ok", 200


# =========================
# MAIN
# =========================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)