import pytest
from unittest.mock import ANY, MagicMock, patch
from flask import Flask
from decimal import Decimal
from unittest.mock import patch
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

@patch('api.sqlite3.connect')
@patch('api.requests.get')
def test_obtener_precio_actual(mock_get, mock_connect):
    # Configuración del mock para la base de datos
    mock_cursor = mock_connect.return_value.cursor.return_value
    mock_cursor.fetchone.return_value = None  # Simula que no hay datos en caché

    # Configuración del mock para requests.get
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = [{"price": 150.75}]
    mock_get.return_value = mock_response

    # Llamada a la función
    precio = obtener_precio_actual("AAPL")

    # Verificación del resultado
    assert precio == 150.75
    mock_cursor.execute.assert_called_with(
        "REPLACE INTO precios (symbol, precio, fecha) VALUES (?, ?, ?)",
        ("AAPL", 150.75, ANY)  # `ANY` para ignorar el timestamp
    )


# Pruebas para la ruta /precio_actual
def test_precio_actual(client):
    with patch('api.obtener_precio_actual', return_value=150.75):
        response = client.get('/precio_actual?symbol=AAPL')
        assert response.status_code == 200
        assert response.json == {"precio_actual": 150.75}

    response = client.get('/precio_actual')
    assert response.status_code == 400
    assert response.json == {"error": "Símbolo no proporcionado"}

# Pruebas para la ruta /buscar_simbolo
@patch('api.requests.get')
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
    with patch('api.obtener_consolidacion', return_value=[]):
        response = client.get('/')
        assert response.status_code == 200

    response = client.post('/', data={"fecha_compra": "2025-01-01", "empresa": "AAPL"})
    assert response.status_code == 302  # Redirección en caso de éxito

    response = client.post('/', data={})
    assert response.status_code == 302

from decimal import Decimal
from unittest.mock import patch

@patch('api.sqlite3.connect')
@patch('api.obtener_precio_actual')
def test_obtener_consolidacion(mock_obtener_precio, mock_connect):
    # Configura los mocks
    mock_cursor = mock_connect.return_value.cursor.return_value
    mock_cursor.fetchall.return_value = [
        ("AAPL", 10, Decimal("1507.50"), Decimal("150.75")),
        ("GOOG", 5, Decimal("14002.50"), Decimal("2800.50"))
    ]
    mock_obtener_precio.side_effect = [Decimal("150.75"), Decimal("2800.50")]

    # Llamada a la función
    consolidacion = obtener_consolidacion()

    # Resultado esperado
    esperado = [
        {
            "accion": "AAPL",
            "cantidad_total": 10,
            "valor_usd_total": Decimal("1507.50"),
            "precio_costo": Decimal("150.75"),
            "precio_actual": Decimal("150.75"),
            "ganancia_perdida": Decimal("0.00"),
            "porcentaje": Decimal("0.00")
        },
        {
            "accion": "GOOG",
            "cantidad_total": 5,
            "valor_usd_total": Decimal("14002.50"),
            "precio_costo": Decimal("2800.50"),
            "precio_actual": Decimal("2800.50"),
            "ganancia_perdida": Decimal("0.00"),
            "porcentaje": Decimal("0.00")
        }
    ]

    assert consolidacion == esperado

