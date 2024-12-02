import requests
from flask import Flask, render_template, request, jsonify, flash
from gevent.pywsgi import WSGIServer
from datetime import datetime, timedelta
import sqlite3

app = Flask(__name__)
app.secret_key = "supersecretkey"  # Necesario para usar mensajes flash

# Verificar caché en la base de datos
def obtener_precio_actual(symbol):
    API_KEY = "1DomrXlMKxYD26M8CundrQBaInhTMU8S"
    CACHE_DURATION = timedelta(hours=1)  # Duración de la caché

    # Conexión a la base de datos
    conn = sqlite3.connect("precios.db")
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
                    (symbol, precio_actual, datetime.now().isoformat()),
                )
                conn.commit()
                conn.close()
                return precio_actual

    except requests.exceptions.RequestException as e:
        print(f"Error al hacer la solicitud: {e}")

    conn.close()
    return None


# Obtener el historial de compras desde la base de datos
def obtener_historial_compras():
    conn = sqlite3.connect("precios.db")
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT fecha_compra, symbol, cantidad_acciones, valor_compra, precio_actual, 
               valor_total, valor_actual, ganancia_perdida, porcentaje 
        FROM historial_compras
        """
    )
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
            "porcentaje": registro[8],
        }
        for registro in historial
    ]
    return historial_compras


# Validar datos de entrada
def validar_datos(fecha_compra, symbol, cantidad_acciones, valor_compra):
    # Validar fecha
    try:
        datetime.strptime(fecha_compra, "%Y-%m-%d")
    except ValueError:
        return "Error: Formato de fecha inválido. Use aaaa-mm-dd."

    # Validar símbolo de empresa
    if not symbol.isalpha() or not (2 <= len(symbol) <= 3) or not symbol.isupper():
        return "Error: El código de empresa debe tener 2 o 3 letras en mayúscula."

    # Validar cantidad de acciones
    if not isinstance(cantidad_acciones, int) or cantidad_acciones <= 0:
        return "Error: La cantidad debe ser un número entero positivo mayor que cero."

    # Validar valor de compra
    if not isinstance(valor_compra, (int, float)) or valor_compra <= 0:
        return "Error: El valor debe ser un número positivo mayor que cero."

    return None  # Sin errores


# Ruta principal para el formulario y el historial de compras
@app.route("/", methods=["GET", "POST"])
def home():
    if request.method == "POST":
        fecha_compra = request.form.get("fecha_compra")
        symbol = request.form.get("empresa")
        try:
            cantidad_acciones = int(request.form.get("cantidad_acciones"))
            valor_compra = float(request.form.get("valor_compra"))
        except ValueError:
            flash("Error: Cantidad o valor no válidos.")
            return render_template("index.html", historial=obtener_historial_compras())

        # Validar los datos
        error = validar_datos(fecha_compra, symbol, cantidad_acciones, valor_compra)
        if error:
            flash(error)
            return render_template("index.html", historial=obtener_historial_compras())

        precio_actual = obtener_precio_actual(symbol)
        if precio_actual is None:
            flash("Error: No se pudo obtener el precio actual de la empresa.")
            return render_template("index.html", historial=obtener_historial_compras())

        valor_total = round(cantidad_acciones * valor_compra, 2)
        valor_actual = round(cantidad_acciones * precio_actual, 2)
        ganancia_perdida = round(valor_actual - valor_total, 2)
        porcentaje = round((ganancia_perdida / valor_total) * 100, 2)

        # Guardar el registro en la base de datos
        conn = sqlite3.connect("precios.db")
        cursor = conn.cursor()
        cursor.execute(
            """ 
            INSERT INTO historial_compras (fecha_compra, symbol, cantidad_acciones, valor_compra, 
                precio_actual, valor_total, valor_actual, ganancia_perdida, porcentaje)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                fecha_compra,
                symbol,
                cantidad_acciones,
                valor_compra,
                precio_actual,
                valor_total,
                valor_actual,
                ganancia_perdida,
                porcentaje,
            ),
        )
        conn.commit()
        conn.close()

        flash("Compra registrada exitosamente.")
    return render_template("index.html", historial=obtener_historial_compras())


# Ruta para obtener el precio actual de una acción en función de su símbolo
@app.route("/precio_actual", methods=["GET"])
def precio_actual():
    symbol = request.args.get("symbol")
    precio = obtener_precio_actual(symbol)
    if precio:
        return jsonify({"precio_actual": precio})
    else:
        return jsonify({"error": "No se pudo obtener el precio actual"}), 404


if __name__ == "__main__":
    http_server = WSGIServer(("0.0.0.0", 5000), app)
    print("Servidor corriendo en http://127.0.0.1:5000")
    http_server.serve_forever()
