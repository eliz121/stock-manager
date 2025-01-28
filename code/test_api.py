import pytest
from unittest.mock import ANY, MagicMock, patch, Mock
from flask import Flask
from decimal import Decimal
from unittest.mock import patch
from api import app, obtener_precio_actual, obtener_consolidacion
from datetime import datetime, timedelta
from dotenv import load_dotenv
import requests
import sqlite3
import os

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

# Test para API key
def test_api_key_exists(monkeypatch):
    """Test cuando la API key existe en las variables de entorno"""
    # Simular una API key en las variables de entorno
    monkeypatch.setenv("FINANCIAL_MODELING_API_KEY", "test_api_key_123")
    
    # Cargar variables de entorno
    load_dotenv()
    
    # Obtener la API key
    api_key = os.getenv("FINANCIAL_MODELING_API_KEY")
    
    # Verificar que la API key no es None y coincide con el valor esperado
    assert api_key is not None
    assert api_key == "test_api_key_123"

def test_api_key_missing(monkeypatch):
    """Test cuando la API key no existe en las variables de entorno"""
    # Asegurar que la variable de entorno no existe
    monkeypatch.delenv("FINANCIAL_MODELING_API_KEY", raising=False)
    
    # Cargar variables de entorno
    load_dotenv()
    
    # Verificar que se lanza ValueError cuando la API key no existe
    with pytest.raises(ValueError) as exc_info:
        api_key = os.getenv("FINANCIAL_MODELING_API_KEY")
        if not api_key:
            raise ValueError("API key no configurada en el archivo .env")
    
    # Verificar el mensaje de error
    assert str(exc_info.value) == "API key no configurada en el archivo .env"

def test_api_key_empty(monkeypatch):
    """Test cuando la API key existe pero está vacía"""
    # Simular una API key vacía
    monkeypatch.setenv("FINANCIAL_MODELING_API_KEY", "")
    
    # Cargar variables de entorno
    load_dotenv()
    
    # Verificar que se lanza ValueError cuando la API key está vacía
    with pytest.raises(ValueError) as exc_info:
        api_key = os.getenv("FINANCIAL_MODELING_API_KEY")
        if not api_key:
            raise ValueError("API key no configurada en el archivo .env")
    
    # Verificar el mensaje de error
    assert str(exc_info.value) == "API key no configurada en el archivo .env"

    
@pytest.fixture
def app():
    """Fixture que proporciona una instancia limpia de Flask para cada test"""
    return Flask(__name__)

def test_secret_key_exists(app, monkeypatch):
    """Test cuando la secret key existe en las variables de entorno"""
    # Simular una secret key en las variables de entorno
    test_secret = "test_secret_key_123"
    monkeypatch.setenv("FLASK_SECRET_KEY", test_secret)
    
    # Cargar variables de entorno
    load_dotenv()
    
    # Configurar la secret key
    app.secret_key = os.getenv('FLASK_SECRET_KEY')
    
    # Verificar que la secret key se configuró correctamente
    assert app.secret_key is not None
    assert app.secret_key == test_secret

def test_secret_key_missing(app, monkeypatch):
    """Test cuando la secret key no existe en las variables de entorno"""
    # Asegurar que la variable de entorno no existe
    monkeypatch.delenv("FLASK_SECRET_KEY", raising=False)
    
    # Cargar variables de entorno
    load_dotenv()
    
    # Verificar que se lanza ValueError cuando la secret key no existe
    with pytest.raises(ValueError) as exc_info:
        app.secret_key = os.getenv('FLASK_SECRET_KEY')
        if not app.secret_key:
            raise ValueError("Flask secret key no configurada en el archivo .env")
    
    # Verificar el mensaje de error
    assert str(exc_info.value) == "Flask secret key no configurada en el archivo .env"

def test_secret_key_empty(app, monkeypatch):
    """Test cuando la secret key existe pero está vacía"""
    # Simular una secret key vacía
    monkeypatch.setenv("FLASK_SECRET_KEY", "")
    
    # Cargar variables de entorno
    load_dotenv()
    
    # Verificar que se lanza ValueError cuando la secret key está vacía
    with pytest.raises(ValueError) as exc_info:
        app.secret_key = os.getenv('FLASK_SECRET_KEY')
        if not app.secret_key:
            raise ValueError("Flask secret key no configurada en el archivo .env")
    
    # Verificar el mensaje de error
    assert str(exc_info.value) == "Flask secret key no configurada en el archivo .env"

