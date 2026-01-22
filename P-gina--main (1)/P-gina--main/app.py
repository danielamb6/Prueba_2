from flask import Flask, request, jsonify
from flask_cors import CORS
import psycopg2
from psycopg2.extras import RealDictCursor
import datetime

app = Flask(__name__)
CORS(app)

# --- CONEXIÓN BD ---
# Asegúrate de que esta URI sea la correcta y esté activa
DB_URI = 'postgresql://neondb_owner:npg_LOQTwP86bvYc@ep-floral-meadow-ahobjrmx-pooler.c-3.us-east-1.aws.neon.tech/neondb?sslmode=require'

def get_db_connection():
    try:
        conn = psycopg2.connect(DB_URI)
        return conn
    except Exception as e:
        print(f"❌ Error DB: {e}")
        return None

# ==========================================
# 1. DASHBOARD Y KPC (Tarjetas Informativas)
# ==========================================

@app.route('/api/dashboard/stats', methods=['GET'])
def get_dashboard_stats():
    conn = get_db_connection()
    if not conn: return jsonify({})
    try:
        cur = conn.cursor()
        stats = {}
        # Conteo de Técnicos Activos
        cur.execute("SELECT COUNT(*) FROM tecnicos WHERE activo = TRUE")
        stats['tecnicos'] = cur.fetchone()[0]
        # Conteo de Empresas
        cur.execute("SELECT COUNT(*) FROM empresas")
        stats['empresas'] = cur.fetchone()[0]
        # Conteo de Clientes Activos
        cur.execute("SELECT COUNT(*) FROM cliente WHERE activo = TRUE")
        stats['clientes'] = cur.fetchone()[0]
        return jsonify(stats)
    except Exception as e:
        return jsonify({"error": str(e)})
    finally:
        conn.close()

@app.route('/api/dashboard/ultimos-tickets', methods=['GET'])
def get_ultimos_tickets_fichas():
    # Conectado a fichas_tecnicas como solicitaste
    conn = get_db_connection()
    if not conn: return jsonify([])
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        query = """
            SELECT 
                ft.id as id_ficha,
                t.id as id_ticket,
                t.estado,
                t.fecha_creacion,
                fr.falla as falla_descripcion,
                CONCAT(tec.nombre, ' ', tec.primer_apellido) as tecnico_nombre,
                e.empresa,
                c.nombre as cliente_nombre
            FROM fichas_tecnicas ft
            JOIN tickets t ON ft.id_ticket = t.id
            LEFT JOIN falla_reportada fr ON t.id_falla_reportada = fr.id
            LEFT JOIN tecnicos tec ON ft.id_tecnico = tec.id
            LEFT JOIN cliente c ON t.id_clientes = c.id
            LEFT JOIN empresas e ON c.id_empresa = e.id
            ORDER BY t.fecha_creacion DESC LIMIT 50
        """
        cur.execute(query)
        data = cur.fetchall()
        for item in data:
            if item['fecha_creacion']:
                item['fecha_creacion'] = item['fecha_creacion'].strftime('%Y-%m-%d')
        return jsonify(data)
    except Exception as e:
        print(e)
        return jsonify([])
    finally:
        conn.close()

# Para llenar los filtros del dashboard (Técnicos y Fallas)
@app.route('/api/filtros-dashboard', methods=['GET'])
def get_filtros_dashboard():
    conn = get_db_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        data = {}
        cur.execute("SELECT DISTINCT CONCAT(nombre, ' ', primer_apellido) as nombre FROM tecnicos")
        data['tecnicos'] = [x['nombre'] for x in cur.fetchall()]
        cur.execute("SELECT DISTINCT falla FROM falla_reportada")
        data['fallas'] = [x['falla'] for x in cur.fetchall()]
        return jsonify(data)
    except Exception: return jsonify({})
    finally: conn.close()

