import decimal
import requests
from flask import Flask, render_template, redirect, jsonify, flash, request, url_for
from gevent.pywsgi import WSGIServer
from datetime import datetime, timedelta
import sqlite3
from dotenv import load_dotenv
import os
import locale
from decimal import Decimal

load_dotenv()
API_KEY = os.getenv("FINANCIAL_MODELING_API_KEY")

if not API_KEY:
    raise ValueError("API key no configurada en el archivo .env")

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY')

if not app.secret_key:
    raise ValueError("Flask secret key no configurada en el archivo .env")

# Configurar el locale para usar comas en los números
locale.setlocale(locale.LC_ALL, 'en_US.UTF-8')

# Agregar filtro personalizado para formatear números
@app.template_filter('format_number')
def format_number(value):
    if value is None:
        return "0.00"
    try:
        # Convertir a decimal para mayor precisión
        d = Decimal(str(value))
        # Formatear con comas para miles y 2 decimales
        return locale.format_string("%.2f", d, grouping=True)
    except (ValueError, decimal.InvalidOperation):
        return "0.00"

def obtener_precio_actual(symbol):
    CACHE_DURATION = timedelta(hours=1)

    if not symbol or not symbol.isalpha():
        raise ValueError("Símbolo inválido")

    conn = sqlite3.connect('precios.db')
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT precio, fecha FROM precios WHERE symbol = ?", (symbol,))
        resultado = cursor.fetchone()

        if resultado:
            precio, fecha = resultado
            fecha_precio = datetime.fromisoformat(fecha)
            if datetime.now() - fecha_precio < CACHE_DURATION:
                return precio

        API_URL = f"https://financialmodelingprep.com/api/v3/quote/{symbol}"
        response = requests.get(API_URL, params={"apikey": API_KEY}, timeout=5)
        
        if response.status_code == 429:
            raise ValueError("Se ha excedido el límite de solicitudes a la API")  # Cambiado aquí
        elif response.status_code != 200:
            raise ValueError(f"Error al obtener datos de la API: {response.status_code}")
        data = response.json()

        if not data or not isinstance(data, list) or len(data) == 0:
            raise ValueError("No se encontraron datos para este símbolo")

        precio_actual = data[0].get("price")
        if precio_actual is None:
            raise ValueError("No se pudo obtener el precio actual")

        cursor.execute(
            "REPLACE INTO precios (symbol, precio, fecha) VALUES (?, ?, ?)",
            (symbol, precio_actual, datetime.now().isoformat())
        )
        conn.commit()
        return precio_actual

    except requests.exceptions.Timeout:
        raise ValueError("Tiempo de espera agotado al contactar la API")
    except requests.exceptions.RequestException as e:
        raise ValueError(f"Error de conexión: {str(e)}")
    except sqlite3.Error as e:
        raise ValueError(f"Error de base de datos: {str(e)}")
    except Exception as e:
        raise ValueError(f"Error inesperado: {str(e)}")
    finally:
        conn.close()

@app.route('/precio_actual', methods=['GET'])
def precio_actual():
    try:
        symbol = request.args.get("symbol")
        if not symbol:
            return jsonify({"error": "Símbolo no proporcionado"}), 400

        precio = obtener_precio_actual(symbol)
        if precio:
            return jsonify({"precio_actual": precio})
        else:
            return jsonify({"error": "No se pudo obtener el precio actual"}), 404

    except ValueError as e:
        error_message = str(e)
    
    # Manejo específico para el error de límite de solicitudes
        if "límite de solicitudes" in error_message.lower():
            return jsonify({"error": error_message}), 429
    
        return jsonify({"error": error_message}), 400  # Código 400 si es otro ValueError
    
    except Exception:
        return jsonify({"error": "Error interno del servidor"}), 500