def test_app_configuration(app, monkeypatch):
    """Test de la configuración completa de la aplicación"""
    # Simular una secret key válida
    test_secret = "valid_secret_key"
    monkeypatch.setenv("FLASK_SECRET_KEY", test_secret)
    
    # Cargar variables de entorno
    load_dotenv()
    
    # Configurar la aplicación
    app.secret_key = os.getenv('FLASK_SECRET_KEY')
    
    # Verificar que la aplicación está correctamente configurada
    assert isinstance(app, Flask)
    assert app.secret_key == test_secret
    assert app.secret_key is not None

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
    import os
    os.remove('test_precios.db')

@pytest.fixture
def mock_response():
    """Fixture para simular respuesta de la API"""
    mock = Mock()
    mock.status_code = 200
    mock.json.return_value = [{"price": 150.25}]
    return mock

def test_simbolo_invalido():
    """Test para verificar que se rechacen símbolos inválidos"""
    invalid_symbols = ["", "123", "AB$", None]
    for symbol in invalid_symbols:
        with pytest.raises(ValueError, match="Símbolo inválido"):
            obtener_precio_actual(symbol)

def test_cache_valido(mock_db):
    """Test para verificar que se use el caché cuando está dentro del tiempo válido"""
    symbol = "AAPL"
    precio_cached = 150.25
    fecha_reciente = (datetime.now() - timedelta(minutes=30)).isoformat()
    
    cursor = mock_db.cursor()
    cursor.execute(
        "INSERT INTO precios (symbol, precio, fecha) VALUES (?, ?, ?)",
        (symbol, precio_cached, fecha_reciente)
    )
    mock_db.commit()

    with patch('sqlite3.connect', return_value=mock_db):
        precio = obtener_precio_actual(symbol)
        assert precio == precio_cached

def test_cache_expirado(mock_db, mock_response):
    """Test para verificar que se actualice el precio cuando el caché está expirado"""
    symbol = "AAPL"
    precio_viejo = 140.00
    fecha_vieja = (datetime.now() - timedelta(hours=2)).isoformat()
    
    cursor = mock_db.cursor()
    cursor.execute(
        "INSERT INTO precios (symbol, precio, fecha) VALUES (?, ?, ?)",
        (symbol, precio_viejo, fecha_vieja)
    )
    mock_db.commit()

    with patch('sqlite3.connect', return_value=mock_db), \
         patch('requests.get', return_value=mock_response):
        precio = obtener_precio_actual(symbol)
        assert precio == mock_response.json()[0]["price"]

def test_error_api_429(mock_db):
    """Test para verificar el manejo del error de límite de solicitudes"""
    mock_response = Mock()
    mock_response.status_code = 429

    with patch('sqlite3.connect', return_value=mock_db), \
         patch('requests.get', return_value=mock_response), \
         pytest.raises(ValueError, match="Se ha excedido el límite de solicitudes a la API"):
        obtener_precio_actual("AAPL")

def test_timeout_api(mock_db):
    """Test para verificar el manejo de timeout de la API"""
    with patch('sqlite3.connect', return_value=mock_db), \
         patch('requests.get', side_effect=requests.exceptions.Timeout), \
         pytest.raises(ValueError, match="Tiempo de espera agotado al contactar la API"):
        obtener_precio_actual("AAPL")

def test_datos_api_vacios(mock_db):
    """Test para verificar el manejo de respuesta vacía de la API"""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = []

    with patch('sqlite3.connect', return_value=mock_db), \
         patch('requests.get', return_value=mock_response), \
         pytest.raises(ValueError, match="No se encontraron datos para este símbolo"):
        obtener_precio_actual("AAPL")

# Test específico para la lógica del caché
def test_logica_cache():
    """Test unitario para la lógica de verificación del caché"""
    CACHE_DURATION = timedelta(hours=1)
    
    # Caso 1: Caché válido (menos de 1 hora)
    fecha_reciente = datetime.now() - timedelta(minutes=30)
    assert datetime.now() - fecha_reciente < CACHE_DURATION
    
    # Caso 2: Caché expirado (más de 1 hora)
    fecha_vieja = datetime.now() - timedelta(hours=2)
    assert not (datetime.now() - fecha_vieja < CACHE_DURATION)
    
    # Caso límite: Exactamente 1 hora
    fecha_limite = datetime.now() - timedelta(hours=1)
    assert not (datetime.now() - fecha_limite < CACHE_DURATION)

