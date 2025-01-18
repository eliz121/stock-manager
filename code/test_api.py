import pytest
import requests
from unittest.mock import patch
from flask import Flask
from api import app, obtener_precio_actual, obtener_consolidacion

@pytest.fixture
def client():
    with app.test_client() as client:
        yield client

# Pruebas para el filtro 'format_number'
def test_format_number():
    with app.app_context():
        assert app.jinja_env.filters['format_number'](1234567.89) == '1,234,567.89'
        assert app.jinja_env.filters['format_number'](None) == '0.00'
        assert app.jinja_env.filters['format_number']('invalid') == '0.00'

# Pruebas para obtener_precio_actual
@patch('app.sqlite3.connect')
@patch('app.requests.get')
def test_obtener_precio_actual(mock_get, mock_connect):
    mock_cursor = mock_connect.return_value.cursor.return_value

    # Caso: Precio en caché
    mock_cursor.fetchone.return_value = (100.50, '2025-01-17T10:00:00')
    precio = obtener_precio_actual("AAPL")
    assert precio == 100.50

    # Caso: Precio no en caché y éxito de la API
    mock_cursor.fetchone.return_value = None
    mock_get.return_value.status_code = 200
    mock_get.return_value.json.return_value = [{"price": 150.75}]
    precio = obtener_precio_actual("AAPL")
    assert precio == 150.75

    # Caso: Límite de solicitudes de la API
    mock_get.return_value.status_code = 429
    with pytest.raises(ValueError, match="Se ha excedido el límite de solicitudes a la API"):
        obtener_precio_actual("AAPL")

    # Caso: Error de conexión
    mock_get.side_effect = requests.exceptions.ConnectionError
    with pytest.raises(ValueError, match="Error de conexión"):
        obtener_precio_actual("AAPL")

# Pruebas para la ruta /precio_actual
def test_precio_actual(client):
    with patch('app.obtener_precio_actual', return_value=150.75):
        response = client.get('/precio_actual?symbol=AAPL')
        assert response.status_code == 200
        assert response.json == {"precio_actual": 150.75}

    response = client.get('/precio_actual')
    assert response.status_code == 400
    assert response.json == {"error": "Símbolo no proporcionado"}

# Pruebas para la ruta /buscar_simbolo
@patch('app.requests.get')
def test_buscar_simbolo(mock_get, client):
    mock_get.return_value.status_code = 200
    mock_get.return_value.json.return_value = [
        {"symbol": "AAPL", "name": "Apple Inc."},
        {"symbol": "MSFT", "name": "Microsoft Corporation"}
    ]

    response = client.get('/buscar_simbolo?term=AP')
    assert response.status_code == 200
    assert response.json == {
        "simbolos": [
            {"symbol": "AAPL", "nombre": "Apple Inc. (AAPL)"},
            {"symbol": "MSFT", "nombre": "Microsoft Corporation (MSFT)"}
        ]
    }

    response = client.get('/buscar_simbolo?term=A')
    assert response.status_code == 200
    assert response.json == {"simbolos": []}

# Pruebas para la ruta principal
def test_home(client):
    with patch('app.obtener_consolidacion', return_value=[]):
        response = client.get('/')
        assert response.status_code == 200

    response = client.post('/', data={"fecha_compra": "2025-01-01", "empresa": "AAPL"})
    assert response.status_code == 302  # Redirección en caso de éxito

    response = client.post('/', data={})
    assert response.status_code == 302

# Pruebas para obtener_consolidacion
@patch('app.sqlite3.connect')
@patch('app.obtener_precio_actual', return_value=150.75)
def test_obtener_consolidacion(mock_precio_actual, mock_connect):
    mock_cursor = mock_connect.return_value.cursor.return_value
    mock_cursor.fetchall.return_value = [
        ("AAPL", 10, 1000.00, 100.00)
    ]

    consolidacion = obtener_consolidacion()
    assert len(consolidacion) == 1
    assert consolidacion[0]['accion'] == "AAPL"
    assert consolidacion[0]['ganancia_perdida'] == 507.50
    assert consolidacion[0]['porcentaje'] == 50.75

