import requests
from flask import Flask, render_template, request, jsonify, flash
from gevent.pywsgi import WSGIServer
from datetime import datetime, timedelta
import sqlite3
from dotenv import load_dotenv
import os

load_dotenv()  # Carga las variables del archivo .env
API_KEY = os.getenv("FINANCIAL_MODELING_API_KEY")
# Acceder a la API key
API_KEY = os.getenv("FINANCIAL_MODELING_API_KEY")

if not API_KEY:
    raise ValueError("API key no configurada en el archivo .env")

app = Flask(__name__)

# Verificar caché en la base de datos
def obtener_precio_actual(symbol):
    API_KEY = os.getenv("FINANCIAL_MODELING_API_KEY")  # Acceder a la API key
    CACHE_DURATION = timedelta(hours=1)  # Duración de la caché

    # Conexión a la base de datos
    conn = sqlite3.connect('precios.db')  
    cursor = conn.cursor()

    # Verificar si el símbolo existe en la caché y si es reciente
    cursor.execute("SELECT precio, fecha FROM precios WHERE symbol = ?", (symbol,))
    resultado = cursor.fetchone()

    if resultado:
        precio, fecha = resultado
        fecha_precio = datetime.fromisoformat(fecha)
        # Si el precio está actualizado, usarlo
        if datetime.now() - fecha_precio < CACHE_DURATION:
            conn.close()
            return precio

    # Si no está en la caché, o es antiguo, consultar a la API
    API_URL = f"https://financialmodelingprep.com/api/v3/quote/{symbol}"
    try:
        response = requests.get(API_URL, params={"apikey": API_KEY})
        response.raise_for_status()
        data = response.json()

        if data and isinstance(data, list) and len(data) > 0:
            precio_actual = data[0].get("price")
            if precio_actual is not None:
                # Almacenar en la caché (actualizar o insertar)
                cursor.execute(
                    "REPLACE INTO precios (symbol, precio, fecha) VALUES (?, ?, ?)",
                    (symbol, precio_actual, datetime.now().isoformat())
                )
                conn.commit()
                conn.close()
                return precio_actual

    except requests.exceptions.RequestException as e:
        print(f"Error al hacer la solicitud: {e}")

    conn.close()
    return None 

def obtener_historial_compras(orden_campo="fecha_compra", orden_direccion="asc"):
    # Validar que el campo y la dirección sean válidos para evitar inyecciones SQL
    campos_validos = ["fecha_compra", "symbol", "cantidad_acciones", "valor_compra", 
                      "precio_actual", "valor_total", "valor_actual", 
                      "ganancia_perdida", "porcentaje"]
    direcciones_validas = ["asc", "desc"]

    if orden_campo not in campos_validos:
        orden_campo = "fecha_compra"
    if orden_direccion not in direcciones_validas:
        orden_direccion = "asc"

    # Conexión a la base de datos
    conn = sqlite3.connect("precios.db")
    cursor = conn.cursor()

    # Construir la consulta dinámica con los parámetros validados
    query = f"""
    SELECT fecha_compra, symbol, cantidad_acciones, valor_compra, precio_actual, 
           valor_total, valor_actual, ganancia_perdida, porcentaje
    FROM historial_compras
    ORDER BY {orden_campo} {orden_direccion.upper()}
    """
    cursor.execute(query)
    historial = cursor.fetchall()
    conn.close()

    # Convertir los resultados a un diccionario
    historial_compras = [
        {
            "fecha_compra": registro[0],
            "symbol": registro[1],
            "cantidad_acciones": registro[2],
            "valor_compra": registro[3],
            "precio_actual": registro[4],
            "valor_total": registro[5],
            "valor_actual": registro[6],
            "ganancia_perdida": registro[7],
            "porcentaje": registro[8]
        }
        for registro in historial
    ]
    return historial_compras