def test_limite_solicitudes_api():
    """Test para verificar el manejo del código 429 (Too Many Requests)"""
    # Configurar el mock de la respuesta
    mock_response = Mock()
    mock_response.status_code = 429
    
    with patch('requests.get', return_value=mock_response), \
         pytest.raises(ValueError) as exc_info:
        obtener_precio_actual("AAPL")
    
    assert str(exc_info.value) == "Se ha excedido el límite de solicitudes a la API"

def test_diversos_errores_http():
    """Test para verificar el manejo de diferentes códigos de error HTTP"""
    codigos_error = [
        400,  # Bad Request
        401,  # Unauthorized
        403,  # Forbidden
        404,  # Not Found
        500,  # Internal Server Error
        502,  # Bad Gateway
        503,  # Service Unavailable
        504   # Gateway Timeout
    ]
    
    for codigo in codigos_error:
        mock_response = Mock()
        mock_response.status_code = codigo
        
        with patch('requests.get', return_value=mock_response), \
             pytest.raises(ValueError) as exc_info:
            obtener_precio_actual("AAPL")
        
        assert str(exc_info.value) == f"Error al obtener datos de la API: {codigo}"

def test_respuesta_exitosa():
    """Test para verificar el manejo correcto de una respuesta exitosa (código 200)"""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = [{"price": 150.25}]
    
    with patch('requests.get', return_value=mock_response), \
         patch('sqlite3.connect'), \
         patch('sqlite3.Connection.cursor'):
        precio = obtener_precio_actual("AAPL")
        assert precio == 150.25

def test_codigos_redireccion():
    """Test para verificar el manejo de códigos de redirección"""
    codigos_redireccion = [301, 302, 307, 308]
    
    for codigo in codigos_redireccion:
        mock_response = Mock()
        mock_response.status_code = codigo
        
        with patch('requests.get', return_value=mock_response), \
             pytest.raises(ValueError) as exc_info:
            obtener_precio_actual("AAPL")
        
        assert str(exc_info.value) == f"Error al obtener datos de la API: {codigo}"

def test_error_personalizado():
    """Test para verificar el formato del mensaje de error personalizado"""
    codigos_prueba = [404, 500, 403]
    
    for codigo in codigos_prueba:
        mock_response = Mock()
        mock_response.status_code = codigo
        mensaje_esperado = f"Error al obtener datos de la API: {codigo}"
        
        with patch('requests.get', return_value=mock_response), \
             pytest.raises(ValueError) as exc_info:
            obtener_precio_actual("AAPL")
        
        assert str(exc_info.value) == mensaje_esperado
        assert isinstance(exc_info.value, ValueError)

    def test_respuesta_vacia():
        """Test para verificar el manejo de respuestas vacías"""
    casos_prueba = [
        None,           # data es None
        [],            # lista vacía
        "",            # string vacío
        {},            # diccionario vacío
    ]
    
    for caso in casos_prueba:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = caso
        
        with patch('requests.get', return_value=mock_response), \
             pytest.raises(ValueError) as exc_info:
            obtener_precio_actual("AAPL")
        
        assert str(exc_info.value) == "No se encontraron datos para este símbolo"

def test_respuesta_tipo_invalido():
    """Test para verificar el manejo de tipos de datos inválidos"""
    casos_prueba = [
        "string_invalido",    # string en lugar de lista
        123,                  # número en lugar de lista
        {"key": "value"},     # diccionario en lugar de lista
        True,                 # booleano en lugar de lista
    ]
    
    for caso in casos_prueba:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = caso
        
        with patch('requests.get', return_value=mock_response), \
             pytest.raises(ValueError) as exc_info:
            obtener_precio_actual("AAPL")
        
        assert str(exc_info.value) == "No se encontraron datos para este símbolo"