# Cambio de estado del ticket
@app.route('/api/tickets/<int:id>/estado', methods=['PUT'])
def cambiar_estado_ticket(id):
    data = request.json
    nuevo_estado = data.get('estado')
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("UPDATE tickets SET estado = %s WHERE id = %s", (nuevo_estado, id))
        conn.commit()
        return jsonify({"message": "Estado actualizado"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()

# ==========================================
# 2. INCIDENCIAS (Tickets Desglosados)
# ==========================================
@app.route('/api/incidencias', methods=['GET'])
def get_incidencias_detalle():
    conn = get_db_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        query = """
            SELECT 
                t.id, 
                t.num_autobus,
                t.estado,
                t.fecha_creacion,
                fr.falla as falla,
                CONCAT(c.nombre, ' ', c.primer_apellido) as cliente,
                e.empresa
            FROM tickets t
            LEFT JOIN falla_reportada fr ON t.id_falla_reportada = fr.id
            LEFT JOIN cliente c ON t.id_clientes = c.id
            LEFT JOIN empresas e ON c.id_empresa = e.id
            ORDER BY t.id DESC
        """
        cur.execute(query)
        data = cur.fetchall()
        for d in data:
            if d['fecha_creacion']: d['fecha_creacion'] = d['fecha_creacion'].strftime('%Y-%m-%d')
        return jsonify(data)
    except Exception as e: return jsonify([])
    finally: conn.close()

# ==========================================
# 3. GESTIÓN TÉCNICA (Catálogos)
# ==========================================
@app.route('/api/catalogos/<tabla>', methods=['GET', 'POST'])
def gestionar_catalogos(tabla):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    # Mapeo exacto según tu CSV y solicitud
    config = {
        'cat_elementos': {'t': 'cat_elementos', 'c': 'elemento'},
        'detalle_revision': {'t': 'detalle_revision', 'c': 'descripción'}, # Ojo con el acento en BD
        'solucion': {'t': 'solucion', 'c': 'solución'}, # Ojo con el acento en BD
        'equipo': {'t': 'equipo', 'c': 'equipo'}
    }

    if tabla not in config: return jsonify({"error": "Tabla no válida"}), 400
    
    t_name = config[tabla]['t']
    c_name = config[tabla]['c']

    try:
        if request.method == 'GET':
            cur.execute(f'SELECT id, "{c_name}" as descripcion FROM "{t_name}" ORDER BY id DESC')
            return jsonify(cur.fetchall())
        
        elif request.method == 'POST':
            val = request.json.get('valor')
            # Si es cat_elementos o detalle_revision, requerimos un id_equipo dummy o real. 
            # Para simplificar este ejemplo, insertamos NULL en id_equipo si la BD lo permite, 
            # o deberíamos pedir el id_equipo. Asumiré inserción simple por ahora.
            cur.execute(f'INSERT INTO "{t_name}" ("{c_name}") VALUES (%s)', (val,))
            conn.commit()
            return jsonify({"message": "Agregado"}), 201
    except Exception as e:
        print(e)
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()

@app.route('/api/catalogos/<tabla>/<int:id>', methods=['DELETE'])
def eliminar_catalogo(tabla, id):
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        # Mapeo simple de tabla URL a tabla BD
        mapa = {
            'detalle_revision': 'detalle_revision',
            'solucion': 'solucion',
            'cat_elementos': 'cat_elementos',
            'equipo': 'equipo'
        }
        t_name = mapa.get(tabla, tabla)
        cur.execute(f'DELETE FROM "{t_name}" WHERE id = %s', (id,))
        conn.commit()
        return jsonify({"message": "Eliminado"}), 200
    except Exception as e: return jsonify({"error": str(e)}), 500
    finally: conn.close()

# ==========================================
# 4. TÉCNICOS Y CLIENTES (Con Toggles)
# ==========================================

@app.route('/api/tecnicos', methods=['GET'])
def get_tecnicos_full():
    conn = get_db_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        # JOIN con especialidad
        query = """
            SELECT t.id, t.nombre, t.primer_apellido, t.activo, e.especialidad
            FROM tecnicos t
            LEFT JOIN especialidad e ON t.id_especialidad = e.id
            ORDER BY t.id
        """
        cur.execute(query)
        return jsonify(cur.fetchall())
    except Exception: return jsonify([])
    finally: conn.close()

@app.route('/api/clientes', methods=['GET'])
def get_clientes_full():
    conn = get_db_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        query = """
            SELECT c.id, c.nombre, c.primer_apellido, c.activo, emp.empresa
            FROM cliente c
            LEFT JOIN empresas emp ON c.id_empresa = emp.id
            ORDER BY c.id
        """
        cur.execute(query)
        return jsonify(cur.fetchall())
    except Exception: return jsonify([])
    finally: conn.close()

@app.route('/api/toggle/<tipo>/<int:id>', methods=['PUT'])
def toggle_estado(tipo, id):
    # tipo: 'tecnico', 'cliente', 'admin'
    tablas = {'tecnico': 'tecnicos', 'cliente': 'cliente', 'admin': 'admin'}
    tabla_bd = tablas.get(tipo)
    if not tabla_bd: return jsonify({"error": "Tipo inválido"}), 400

    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute(f"UPDATE {tabla_bd} SET activo = NOT activo WHERE id = %s", (id,))
        conn.commit()
        return jsonify({"message": "Estado cambiado"}), 200
    except Exception as e: return jsonify({"error": str(e)}), 500
    finally: conn.close()

# ==========================================
# 5. ADMIN (Registro)
# ==========================================

@app.route('/api/admin', methods=['GET', 'POST'])
def gestion_admin():
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        if request.method == 'GET':
            cur.execute("SELECT id, nombre, usuario, rol, correo, activo FROM admin ORDER BY id DESC")
            return jsonify(cur.fetchall())
        
        elif request.method == 'POST':
            d = request.json
            sql = """
                INSERT INTO admin 
                (nombre, primer_apellido, segundo_apellido, contrasena, usuario, rol, correo, activo)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """
            cur.execute(sql, (
                d['nombre'], d['primer_apellido'], d['segundo_apellido'], 
                d['contrasena'], d['usuario'], d['rol'], d['correo'], True
            ))
            conn.commit()
            return jsonify({"message": "Admin registrado"}), 201
    except Exception as e:
        print(f"Error Admin: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()

if __name__ == '__main__':
    app.run(debug=True, port=5000)