# Ruta principal para el formulario y el historial de compras
@app.route('/', methods=['GET', 'POST'])
def home():
    # Capturar los parámetros de orden del query string
    orden_campo = request.args.get("orden_campo", "fecha_compra")
    orden_direccion = request.args.get("orden_direccion", "asc")

    if request.method == "POST":
        fecha_compra = request.form.get("fecha_compra")
        symbol = request.form.get("empresa")
        cantidad_acciones = int(request.form.get("cantidad_acciones"))
        valor_compra = float(request.form.get("valor_compra"))
        precio_actual = obtener_precio_actual(symbol)
            
        if cantidad_acciones <= 0:
            flash("Error: La cantidad no es válida.")
            return render_template("index.html", historial=obtener_historial_compras(orden_campo, orden_direccion))

        if valor_compra <= 0:
            flash("Error: El valor de compra no es válido.")
            return render_template("index.html", historial=obtener_historial_compras(orden_campo, orden_direccion))
        
        if precio_actual is None:
            flash("Error: El símbolo de la empresa no es válido o no se pudo obtener el precio actual.")
            return render_template("index.html", historial=obtener_historial_compras(orden_campo, orden_direccion))

        valor_total = round(cantidad_acciones * valor_compra, 2)
        valor_actual = round(cantidad_acciones * precio_actual, 2)
        ganancia_perdida = round(valor_actual - valor_total, 2)
        porcentaje = round((ganancia_perdida / valor_total) * 100, 2)

        # Guardar el registro en la base de datos
        conn = sqlite3.connect("precios.db")
        cursor = conn.cursor()
        cursor.execute(""" 
            INSERT INTO historial_compras (fecha_compra, symbol, cantidad_acciones, valor_compra, 
                precio_actual, valor_total, valor_actual, ganancia_perdida, porcentaje)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (fecha_compra, symbol, cantidad_acciones, valor_compra, precio_actual, 
              valor_total, valor_actual, ganancia_perdida, porcentaje))
        conn.commit()
        conn.close()

    # Renderizar el historial con ordenamiento
    historial = obtener_historial_compras(orden_campo, orden_direccion)
    return render_template("index.html", historial=historial)


# Ruta para obtener el precio actual de una acción en función de su símbolo
@app.route('/precio_actual', methods=['GET'])
def precio_actual():
    symbol = request.args.get("symbol")
    precio = obtener_precio_actual(symbol)
    if precio:
        return jsonify({"precio_actual": precio})
    else:
        flash("No se pudo obtener el precio actual.")
        return jsonify({"error": "No se pudo obtener el precio actual"}), 404

# Nueva ruta para buscar empresas (autocompletado)
@app.route('/buscar_empresa', methods=['GET'])
def buscar_empresa():
    query = request.args.get("q")  # Obtener la consulta de la búsqueda
    if query:
        API_KEY = os.getenv("FINANCIAL_MODELING_API_KEY")  # Acceder a la API key
        API_URL = "https://financialmodelingprep.com/api/v3/search"
        try:
            # Realizar la solicitud a la API de Financial Modeling Prep
            response = requests.get(API_URL, params={"query": query, "apikey": API_KEY})
            response.raise_for_status()  # Verificar que la respuesta sea correcta
            data = response.json()

            # Filtrar y preparar los resultados
            resultados = [{"symbol": item["symbol"], "name": item["name"]} for item in data[:10]]  # Limitar a 10 resultados
            return jsonify(resultados)
        except requests.exceptions.RequestException as e:
            print(f"Error al hacer la solicitud: {e}")
            return jsonify({"error": "No se pudieron obtener los resultados de búsqueda."}), 500
    return jsonify({"error": "No se proporcionó ninguna consulta."}), 400

if __name__ == "__main__":
    http_server = WSGIServer(('0.0.0.0', 5000), app)
    print("Servidor corriendo en http://127.0.0.1:5000")
    http_server.serve_forever()