@app.route('/buscar_simbolo', methods=['GET'])
def buscar_simbolo():
    term = request.args.get("term", "").upper()
    if not term or len(term) < 2:
        return jsonify({"simbolos": []})
    
    try:
        url = "https://financialmodelingprep.com/api/v3/search"
        response = requests.get(
            url,
            params={"query": term, "limit": 10, "apikey": API_KEY},
            timeout=5
        )
        
        if response.status_code != 200:
            raise ValueError(f"Error en la API: {response.status_code}")

        data = response.json()
        simbolos = [
            {
                "symbol": item["symbol"],
                "nombre": f"{item['name']} ({item['symbol']})"
            }
            for item in data
            if item.get("symbol") and item.get("name")
        ]

        return jsonify({"simbolos": simbolos})

    except requests.exceptions.Timeout:
        return jsonify({"error": "Tiempo de espera agotado"}), 504
    except requests.exceptions.RequestException as e:
        return jsonify({"error": f"Error de conexión: {str(e)}"}), 503
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": "Error interno del servidor"}), 500

# Modificar la ruta principal para manejar los filtros:
@app.route('/', methods=['GET', 'POST'])
def home():
    if request.method == "POST":
        try:
            fecha_compra = request.form.get("fecha_compra")
            if not fecha_compra:
                flash("La fecha de compra es obligatoria", "danger")
                return redirect(request.url)
            
            try:
                fecha_parsed = datetime.strptime(fecha_compra, '%Y-%m-%d')
                if fecha_parsed > datetime.now():
                    flash("La fecha no puede ser futura", "danger")
                    return redirect(request.url)
            except ValueError:
                flash("Fecha inválida", "danger")
                return redirect(request.url)

            symbol = request.form.get("empresa", "").strip().upper()
            if not symbol:
                flash("El símbolo de la empresa es obligatorio", "danger")
                return redirect(request.url)
            
            flash("Registro guardado exitosamente", "success")
            return redirect(url_for('home'))

        except ValueError as e:
            flash(str(e), "danger")
            return redirect(request.url)
        except Exception as e:
            flash(f"Error inesperado: {str(e)}", "danger")
            return redirect(request.url)

    try:
        # Obtener datos de consolidación
        consolidacion = obtener_consolidacion()
        return render_template("index.html", consolidacion=consolidacion)
    except Exception as e:
        flash(f"Error al obtener la consolidación: {str(e)}", "danger")
        return render_template("index.html", consolidacion=[])

# Modificar la función obtener_consolidacion para usar Decimal
def obtener_consolidacion():
    conn = sqlite3.connect("precios.db")
    cursor = conn.cursor()
    
    try:
        query = """
        SELECT 
            symbol,
            SUM(cantidad_acciones) as cantidad_total,
            SUM(valor_total) as valor_usd_total,
            ROUND(SUM(valor_total) / SUM(cantidad_acciones), 2) as precio_costo
        FROM historial_compras
        GROUP BY symbol
        """
        cursor.execute(query)
        resultados = cursor.fetchall()
        
        consolidacion = []
        for row in resultados:
            symbol, cantidad_total, valor_usd_total, precio_costo = row
            
            try:
                precio_actual = Decimal(str(obtener_precio_actual(symbol)))
                valor_actual_total = precio_actual * Decimal(str(cantidad_total))
                ganancia_perdida = valor_actual_total - Decimal(str(valor_usd_total))
                porcentaje = (ganancia_perdida / Decimal(str(valor_usd_total)) * 100).quantize(Decimal('0.01'))
            except Exception:
                precio_actual = Decimal('0')
                ganancia_perdida = Decimal('0')
                porcentaje = Decimal('0')
            
            consolidacion.append({
                'accion': symbol,
                'cantidad_total': cantidad_total,
                'valor_usd_total': Decimal(str(valor_usd_total)).quantize(Decimal('0.01')),
                'precio_costo': Decimal(str(precio_costo)).quantize(Decimal('0.01')),
                'precio_actual': precio_actual.quantize(Decimal('0.01')),
                'ganancia_perdida': ganancia_perdida.quantize(Decimal('0.01')),
                'porcentaje': porcentaje
            })
        
        return consolidacion
    finally:
        conn.close()

if __name__ == "__main__":
    http_server = WSGIServer(('0.0.0.0', 5000), app)
    print("Servidor corriendo en http://127.0.0.1:5000")
    http_server.serve_forever()