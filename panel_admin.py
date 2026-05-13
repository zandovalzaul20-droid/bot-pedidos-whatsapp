from flask import Flask, request, jsonify, session, send_from_directory
import json
import os
from functools import wraps
from db import init_db, obtener_pedidos_db, actualizar_estado_db, actualizar_envio_db, actualizar_nota_db, guardar_pedido_db

print("Panel admin cargado correctamente - version con notificaciones")

app = Flask(__name__, static_folder="panel_static")
app.secret_key = "floreria-candelaria-secret-2024"

try:
    init_db()
except Exception as e:
    print(f"Error iniciando DB: {e}")

CONFIG_FILE = "config.json"
ADMIN_USER = "admin"
ADMIN_PASS = "password"


def cargar_config():
    if not os.path.exists(CONFIG_FILE):
        return {}
    with open(CONFIG_FILE, encoding="utf-8") as f:
        return json.load(f)


def guardar_config(data):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in"):
            return jsonify({"error": "No autorizado"}), 401
        return f(*args, **kwargs)
    return decorated



# =========================
# MENSAJES DE NOTIFICACION POR ESTADO
# =========================
NOTIFICACIONES_ESTADO = {
    "✅ Anticipo recibido": "✅ *¡Anticipo confirmado!*\n\nRecibimos tu pago, ya estamos preparando tu ramo 🌸\nTe avisaremos cuando esté listo.",
    "🌸 En preparación": "🌸 *Tu ramo está en preparación*\n\nEstamos preparando tu pedido con mucho cariño 💐\nPronto te avisamos cuando esté listo.",
    "🚚 En camino": "🚚 *¡Tu pedido va en camino!*\n\nTu ramo ya está en camino a tu domicilio.\nEstaremos contigo en breve 🌹",
    "🏪 Listo para recoger": "🏪 *¡Tu ramo está listo!*\n\nYa puedes pasar a recoger tu pedido 🌸\nTe esperamos.",
    "✔️ Entregado": "✔️ *¡Pedido entregado!*\n\nEsperamos que disfrutes mucho tu ramo 🌹\n¡Gracias por confiar en Florería Ferrer!",
    "❌ Cancelado": "❌ *Pedido cancelado*\n\nTu pedido ha sido cancelado.\nSi tienes dudas, contáctanos directamente."
}


def enviar_notificacion_cliente(numero, estado):
    mensaje = NOTIFICACIONES_ESTADO.get(estado)
    if not mensaje:
        return

    try:
        import requests as req
        ACCESS_TOKEN = os.getenv("WHATSAPP_ACCESS_TOKEN")
        PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")

        if not ACCESS_TOKEN or not PHONE_NUMBER_ID:
            return

        numero_limpio = "".join(ch for ch in str(numero) if ch.isdigit())
        if numero_limpio.startswith("521") and len(numero_limpio) == 13:
            numero_limpio = "52" + numero_limpio[3:]

        url = f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages"
        headers = {"Authorization": f"Bearer {ACCESS_TOKEN}", "Content-Type": "application/json"}
        body = {
            "messaging_product": "whatsapp",
            "to": numero_limpio,
            "type": "text",
            "text": {"body": mensaje}
        }
        response = req.post(url, headers=headers, json=body)
        print(f"[Notificacion estado] To: {numero_limpio} | Status: {response.status_code}")
    except Exception as e:
        print(f"Error enviando notificacion: {e}")

@app.route("/")
def index():
    return send_from_directory("panel_static", "index.html")


@app.route("/catalogo")
def catalogo():
    return send_from_directory("panel_static", "catalogo.html")


@app.route("/api/login", methods=["POST"])
def login():
    data = request.get_json()
    if data.get("usuario") == ADMIN_USER and data.get("password") == ADMIN_PASS:
        session["logged_in"] = True
        return jsonify({"ok": True})
    return jsonify({"ok": False, "error": "Usuario o contraseña incorrectos"}), 401


@app.route("/api/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"ok": True})


@app.route("/api/productos", methods=["GET"])
def get_productos():
    config = cargar_config()
    return jsonify(config.get("productos", {}))


@app.route("/api/productos", methods=["POST"])
@login_required
def update_productos():
    config = cargar_config()
    config["productos"] = request.get_json()
    guardar_config(config)
    return jsonify({"ok": True})


@app.route("/api/mensajes", methods=["GET"])
@login_required
def get_mensajes():
    config = cargar_config()
    return jsonify(config.get("mensajes", {}))


@app.route("/api/mensajes", methods=["POST"])
@login_required
def update_mensajes():
    config = cargar_config()
    config["mensajes"] = request.get_json()
    guardar_config(config)
    return jsonify({"ok": True})


@app.route("/api/negocio", methods=["GET"])
def get_negocio():
    config = cargar_config()
    return jsonify(config.get("negocio", {}))


@app.route("/api/negocio", methods=["POST"])
@login_required
def update_negocio():
    config = cargar_config()
    config["negocio"] = request.get_json()
    guardar_config(config)
    return jsonify({"ok": True})


@app.route("/api/pedidos", methods=["GET"])
@login_required
def get_pedidos():
    try:
        pedidos = obtener_pedidos_db()
        # Mapear campos de DB a los nombres que espera el frontend
        result = []
        for p in pedidos:
            result.append({
                "_fila": p.get("id"),
                "Numero": p.get("numero"),
                "Pedido": p.get("pedido"),
                "Direccion": p.get("direccion"),
                "Fecha": p.get("fecha"),
                "Hora": p.get("hora"),
                "Nombre Receptor": p.get("nombre_receptor"),
                "Tel. Receptor": p.get("tel_receptor"),
                "Tipo Entrega": p.get("tipo_entrega"),
                "Dedicatoria": p.get("dedicatoria"),
                "Observaciones": p.get("observaciones"),
                "Estado": p.get("estado"),
                "Costo Envio": p.get("costo_envio"),
                "Precio Ramo": p.get("precio_ramo"),
                "Notas Internas": p.get("notas_internas"),
            })
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/pedidos/estado", methods=["POST"])
@login_required
def update_estado_pedido():
    try:
        data = request.get_json()
        pedido_id = data.get("fila")
        nuevo_estado = data.get("estado")
        numero_cliente = data.get("numero", "")
        actualizar_estado_db(pedido_id, nuevo_estado)
        if numero_cliente:
            enviar_notificacion_cliente(numero_cliente, nuevo_estado)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    os.makedirs("panel_static", exist_ok=True)
    app.run(port=5001, debug=True)