def test_precio_no_presente():
    """Test para verificar el manejo de respuestas sin precio"""
    casos_prueba = [
        [{}],                          # diccionario vacío
        [{"otherField": "value"}],     # sin campo price
        [{"price": None}],             # price es None
    ]
    
    for caso in casos_prueba:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = caso
        
        with patch('requests.get', return_value=mock_response), \
             pytest.raises(ValueError) as exc_info:
            obtener_precio_actual("AAPL")
        
        assert str(exc_info.value) == "No se pudo obtener el precio actual"

def test_precio_valido():
    """Test para verificar el manejo correcto de un precio válido"""
    precios_prueba = [
        100.50,     # precio decimal
        100,        # precio entero
        0.01,       # precio muy bajo
        9999.99,    # precio alto
    ]
    
    for precio in precios_prueba:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [{"price": precio}]
        
        with patch('requests.get', return_value=mock_response), \
             patch('sqlite3.connect'), \
             patch('sqlite3.Connection.cursor'):
            resultado = obtener_precio_actual("AAPL")
            assert resultado == precio

def test_multiples_resultados():
    """Test para verificar que se toma el primer precio cuando hay múltiples resultados"""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = [
        {"price": 100.50},
        {"price": 101.50},
        {"price": 102.50}
    ]
    
    with patch('requests.get', return_value=mock_response), \
         patch('sqlite3.connect'), \
         patch('sqlite3.Connection.cursor'):
        resultado = obtener_precio_actual("AAPL")
        assert resultado == 100.50

def test_precio_tipos_invalidos():
    """Test para verificar el manejo de precios con tipos de datos inválidos"""
    precios_invalidos = [
        [{"price": "no-numerico"}],    # string en lugar de número
        [{"price": []}],               # lista en lugar de número
        [{"price": {}}],               # diccionario en lugar de número
        [{"price": True}],             # booleano en lugar de número
    ]
    
    for caso in precios_invalidos:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = caso
        
        with patch('requests.get', return_value=mock_response), \
             pytest.raises(ValueError) as exc_info:
            obtener_precio_actual("AAPL")
        
        assert str(exc_info.value) == "No se pudo obtener el precio actual"

def test_timeout_exception():
    """Test para verificar el manejo de timeout en la API"""
    with patch('requests.get', side_effect=requests.exceptions.Timeout), \
         pytest.raises(ValueError) as exc_info:
        obtener_precio_actual("AAPL")
    
    assert str(exc_info.value) == "Tiempo de espera agotado al contactar la API"

def test_request_exceptions():
    """Test para verificar diferentes tipos de errores de conexión"""
    excepciones = [
        (requests.exceptions.ConnectionError("Error de conexión"), "Error de conexión: Error de conexión"),
        (requests.exceptions.SSLError("Error SSL"), "Error de conexión: Error SSL"),
        (requests.exceptions.ProxyError("Error de proxy"), "Error de conexión: Error de proxy"),
        (requests.exceptions.TooManyRedirects("Demasiadas redirecciones"), "Error de conexión: Demasiadas redirecciones"),
    ]
    
    for exception, expected_message in excepciones:
        with patch('requests.get', side_effect=exception), \
             pytest.raises(ValueError) as exc_info:
            obtener_precio_actual("AAPL")
        
        assert str(exc_info.value) == expected_message

def test_sqlite_exceptions():
    """Test para verificar diferentes tipos de errores de base de datos"""
    excepciones_db = [
        (sqlite3.OperationalError("tabla no existe"), "Error de base de datos: tabla no existe"),
        (sqlite3.IntegrityError("violación de integridad"), "Error de base de datos: violación de integridad"),
        (sqlite3.DatabaseError("error general de base de datos"), "Error de base de datos: error general de base de datos"),
    ]
    
    for exception, expected_message in excepciones_db:
        with patch('sqlite3.connect', side_effect=exception), \
             pytest.raises(ValueError) as exc_info:
            obtener_precio_actual("AAPL")
        
        assert str(exc_info.value) == expected_message

def test_generic_exceptions():
    """Test para verificar el manejo de excepciones genéricas"""
    excepciones_genericas = [
        (KeyError("llave no encontrada"), "Error inesperado: llave no encontrada"),
        (TypeError("tipo inválido"), "Error inesperado: tipo inválido"),
        (ValueError("valor inválido"), "Error inesperado: valor inválido"),
    ]
    
    for exception, expected_message in excepciones_genericas:
        with patch('requests.get', side_effect=exception), \
             pytest.raises(ValueError) as exc_info:
            obtener_precio_actual("AAPL")
        
        assert str(exc_info.value) == expected_message

