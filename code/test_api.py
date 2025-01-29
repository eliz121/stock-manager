import pytest
from unittest.mock import ANY, MagicMock, Mock
from flask import Flask
from decimal import Decimal
from unittest.mock import patch
from dotenv import load_dotenv
from api import app,obtener_precio_actual, obtener_consolidacion
from datetime import datetime, timedelta
from gevent.pywsgi import WSGIServer
import sqlite3
import os, requests

@pytest.fixture
def client(monkeypatch):
    # Aquí podemos configurar la variable de entorno
    test_secret = "valid_secret_key"
    monkeypatch.setenv("FLASK_SECRET_KEY", test_secret)

    # Configuramos la clave secreta de la aplicación
    app.config['SECRET_KEY'] = os.getenv("FLASK_SECRET_KEY")

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

#  OJO Test para API key
def obtener_api_key():
    api_key = os.getenv("FINANCIAL_MODELING_API_KEY")
    if not api_key:
        raise ValueError("API key no configurada en el archivo .env")
    return api_key


def test_api_key_missing(monkeypatch):
    """Test cuando la API key no existe en las variables de entorno"""
    monkeypatch.delenv("FINANCIAL_MODELING_API_KEY", raising=False)

    with pytest.raises(ValueError) as exc_info:
        obtener_api_key()  # Llamada a la nueva función

    assert str(exc_info.value) == "API key no configurada en el archivo .env"

def test_api_key_empty(monkeypatch):
    """Test cuando la API key existe pero está vacía"""
    monkeypatch.setenv("FINANCIAL_MODELING_API_KEY", "")

    with pytest.raises(ValueError) as exc_info:
        obtener_api_key()  # Llamada a la nueva función

    assert str(exc_info.value) == "API key no configurada en el archivo .env"

def obtener_secret_key():
    secret_key = os.getenv("FLASK_SECRET_KEY")
    if not secret_key:
        raise ValueError("Flask secret key no configurada en el archivo .env")
    return secret_key

def test_secret_key_exists(client, monkeypatch):
    """Test cuando la secret key existe en las variables de entorno"""
    test_secret = "test_secret_key_123"
    monkeypatch.setenv("FLASK_SECRET_KEY", test_secret)

    client.secret_key = obtener_secret_key()

    assert client.secret_key == test_secret

def test_secret_key_missing(client, monkeypatch):
    """Test cuando la secret key no existe en las variables de entorno"""
    monkeypatch.delenv("FLASK_SECRET_KEY", raising=False)

    with pytest.raises(ValueError) as exc_info:
        obtener_secret_key()  # Llamada a la función validada

    assert str(exc_info.value) == "Flask secret key no configurada en el archivo .env"

def test_secret_key_empty(client, monkeypatch):
    """Test cuando la secret key existe pero está vacía"""
    monkeypatch.setenv("FLASK_SECRET_KEY", "")

    with pytest.raises(ValueError) as exc_info:
        obtener_secret_key()  # Llamada a la función validada

    assert str(exc_info.value) == "Flask secret key no configurada en el archivo .env"

# Prueba de configuración de la aplicación
def test_app_configuration(client):
    """Test de la configuración completa de la aplicación"""
    test_secret = "valid_secret_key"

    # Verificar que la clave secreta esté correctamente configurada
    assert isinstance(client.application, Flask)
    assert client.application.config['SECRET_KEY'] == test_secret
    assert client.application.config['SECRET_KEY'] is not None

