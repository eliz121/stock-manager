import pytest
import sqlite3
from api import app, obtener_precio_actual, obtener_historial_compras

# Crear un cliente de prueba para interactuar con la aplicación Flask
@pytest.fixture
def client():
    app.config['TESTING'] = True
    app.config['DATABASE'] = 'test.db'  # Utilizar una base de datos en memoria para las pruebas
    with app.test_client() as client:
        yield client

# Limpiar la base de datos de prueba antes y después de cada prueba
@pytest.fixture(autouse=True)
def clean_db():
    conn = sqlite3.connect('test.db')
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE IF NOT EXISTS precios (symbol TEXT, precio REAL, fecha TEXT)")
    cursor.execute("CREATE TABLE IF NOT EXISTS historial_compras (fecha_compra TEXT, symbol TEXT, cantidad_acciones INTEGER, valor_compra REAL, precio_actual REAL, valor_total REAL, valor_actual REAL, ganancia_perdida REAL, porcentaje REAL)")
    conn.commit()
    conn.close()

    yield

    # Limpiar después de la prueba
    conn = sqlite3.connect('test.db')
    cursor = conn.cursor()
    cursor.execute("DROP TABLE IF EXISTS precios")
    cursor.execute("DROP TABLE IF EXISTS historial_compras")
    conn.commit()
    conn.close()

# Prueba para la función obtener_precio_actual
def test_obtener_precio_actual():
    # Supongamos que el símbolo "AAPL" tiene un precio válido
    precio = obtener_precio_actual("AAPL")
    assert precio is not None
    assert isinstance(precio, float)

# Prueba para la ruta /precio_actual en la aplicación Flask
def test_precio_actual(client):
    # Realiza una solicitud GET a la ruta /precio_actual con el símbolo "AAPL"
    response = client.get('/precio_actual?symbol=AAPL')
    assert response.status_code == 200
    assert 'precio_actual' in response.json

# Prueba para la ruta /historial_compras
def test_historial_compras(client):
    # Realiza una solicitud GET a la ruta del historial de compras
    response = client.get('/')
    assert response.status_code == 200
    # Comprobar si los datos del historial están presentes
    assert 'historial' in response.data.decode()

# Prueba para el proceso de agregar una compra
def test_agregar_compra(client):
    # Simular una compra con datos válidos
    data = {
        'fecha_compra': '2024-11-29',
        'empresa': 'AAPL',
        'cantidad_acciones': 10,
        'valor_compra': 150.00
    }

    # Enviar los datos a la ruta principal que maneja la compra
    response = client.post('/', data=data)

    # Comprobar que la respuesta no es un error y la compra fue procesada correctamente
    assert response.status_code == 200
    assert b'Compra registrada exitosamente' in response.data.decode()

# Prueba para la validación de errores (cantidad de acciones negativa)
def test_error_cantidad_acciones(client):
    data = {
        'fecha_compra': '2024-11-29',
        'empresa': 'AAPL',
        'cantidad_acciones': -10,
        'valor_compra': 150.00
    }
    response = client.post('/', data=data)
    assert 'Error: La cantidad no es válida.' in response.data.decode()

# Prueba para la validación de errores (valor de compra negativo)
def test_error_valor_compra(client):
    data = {
        'fecha_compra': '2024-11-29',
        'empresa': 'AAPL',
        'cantidad_acciones': 10,
        'valor_compra': -150.00
    }
    response = client.post('/', data=data)
    assert 'Error: El valor de compra no es válido.' in response.data.decode()

# Prueba para la validación de errores (símbolo de empresa inválido)
def test_error_simbolo_empresa(client):
    data = {
        'fecha_compra': '2024-11-29',
        'empresa': 'INVALID',
        'cantidad_acciones': 10,
        'valor_compra': 150.00
    }
    response = client.post('/', data=data)
    assert 'Error: El símbolo de la empresa no es válido o no se pudo obtener el precio actual.' in response.data.decode()

# Prueba para el historial de compras desde la base de datos
def test_obtener_historial_compras():
    historial = obtener_historial_compras()
    assert isinstance(historial, list)
    assert len(historial) > 0  # Comprobar que el historial no está vacío