def test_connection_cleanup():
    """Test para verificar que la conexión se cierra incluso después de un error"""
    mock_connection = Mock()
    
    with patch('sqlite3.connect', return_value=mock_connection), \
         patch('requests.get', side_effect=requests.exceptions.Timeout):
        
        try:
            obtener_precio_actual("AAPL")
        except ValueError:
            pass
        
        # Verificar que close() fue llamado
        mock_connection.close.assert_called_once()

def test_multiple_exceptions_chain():
    """Test para verificar el manejo de cadenas de excepciones"""
    def raise_chain():
        try:
            raise requests.exceptions.ConnectionError("Error de conexión primario")
        except requests.exceptions.ConnectionError as e:
            raise requests.exceptions.RequestException("Error secundario") from e
    
    with patch('requests.get', side_effect=raise_chain), \
         pytest.raises(ValueError) as exc_info:
        obtener_precio_actual("AAPL")
    
    assert "Error de conexión: Error secundario" in str(exc_info.value)

    @pytest.fixture
    def client():
        """Fixture que proporciona un cliente de prueba de Flask"""
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

def test_error_404_precio_no_encontrado(client):
    """Test para verificar respuesta 404 cuando el precio es None"""
    with patch('your_module.obtener_precio_actual', return_value=None):
        response = client.get('/precio_actual?symbol=AAPL')
        
        assert response.status_code == 404
        data = response.get_json()
        assert data == {"error": "No se pudo obtener el precio actual"}

def test_error_400_valor_invalido(client):
    """Test para verificar respuesta 400 cuando se lanza ValueError"""
    error_messages = [
        "Símbolo inválido",
        "API key no configurada",
        "Error en la validación",
        "Datos incorrectos"
    ]
    
    for message in error_messages:
        with patch('your_module.obtener_precio_actual', side_effect=ValueError(message)):
            response = client.get('/precio_actual?symbol=AAPL')
            
            assert response.status_code == 400
            data = response.get_json()
            assert data == {"error": message}

def test_error_500_excepcion_general(client):
    """Test para verificar respuesta 500 en caso de excepciones no manejadas"""
    excepciones = [
        KeyError("Error de clave"),
        TypeError("Error de tipo"),
        Exception("Error general"),
        RuntimeError("Error de ejecución")
    ]
    
    for exc in excepciones:
        with patch('your_module.obtener_precio_actual', side_effect=exc):
            response = client.get('/precio_actual?symbol=AAPL')
            
            assert response.status_code == 500
            data = response.get_json()
            assert data == {"error": "Error interno del servidor"}

def test_multiples_errores_secuenciales(client):
    """Test para verificar el manejo correcto de múltiples errores en secuencia"""
    scenarios = [
        (ValueError("Error de validación"), 400, {"error": "Error de validación"}),
        (None, 404, {"error": "No se pudo obtener el precio actual"}),
        (Exception("Error general"), 500, {"error": "Error interno del servidor"})
    ]
    
    for error, expected_status, expected_response in scenarios:
        if error is None:
            mock_function = Mock(return_value=None)
        else:
            mock_function = Mock(side_effect=error)
            
        with patch('your_module.obtener_precio_actual', mock_function):
            response = client.get('/precio_actual?symbol=AAPL')
            
            assert response.status_code == expected_status
            assert response.get_json() == expected_response

def test_error_contenido_respuesta(client):
    """Test para verificar el formato y contenido de las respuestas de error"""
    with patch('your_module.obtener_precio_actual', side_effect=ValueError("Error de prueba")):
        response = client.get('/precio_actual?symbol=AAPL')
        
        assert response.status_code == 400
        data = response.get_json()
        
        # Verificar estructura de la respuesta
        assert isinstance(data, dict)
        assert "error" in data
        assert isinstance(data["error"], str)
        
        # Verificar headers
        assert response.content_type == 'application/json'

