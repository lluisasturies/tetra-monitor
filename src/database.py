import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime

class Database:
    def __init__(self, host, port, user, password, dbname):
        self.conn = psycopg2.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            dbname=dbname
        )
        self._create_tables()

    def _create_tables(self):
        with self.conn.cursor() as cur:
            cur.execute('''
            CREATE TABLE IF NOT EXISTS eventos (
                id SERIAL PRIMARY KEY,
                timestamp TIMESTAMP,
                grupo INTEGER,
                ssi INTEGER,
                texto TEXT,
                ruta_audio TEXT
            )
            ''')
            self.conn.commit()

    def guardar_evento(self, grupo, ssi, texto, ruta_audio):
        with self.conn.cursor() as cur:
            cur.execute('''
            INSERT INTO eventos (timestamp, grupo, ssi, texto, ruta_audio)
            VALUES (%s, %s, %s, %s, %s)
            ''', (datetime.now(), grupo, ssi, texto, ruta_audio))
            self.conn.commit()

    def listar_eventos(self, limit=100):
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute('SELECT * FROM eventos ORDER BY timestamp DESC LIMIT %s', (limit,))
            return cur.fetchall()