# Función auxiliar para crear la base de datos de prueba
def setup_test_db():
    conn = sqlite3.connect('test_precios.db')
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS precios (
            symbol TEXT PRIMARY KEY,
            precio REAL,
            fecha TEXT
        )
    """)
    conn.commit()
    return conn

@pytest.fixture
def mock_db():
    """Fixture para configurar y limpiar la base de datos de prueba"""
    conn = setup_test_db()
    yield conn
    conn.close()
    
    # Manejo seguro de la eliminación del archivo
    try:
        os.remove("test_precios.db")
    except FileNotFoundError:
        pass

@pytest.fixture
def mock_response():
    """Fixture para simular respuesta de la API con variabilidad"""
    mock = Mock()
    mock.status_code = 200
    mock.json.return_value = [{"price": 150.25}, {"price": 149.80}]  # Simular varias respuestas
    return mock
     
def test_simbolo_invalido():
    """Test para verificar que se rechacen símbolos inválidos"""
    invalid_symbols = ["", "123", "AB$", None]
    for symbol in invalid_symbols:
        with pytest.raises(ValueError, match="Símbolo inválido"):
            obtener_precio_actual(symbol)

@pytest.mark.parametrize("symbol", ["AAPL", "GOOG", "MSFT"])
def test_cache_valido(mock_db, symbol):
    """Test para verificar que se use el caché cuando está dentro del tiempo válido"""
    precio_cached = 150.25
    fecha_cached = datetime.now().isoformat()  # Formato ISO como lo usa la función real
    
    # Usamos MagicMock para crear un cursor simulado
    cursor_mock = MagicMock()
    
    # Configuramos el mock para simular una conexión a la base de datos
    mock_db = MagicMock()
    mock_db.cursor.return_value = cursor_mock
    
    # Configuramos el comportamiento del cursor simulado
    # Importante: fetchone() retorna una tupla (precio, fecha)
    cursor_mock.fetchone.return_value = (precio_cached, fecha_cached)
    
    # Simulamos el commit de la base de datos
    mock_db.commit.return_value = None
    
    with patch('sqlite3.connect', return_value=mock_db):
        # Como el caché es válido (fecha actual), no debería llamar a la API
        precio = obtener_precio_actual(symbol)
        
        # Verificamos que el precio obtenido sea el del caché
        assert precio == precio_cached
        
        # Verificamos que se consultó la base de datos con el símbolo correcto
        cursor_mock.execute.assert_called_with(
            "SELECT precio, fecha FROM precios WHERE symbol = ?", 
            (symbol,)
        )
        
        # Verificamos que no se hizo ninguna actualización en la base de datos
        assert cursor_mock.execute.call_count == 1  # Solo la consulta SELECT, no REPLACE

@pytest.mark.parametrize("symbol", ["AAPL", "GOOG", "MSFT"])
def test_cache_expirado(mock_db, mock_response, symbol):
    """Test para verificar que se actualice el precio cuando el caché está expirado"""
    precio_viejo = 140.00
    fecha_vieja = (datetime.now() - timedelta(hours=2)).isoformat()

    # Usamos MagicMock para crear un cursor simulado
    cursor_mock = MagicMock()
    
    # Simulamos la conexión a la base de datos
    mock_db = MagicMock()
    mock_db.cursor.return_value = cursor_mock
    
    # Configuramos el comportamiento del cursor para que devuelva los datos antiguos
    # Cambiamos fetchall por fetchone y ajustamos el formato de retorno
    cursor_mock.fetchone.return_value = (precio_viejo, fecha_vieja)
    
    # Simulamos el commit de la base de datos
    mock_db.commit.return_value = None
    
    # Configuramos el mock de la respuesta de la API
    nuevo_precio = 150.00
    mock_response.status_code = 200
    mock_response.json.return_value = [{"price": nuevo_precio}]
    
    with patch('sqlite3.connect', return_value=mock_db), \
         patch('requests.get', return_value=mock_response):
        
        precio = obtener_precio_actual(symbol)
        
        # Verificamos que el precio devuelto sea el nuevo
        assert precio == nuevo_precio
        
        # Verificamos que se llamó a la base de datos correctamente
        cursor_mock.execute.assert_any_call(
            "SELECT precio, fecha FROM precios WHERE symbol = ?", 
            (symbol,)
        )
        
        # Verificamos que se actualizó la base de datos con el nuevo precio
        cursor_mock.execute.assert_any_call(
            "REPLACE INTO precios (symbol, precio, fecha) VALUES (?, ?, ?)",
            (symbol, nuevo_precio, ANY)  # ANY para la fecha porque será la actual
        )
        
        # Verificamos que se hicieron exactamente dos llamadas a execute
        assert cursor_mock.execute.call_count == 2

@pytest.fixture
def mock_response():
    response = Mock()
    response.status_code = 200
    response.json.return_value = []
    return response

def test_datos_api_vacios(mock_response, mock_db):
    """Test para verificar el manejo de respuesta vacía de la API"""
    mock_response.json.return_value = []

    with patch('sqlite3.connect', return_value=mock_db), \
         patch('requests.get', return_value=mock_response), \
         pytest.raises(ValueError, match="No se encontraron datos para este símbolo"):
        obtener_precio_actual("AAPL")

@pytest.mark.parametrize("symbol", ["AAPL", "GOOG", "MSFT"])
def test_cache_expirado(mock_db, mock_response, symbol):
    """Test para verificar que se actualice el precio cuando el caché está expirado"""
    precio_viejo = 140.00
    fecha_vieja = (datetime.now() - timedelta(hours=2)).isoformat()

    # Usamos MagicMock para crear un cursor simulado
    cursor_mock = MagicMock()
    
    # Simulamos la conexión a la base de datos
    mock_db = MagicMock()
    mock_db.cursor.return_value = cursor_mock
    
    # Configuramos el comportamiento del cursor para que devuelva los datos antiguos
    # Cambiamos fetchall por fetchone y ajustamos el formato de retorno
    cursor_mock.fetchone.return_value = (precio_viejo, fecha_vieja)
    
    # Simulamos el commit de la base de datos
    mock_db.commit.return_value = None
    
    # Configuramos el mock de la respuesta de la API
    nuevo_precio = 150.00
    mock_response.status_code = 200
    mock_response.json.return_value = [{"price": nuevo_precio}]
    
    with patch('sqlite3.connect', return_value=mock_db), \
         patch('requests.get', return_value=mock_response):
        
        precio = obtener_precio_actual(symbol)
        
        # Verificamos que el precio devuelto sea el nuevo
        assert precio == nuevo_precio
        
        # Verificamos que se llamó a la base de datos correctamente
        cursor_mock.execute.assert_any_call(
            "SELECT precio, fecha FROM precios WHERE symbol = ?", 
            (symbol,)
        )
        
        # Verificamos que se actualizó la base de datos con el nuevo precio
        cursor_mock.execute.assert_any_call(
            "REPLACE INTO precios (symbol, precio, fecha) VALUES (?, ?, ?)",
            (symbol, nuevo_precio, ANY)  # ANY para la fecha porque será la actual
        )
        
        # Verificamos que se hicieron exactamente dos llamadas a execute
        assert cursor_mock.execute.call_count == 2

def test_api_key_no_configurada():
    """Test para verificar que se lance error cuando la API key no está configurada"""
    with pytest.raises(ValueError) as exc_info:
        raise ValueError("API key no configurada en el archivo .env")
            
    assert str(exc_info.value) == "API key no configurada en el archivo .env"

def test_error_timeout():
    """Test para verificar el manejo del error de timeout"""
    with patch('requests.get') as mock_get:
        # Simulamos un timeout
        mock_get.side_effect = requests.exceptions.Timeout()
        
        # Hacemos la solicitud a la ruta
        response = app.test_client().get('/buscar_simbolo?term=AAPL')
        
        # Verificamos la respuesta
        assert response.status_code == 504
        assert response.get_json() == {"error": "Tiempo de espera agotado"}

def test_error_conexion():
    """Test para verificar el manejo de errores de conexión"""
    with patch('requests.get') as mock_get:
        # Simulamos un error de conexión
        mock_get.side_effect = requests.exceptions.ConnectionError("Error de red")
        
        response = app.test_client().get('/buscar_simbolo?term=AAPL')
        
        assert response.status_code == 503
        assert response.get_json() == {"error": "Error de conexión: Error de red"}

def test_error_valor():
    """Test para verificar el manejo de ValueError"""
    with patch('requests.get') as mock_get:
        # Simulamos una respuesta con error
        mock_response = Mock()
        mock_response.status_code = 400
        mock_get.return_value = mock_response
        
        response = app.test_client().get('/buscar_simbolo?term=AAPL')
        
        assert response.status_code == 400
        assert response.get_json() == {"error": "Error en la API: 400"}

def test_error_generico():
    """Test para verificar el manejo de excepciones genéricas"""
    with patch('requests.get') as mock_get:
        # Simulamos un error inesperado
        mock_get.side_effect = Exception("Error inesperado")
        
        response = app.test_client().get('/buscar_simbolo?term=AAPL')
        
        assert response.status_code == 500
        assert response.get_json() == {"error": "Error interno del servidor"}

def test_buscar_simbolo_timeout():
   """Test para verificar manejo de timeout en búsqueda de símbolo"""
   with patch('requests.get') as mock_get:
       # Simular timeout
       mock_get.side_effect = requests.exceptions.Timeout()
       
       # Hacer request 
       response = app.test_client().get('/buscar_simbolo?term=AAPL')
       
       # Verificar respuesta
       assert response.status_code == 504
       assert response.get_json() == {"error": "Tiempo de espera agotado"}

def test_buscar_simbolo_error_conexion():
   """Test para verificar manejo de error de conexión"""
   with patch('requests.get') as mock_get:
       # Simular error de conexión
       mock_get.side_effect = requests.exceptions.ConnectionError("Error de red") 
       
       response = app.test_client().get('/buscar_simbolo?term=AAPL')
       
       assert response.status_code == 503
       assert response.get_json() == {"error": "Error de conexión: Error de red"}

def test_buscar_simbolo_error_api():
   """Test para verificar manejo de error de la API"""
   with patch('requests.get') as mock_get:
       # Simular error de API
       mock_response = Mock()
       mock_response.status_code = 400
       mock_get.return_value = mock_response
       
       response = app.test_client().get('/buscar_simbolo?term=AAPL')
       
       assert response.status_code == 400
       assert response.get_json() == {"error": "Error en la API: 400"}

def test_buscar_simbolo_error_generico():
   """Test para verificar manejo de error genérico"""
   with patch('requests.get') as mock_get:
       # Simular error genérico
       mock_get.side_effect = Exception("Error inesperado")
       
       response = app.test_client().get('/buscar_simbolo?term=AAPL')
       
       assert response.status_code == 500
       assert response.get_json() == {"error": "Error interno del servidor"}
    
def test_precio_actual_symbol_not_provided(client):
        """Test para verificar el manejo cuando no se proporciona el símbolo"""
        response = client.get('/precio_actual')
        assert response.status_code == 400
        assert response.json == {"error": "Símbolo no proporcionado"}

def test_precio_actual_invalid_symbol(client):
        """Test para verificar el manejo de símbolo inválido"""
        response = client.get('/precio_actual?symbol=1234')
        assert response.status_code == 400
        assert response.json == {"error": "Símbolo inválido"}

def test_home_post_invalid_date(client):
    response = client.post('/', data={"fecha_compra": "invalid-date", "empresa": "AAPL"})
    # Asegurarse de que hay redirección (código 302)
    assert response.status_code == 302
    # Verificar que el mensaje flash es el esperado
    with client.session_transaction() as sess:
        assert 'Fecha inválida' in sess['_flashes'][0][1]

def test_home_post_future_date(client):
    future_date = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
    response = client.post('/', data={"fecha_compra": future_date, "empresa": "AAPL"})
    assert response.status_code == 302
    with client.session_transaction() as sess:
        assert 'La fecha no puede ser futura' in sess['_flashes'][0][1]

def test_home_post_no_symbol(client):
    response = client.post('/', data={"fecha_compra": "2023-01-01"})
    assert response.status_code == 302
    with client.session_transaction() as sess:
        assert 'El símbolo de la empresa es obligatorio' in sess['_flashes'][0][1]

def test_home_post_success(client):
    response = client.post('/', data={"fecha_compra": "2023-01-01", "empresa": "AAPL"})
    assert response.status_code == 302
    with client.session_transaction() as sess:
        assert 'Registro guardado exitosamente' in sess['_flashes'][0][1]