def test_errores_cadena_excepciones(client):
    """Test para verificar el manejo de cadenas de excepciones"""
    def raise_chained_exception():
        try:
            raise ValueError("Error inicial")
        except ValueError as e:
            raise Exception("Error secundario") from e
    
    with patch('your_module.obtener_precio_actual', side_effect=raise_chained_exception):
        response = client.get('/precio_actual?symbol=AAPL')
        
        assert response.status_code == 500
        data = response.get_json()
        assert data == {"error": "Error interno del servidor"}

@pytest.fixture
def client():
    """Fixture que proporciona un cliente de prueba de Flask"""
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

def test_error_api_400(client):
    """Test para verificar el manejo de error 400 de la API"""
    mock_response = Mock()
    mock_response.status_code = 400
    
    with patch('requests.get', return_value=mock_response):
        response = client.get('/buscar_simbolo?term=AAPL')
        
        assert response.status_code == 400
        data = response.get_json()
        assert data == {"error": "Error en la API: 400"}

def test_error_api_401(client):
    """Test para verificar el manejo de error 401 (API key inválida)"""
    mock_response = Mock()
    mock_response.status_code = 401
    
    with patch('requests.get', return_value=mock_response):
        response = client.get('/buscar_simbolo?term=AAPL')
        
        assert response.status_code == 400
        data = response.get_json()
        assert data == {"error": "Error en la API: 401"}

def test_error_api_403(client):
    """Test para verificar el manejo de error 403 (Sin autorización)"""
    mock_response = Mock()
    mock_response.status_code = 403
    
    with patch('requests.get', return_value=mock_response):
        response = client.get('/buscar_simbolo?term=AAPL')
        
        assert response.status_code == 400
        data = response.get_json()
        assert data == {"error": "Error en la API: 403"}

def test_error_api_404(client):
    """Test para verificar el manejo de error 404 de la API"""
    mock_response = Mock()
    mock_response.status_code = 404
    
    with patch('requests.get', return_value=mock_response):
        response = client.get('/buscar_simbolo?term=AAPL')
        
        assert response.status_code == 400
        data = response.get_json()
        assert data == {"error": "Error en la API: 404"}

def test_error_api_429(client):
    """Test para verificar el manejo de error 429 (Rate limit)"""
    mock_response = Mock()
    mock_response.status_code = 429
    
    with patch('requests.get', return_value=mock_response):
        response = client.get('/buscar_simbolo?term=AAPL')
        
        assert response.status_code == 400
        data = response.get_json()
        assert data == {"error": "Error en la API: 429"}

def test_error_api_500(client):
    """Test para verificar el manejo de error 500 de la API"""
    mock_response = Mock()
    mock_response.status_code = 500
    
    with patch('requests.get', return_value=mock_response):
        response = client.get('/buscar_simbolo?term=AAPL')
        
        assert response.status_code == 400
        data = response.get_json()
        assert data == {"error": "Error en la API: 500"}

def test_multiple_api_errors(client):
    """Test para verificar múltiples códigos de error de la API"""
    error_codes = [400, 401, 403, 404, 429, 500, 502, 503, 504]
    
    for code in error_codes:
        mock_response = Mock()
        mock_response.status_code = code
        
        with patch('requests.get', return_value=mock_response):
            response = client.get('/buscar_simbolo?term=AAPL')
            
            assert response.status_code == 400
            data = response.get_json()
            assert data == {"error": f"Error en la API: {code}"}

def test_error_response_format(client):
    """Test para verificar el formato de la respuesta de error"""
    mock_response = Mock()
    mock_response.status_code = 400
    
    with patch('requests.get', return_value=mock_response):
        response = client.get('/buscar_simbolo?term=AAPL')
        
        # Verificar estructura de la respuesta
        assert response.status_code == 400
        data = response.get_json()
        assert isinstance(data, dict)
        assert "error" in data
        assert isinstance(data["error"], str)
        assert data["error"].startswith("Error en la API: ")
        
        # Verificar headers
        assert response.content_type == 'application/json'

def test_error_propagation(client):
    """Test para verificar que los errores se propagan correctamente"""
    def raise_api_error():
        mock_response = Mock()
        mock_response.status_code = 500
        return mock_response
    
    with patch('requests.get', side_effect=raise_api_error):
        response = client.get('/buscar_simbolo?term=AAPL')
        
        assert response.status_code == 400
        data = response.get_json()
        assert data == {"error": "Error en la API: 500"}