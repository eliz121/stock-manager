import unittest
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta
import sqlite3
import json
from api import app, obtener_precio_actual, obtener_historial_compras, obtener_consolidacion

TEST_DB = ':memory:'

class TestFlaskApp(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        self.client = app.test_client()
        
        # Create in-memory test database
        self.conn = sqlite3.connect(TEST_DB)
        self.cursor = self.conn.cursor()
        
        # Create required tables
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS precios (
                symbol TEXT PRIMARY KEY,
                precio REAL,
                fecha TEXT
            )
        ''')
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS historial_compras (
                fecha_compra TEXT,
                symbol TEXT,
                cantidad_acciones INTEGER,
                valor_compra REAL,
                precio_actual REAL,
                valor_total REAL,
                valor_actual REAL,
                ganancia_perdida REAL,
                porcentaje REAL
            )
        ''')
        self.conn.commit()

    def tearDown(self):
        self.conn.close()

    @patch('requests.get')
    def test_obtener_precio_actual_success(self, mock_get):
        # Mock successful API response
        MOCK_PRICE = 150.50
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [{"price": MOCK_PRICE}]
        mock_get.return_value = mock_response

        precio = obtener_precio_actual("AAPL")
        self.assertEqual(precio, MOCK_PRICE)
        mock_get.assert_called_once()

    @patch('requests.get')
    def test_obtener_precio_actual_cached(self, mock_get):
        # Insert cached price
        CACHED_PRICE = 160.75
        self.cursor.execute(
            "INSERT INTO precios (symbol, precio, fecha) VALUES (?, ?, ?)",
            ("AAPL", CACHED_PRICE, datetime.now().isoformat())
        )
        self.conn.commit()

        precio = obtener_precio_actual("AAPL")
        self.assertEqual(precio, CACHED_PRICE)
        mock_get.assert_not_called()

    def test_obtener_precio_actual_invalid_symbol(self):
        with self.assertRaises(ValueError):
            obtener_precio_actual("123")

    @patch('requests.get')
    def test_precio_actual_endpoint(self, mock_get):
        MOCK_PRICE = 150.50
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [{"price": MOCK_PRICE}]
        mock_get.return_value = mock_response

        response = self.client.get('/precio_actual?symbol=AAPL')
        data = json.loads(response.data)
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(data["precio_actual"], MOCK_PRICE)

    def test_precio_actual_endpoint_no_symbol(self):
        response = self.client.get('/precio_actual')
        self.assertEqual(response.status_code, 400)
        self.assertIn(b'Error', response.data)

    @patch('requests.get')
    def test_buscar_simbolo_success(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"symbol": "AAPL", "name": "Apple Inc"}
        ]
        mock_get.return_value = mock_response

        response = self.client.get('/buscar_simbolo?term=AAPL')
        data = json.loads(response.data)
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(data["simbolos"]), 1)
        self.assertEqual(data["simbolos"][0]["symbol"], "AAPL")

    def test_obtener_historial_compras(self):
        self.cursor.execute('''
            INSERT INTO historial_compras 
            (fecha_compra, symbol, cantidad_acciones, valor_compra, precio_actual,
             valor_total, valor_actual, ganancia_perdida, porcentaje)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            datetime.now().isoformat(),
            "AAPL",
            10,
            150.0,
            160.0,
            1500.0,
            1600.0,
            100.0,
            6.67
        ))
        self.conn.commit()

        historial = obtener_historial_compras()
        self.assertEqual(len(historial), 1)
        self.assertEqual(historial[0]["symbol"], "AAPL")

    def test_obtener_consolidacion(self):
        self.cursor.execute('''
            INSERT INTO historial_compras 
            (fecha_compra, symbol, cantidad_acciones, valor_compra, precio_actual,
             valor_total, valor_actual, ganancia_perdida, porcentaje)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            datetime.now().isoformat(),
            "AAPL",
            10,
            150.0,
            160.0,
            1500.0,
            1600.0,
            100.0,
            6.67
        ))
        self.conn.commit()

        with patch('app.obtener_precio_actual') as mock_precio:
            MOCK_NEW_PRICE = 170.0
            mock_precio.return_value = MOCK_NEW_PRICE

            consolidacion = obtener_consolidacion()
            self.assertEqual(len(consolidacion), 1)
            self.assertEqual(consolidacion[0]["accion"], "AAPL")
            self.assertEqual(float(consolidacion[0]["cantidad_total"]), 10)

    def test_format_number_filter(self):
        with app.app_context():
            self.assertEqual(app.jinja_env.filters['format_number'](1234.56), "1,234.56")
            self.assertEqual(app.jinja_env.filters['format_number'](None), "0.00")
            self.assertEqual(app.jinja_env.filters['format_number']("invalid"), "0.00")

if __name__ == '__main__':
    unittest.main()
