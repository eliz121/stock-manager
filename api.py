import requests
from flask import Flask, render_template, request, jsonify, flash
from gevent.pywsgi import WSGIServer
from datetime import datetime, timedelta
import sqlite3
from dotenv import load_dotenv
import os

load_dotenv()  # Carga las variables del archivo .env
API_KEY = os.getenv("FINANCIAL_MODELING_API_KEY")


if not API_KEY:
    raise ValueError("API key no configurada en el archivo .env")

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY')

if not app.secret_key:
    raise ValueError("Flask secret key no configurada en el archivo .env")

# Verificar caché en la base de datos
def obtener_precio_actual(symbol):
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


@app.route('/', methods=['GET', 'POST'])
def home():
    # Capturar los parámetros de ordenamiento correctos
    ordenar_por = request.args.get("ordenar_por", "fecha_compra")
    direccion = request.args.get("direccion", "asc")
    
    # Mapear los criterios de ordenamiento del frontend al backend
    criterios_mapping = {
        "nombre": "symbol",
        "ganancia": "ganancia_perdida",
        "fecha": "fecha_compra"
    }
    
    # Convertir el criterio del frontend al nombre de columna correcto
    orden_campo = criterios_mapping.get(ordenar_por, "fecha_compra")
    
    if request.method == "POST":
        try:
            # Obtener y validar fecha
            fecha_compra = request.form.get("fecha_compra")
            if not fecha_compra:
                raise ValueError("La fecha de compra es obligatoria")
            
            try:
                fecha_parsed = datetime.strptime(fecha_compra, '%Y-%m-%d')
                if fecha_parsed > datetime.now():
                    raise ValueError("La fecha no puede ser futura")
            except ValueError as e:
                raise ValueError("Fecha inválida")

            # Obtener y validar símbolo de empresa
            symbol = request.form.get("empresa", "").strip().upper()
            if not symbol:
                raise ValueError("El símbolo de la empresa es obligatorio")
            if not symbol.isalpha():
                raise ValueError("El símbolo debe contener solo letras")

            # Obtener y validar cantidad de acciones
            try:
                cantidad_acciones = int(request.form.get("cantidad_acciones", 0))
                if cantidad_acciones <= 0:
                    raise ValueError("La cantidad de acciones debe ser mayor a 0")
            except ValueError:
                raise ValueError("La cantidad de acciones debe ser un número entero válido")

            # Obtener y validar valor de compra
            try:
                valor_compra = float(request.form.get("valor_compra", 0))
                if valor_compra <= 0:
                    raise ValueError("El valor de compra debe ser mayor a 0")
            except ValueError:
                raise ValueError("El valor de compra debe ser un número válido")

            # Validar que el símbolo existe y obtener precio actual
            precio_actual = obtener_precio_actual(symbol)
            if precio_actual is None:
                raise ValueError("No se pudo obtener el precio actual para este símbolo")

            # Cálculos
            valor_total = round(cantidad_acciones * valor_compra, 2)
            valor_actual = round(cantidad_acciones * precio_actual, 2)
            ganancia_perdida = round(valor_actual - valor_total, 2)
            porcentaje = round((ganancia_perdida / valor_total) * 100, 2)

            # Guardar en la base de datos
            try:
                conn = sqlite3.connect("precios.db")
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO historial_compras (
                        fecha_compra, symbol, cantidad_acciones, valor_compra,
                        precio_actual, valor_total, valor_actual, ganancia_perdida, porcentaje
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    fecha_compra, symbol, cantidad_acciones, valor_compra,
                    precio_actual, valor_total, valor_actual, ganancia_perdida, porcentaje
                ))
                conn.commit()
                flash("Registro guardado exitosamente", "success")
            except sqlite3.Error as e:
                raise ValueError(f"Error al guardar en la base de datos: {str(e)}")
            finally:
                conn.close()

        except ValueError as e:
            flash(str(e), "error")
        except Exception as e:
            flash("Error inesperado al procesar la solicitud", "error")

    # Obtener y mostrar el historial ordenado
    try:
        historial = obtener_historial_compras(orden_campo, direccion)
        return render_template("index.html", 
                             historial=historial,
                             orden_actual=ordenar_por,
                             direccion_actual=direccion)
    except Exception as e:
        flash(f"Error al obtener el historial: {str(e)}")
        return render_template("index.html", historial=[])

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

# Actualiza la ruta en el backend (Python)
@app.route('/buscar_simbolo', methods=['GET'])
def buscar_simbolo():
    term = request.args.get("term", "").upper()
    if not term or len(term) < 2:
        return jsonify({"simbolos": []})
    
    API_KEY = os.getenv("FINANCIAL_MODELING_API_KEY")
    if not API_KEY:
        return jsonify({"error": "API key no configurada"}), 500

    try:
        # Usar la API de búsqueda de FMP
        url = "https://financialmodelingprep.com/api/v3/search"
        params = {
            "query": term,
            "limit": 10,
            "apikey": API_KEY
        }
        
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()

        # Formatear los resultados
        simbolos = [
            {
                "symbol": item["symbol"],
                "nombre": f"{item['name']} ({item['symbol']})"
            }
            for item in data
            if item.get("symbol") and item.get("name")
        ]

        return jsonify({"simbolos": simbolos})

    except requests.exceptions.RequestException as e:
        print(f"Error en la API: {str(e)}")
        return jsonify({"error": "Error al buscar símbolos"}), 500
    except Exception as e:
        print(f"Error inesperado: {str(e)}")
        return jsonify({"error": "Error inesperado"}), 500

if __name__ == "__main__":
    http_server = WSGIServer(('0.0.0.0', 5000), app)
    print("Servidor corriendo en http://127.0.0.1:5000")
    http_server.serve_forever()
