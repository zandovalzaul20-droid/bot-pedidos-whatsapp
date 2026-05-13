import os
import psycopg2
from psycopg2.extras import RealDictCursor

def get_conn():
    return psycopg2.connect(
        os.environ.get("DATABASE_URL"),
        sslmode="require",
        connect_timeout=10
    )

def ejecutar(query, params=(), fetch=None):
    """Ejecuta una query con reconexion automatica"""
    for intento in range(3):
        try:
            conn = get_conn()
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute(query, params)
            result = None
            if fetch == "all":
                result = [dict(r) for r in cur.fetchall()]
            elif fetch == "one":
                row = cur.fetchone()
                result = dict(row) if row else None
            conn.commit()
            cur.close()
            conn.close()
            return result
        except Exception as e:
            print(f"Error DB intento {intento+1}: {e}")
            if intento == 2:
                raise

def init_db():
    ejecutar("""
        CREATE TABLE IF NOT EXISTS pedidos (
            id SERIAL PRIMARY KEY,
            numero TEXT,
            pedido TEXT,
            direccion TEXT,
            fecha TEXT,
            hora TEXT,
            nombre_receptor TEXT,
            tel_receptor TEXT,
            tipo_entrega TEXT,
            dedicatoria TEXT,
            firma TEXT,
            observaciones TEXT,
            estado TEXT DEFAULT '⏳ En espera de anticipo',
            costo_envio NUMERIC DEFAULT 0,
            precio_ramo NUMERIC DEFAULT 0,
            notas_internas TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

def guardar_pedido_db(numero, pedido, direccion, fecha="", hora="",
                      nombre_receptor="", tel_receptor="", tipo_entrega="",
                      dedicatoria="", firma="", observaciones="", precio_ramo=0):
    ejecutar("""
        INSERT INTO pedidos (numero, pedido, direccion, fecha, hora, nombre_receptor,
                            tel_receptor, tipo_entrega, dedicatoria, firma, observaciones, precio_ramo)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """, (numero, pedido, direccion, fecha, hora, nombre_receptor,
          tel_receptor, tipo_entrega, dedicatoria, firma, observaciones, precio_ramo))

def obtener_pedidos_db():
    return ejecutar("SELECT * FROM pedidos ORDER BY created_at DESC", fetch="all") or []

def obtener_pedidos_por_numero_db(numero):
    return ejecutar(
        "SELECT * FROM pedidos WHERE numero = %s ORDER BY created_at DESC",
        (numero,), fetch="all"
    ) or []

def obtener_pedidos_por_fecha_db(fecha):
    return ejecutar(
        "SELECT * FROM pedidos WHERE fecha = %s ORDER BY hora ASC",
        (fecha,), fetch="all"
    ) or []

def actualizar_estado_db(pedido_id, estado):
    ejecutar("UPDATE pedidos SET estado = %s WHERE id = %s", (estado, pedido_id))

def actualizar_envio_db(pedido_id, costo_envio):
    ejecutar("UPDATE pedidos SET costo_envio = %s WHERE id = %s", (costo_envio, pedido_id))

def actualizar_nota_db(pedido_id, nota):
    ejecutar("UPDATE pedidos SET notas_internas = %s WHERE id = %s", (nota, pedido_id))
