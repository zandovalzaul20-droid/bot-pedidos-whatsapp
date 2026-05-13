import os
import psycopg2
from psycopg2.extras import RealDictCursor

def get_conn():
    return psycopg2.connect(os.environ.get("DATABASE_URL"), sslmode="require")

def init_db():
    """Crea la tabla de pedidos si no existe"""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
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
    conn.commit()
    cur.close()
    conn.close()

def guardar_pedido_db(numero, pedido, direccion, fecha="", hora="",
                      nombre_receptor="", tel_receptor="", tipo_entrega="",
                      dedicatoria="", firma="", observaciones="", precio_ramo=0):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO pedidos (numero, pedido, direccion, fecha, hora, nombre_receptor,
                            tel_receptor, tipo_entrega, dedicatoria, firma, observaciones, precio_ramo)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """, (numero, pedido, direccion, fecha, hora, nombre_receptor,
          tel_receptor, tipo_entrega, dedicatoria, firma, observaciones, precio_ramo))
    conn.commit()
    cur.close()
    conn.close()

def obtener_pedidos_db():
    conn = get_conn()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM pedidos ORDER BY created_at DESC")
    pedidos = cur.fetchall()
    cur.close()
    conn.close()
    return [dict(p) for p in pedidos]

def obtener_pedidos_por_numero_db(numero):
    conn = get_conn()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM pedidos WHERE numero = %s ORDER BY created_at DESC", (numero,))
    pedidos = cur.fetchall()
    cur.close()
    conn.close()
    return [dict(p) for p in pedidos]

def obtener_pedidos_por_fecha_db(fecha):
    conn = get_conn()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM pedidos WHERE fecha = %s ORDER BY hora ASC", (fecha,))
    pedidos = cur.fetchall()
    cur.close()
    conn.close()
    return [dict(p) for p in pedidos]

def actualizar_estado_db(pedido_id, estado):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE pedidos SET estado = %s WHERE id = %s", (estado, pedido_id))
    conn.commit()
    cur.close()
    conn.close()

def actualizar_envio_db(pedido_id, costo_envio):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE pedidos SET costo_envio = %s WHERE id = %s", (costo_envio, pedido_id))
    conn.commit()
    cur.close()
    conn.close()

def actualizar_nota_db(pedido_id, nota):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE pedidos SET notas_internas = %s WHERE id = %s", (nota, pedido_id))
    conn.commit()
    cur.close()
    conn.close()
