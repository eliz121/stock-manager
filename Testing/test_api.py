import pytest
import sqlite3
from unittest.mock import patch
from api import app, obtener_precio_actual, obtener_historial_compras

# Configuración para pruebas
@pytest.fixture
def client():
    app.config['TESTING'] = True
    app.config['DATABASE'] = 'test.db'  # Base de datos en memoria para pruebas
    with app.test_client() as client:
        yield client

@pytest.fixture(autouse=True)
def clean_db():
    conn = sqlite3.connect('test.db')
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS historial_compras (
            fecha_compra TEXT, symbol TEXT, cantidad_acciones INTEGER, valor_compra REAL, 
            precio_actual REAL, valor_total REAL, valor_actual REAL, ganancia_perdida REAL, porcentaje REAL
        )
    """)
    conn.commit()
    conn.close()
    yield
    # Limpiar base de datos después de las pruebas
    conn = sqlite3.connect('test.db')
    cursor = conn.cursor()
    cursor.execute("DROP TABLE IF EXISTS historial_compras")
    conn.commit()
    conn.close()

# **Pruebas para HU1: Registro de compras**

def test_registrar_compra_valida(client):
    """Criterios de aceptación: HU1.1 - HU1.6"""
    data = {
        'fecha_compra': '2024-11-30',
        'empresa': 'AAPL',
        'cantidad_acciones': 10,
        'valor_compra': 150.00
    }
    response = client.post('/', data=data)
    assert response.status_code == 200
    assert b"Compra registrada exitosamente" in response.data

def test_registrar_compra_campos_obligatorios(client):
    """Criterio de aceptación: HU1.5"""
    data = {
        'fecha_compra': '',
        'empresa': '',
        'cantidad_acciones': '',
        'valor_compra': ''
    }
    response = client.post('/', data=data)
    assert b"Error: Todos los campos son obligatorios." in response.data

def test_validar_formato_fecha(client):
    """Criterio de aceptación: HU1.1"""
    data = {
        'fecha_compra': '30-11-2024',  # Formato inválido
        'empresa': 'AAPL',
        'cantidad_acciones': 10,
        'valor_compra': 150.00
    }
    response = client.post('/', data=data)
    assert b"Error: Formato de fecha invalido. Use aaaa-mm-dd." in response.data

def test_validar_codigo_empresa(client):
    """Criterio de aceptación: HU1.2"""
    data = {
        'fecha_compra': '2024-11-30',
        'empresa': 'INVALIDO',  # Código no válido
        'cantidad_acciones': 10,
        'valor_compra': 150.00
    }
    response = client.post('/', data=data)
    assert b"Error: El codigo de empresa debe tener 2 o 3 letras en mayuscula." in response.data

def test_validar_cantidad_acciones(client):
    """Criterio de aceptación: HU1.3"""
    data = {
        'fecha_compra': '2024-11-30',
        'empresa': 'AAPL',
        'cantidad_acciones': -10,  # Número negativo
        'valor_compra': 150.00
    }
    response = client.post('/', data=data)
    assert b"Error: La cantidad de acciones debe ser un numero positivo." in response.data

def test_validar_valor_compra(client):
    """Criterio de aceptación: HU1.4"""
    data = {
        'fecha_compra': '2024-11-30',
        'empresa': 'AAPL',
        'cantidad_acciones': 10,
        'valor_compra': -150.00  # Valor negativo
    }
    response = client.post('/', data=data)
    assert b"Error: El valor de compra debe ser mayor que cero." in response.data

def test_prevenir_registros_duplicados(client):
    """Criterio de aceptación: HU1.9"""
    data = {
        'fecha_compra': '2024-11-30',
        'empresa': 'AAPL',
        'cantidad_acciones': 10,
        'valor_compra': 150.00
    }
    client.post('/', data=data)
    response = client.post('/', data=data)  # Intento de registro duplicado
    assert b"Error: Registro duplicado no permitido." in response.data

# **Pruebas para HU2: Historial de compras**

def test_historial_compras_filtrado_por_fecha(client):
    """Criterios de aceptación: HU2.1, HU2.9"""
    # Registrar compras para realizar la prueba
    data1 = {'fecha_compra': '2024-11-29', 'empresa': 'AAPL', 'cantidad_acciones': 10, 'valor_compra': 150.00}
    data2 = {'fecha_compra': '2024-11-30', 'empresa': 'GOO', 'cantidad_acciones': 5, 'valor_compra': 100.00}
    client.post('/', data=data1)
    client.post('/', data=data2)
    
    # Filtrar por rango de fechas
    response = client.get('/historial?fecha_inicio=2024-11-29&fecha_fin=2024-11-29')
    assert response.status_code == 200
    assert b"AAPL" in response.data  # Debe incluir solo el registro de AAPL
    assert b"GOO" not in response.data

def test_historial_compras_sin_registros(client):
    """Criterio de aceptación: HU2.9"""
    response = client.get('/historial?fecha_inicio=2024-11-01&fecha_fin=2024-11-15')
    assert response.status_code == 200
    assert b"No hay datos disponibles para el rango seleccionado." in response.data

@patch("api.obtener_precio_actual", return_value=155.00)
def test_calculos_ganancia_perdida(mock_precio, client):
    """Criterios de aceptación: HU2.4 - HU2.6"""
    data = {'fecha_compra': '2024-11-30', 'empresa': 'AAPL', 'cantidad_acciones': 10, 'valor_compra': 150.00}
    client.post('/', data=data)
    response = client.get('/historial')
    
    # Comprobar que los cálculos son correctos
    assert b"1550.00" in response.data  # Valor actual total
    assert b"50.00" in response.data  # Ganancia en dólares
    assert b"3.33%" in response.data  # Porcentaje de ganancia
