import math
import threading
from contextlib import contextmanager
from typing import List
from psycopg2 import sql
from psycopg2.extras import RealDictCursor
from psycopg2.pool import ThreadedConnectionPool
from .base import BaseConnector
from ..models import GatewayKnowledgeItem
from ..config import SQLConfig


class SQLConnector(BaseConnector):
    """Read-only PostgreSQL retrieval with bounded connections and quoted identifiers."""

    def __init__(self, config: SQLConfig):
        super().__init__('sql_postgres_db', 'sql', config.enabled)
        self.config = config
        self.is_connected = False
        self._pool = None
        self._pool_lock = threading.Lock()

    def _get_connection(self):
        with self._pool_lock:
            if self._pool is None:
                self._pool = ThreadedConnectionPool(
                    1, 4, host=self.config.host, port=self.config.port,
                    dbname=self.config.database, user=self.config.username,
                    password=self.config.password,
                    connect_timeout=math.ceil(self.config.timeout_seconds),
                    options=f'-c statement_timeout={int(self.config.timeout_seconds * 1000)} -c default_transaction_read_only=on',
                    application_name='knowledge-gateway',
                )
            return self._pool.getconn()

    @contextmanager
    def connection(self):
        conn = self._get_connection()
        try:
            yield conn
        finally:
            try:
                if not conn.closed:
                    conn.rollback()
            finally:
                self._pool.putconn(conn, close=bool(conn.closed))

    async def search(self, query, tags, top_k=None):
        return await self.run_blocking(self._search_sync, query, tags, top_k)

    def _search_sync(self, query: str, tags: List[str], top_k=None):
        if not self.enabled or not self.config.tables:
            return []
        words = [w for w in query.split() if len(w) > 2] or [query.strip()]
        words = words[:64]
        limit = top_k or self.config.max_results
        items = []
        try:
            with self.connection() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
                for table in self.config.tables:
                    clauses, params = [], []
                    for col in table.search_columns:
                        for word in words:
                            clauses.append(sql.SQL('CAST({} AS TEXT) ILIKE %s').format(sql.Identifier(col)))
                            literal = word.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
                            params.append('%' + literal + '%')
                    if not clauses:
                        continue
                    statement = sql.SQL('SELECT * FROM {} WHERE {} ORDER BY {} LIMIT %s').format(
                        sql.Identifier(*table.table_name.split('.')),
                        sql.SQL(' OR ').join(clauses), sql.Identifier(table.id_column),
                    )
                    cur.execute(statement, (*params, limit))
                    for row in cur.fetchall():
                        row_id = str(row.get(table.id_column, 'unknown'))
                        title = str(row.get(table.title_column, row_id))
                        content = str(row.get(table.content_column) or '')
                        raw_tags = row.get('tags') or []
                        if isinstance(raw_tags, str):
                            raw_tags = [v.strip() for v in raw_tags.split(',')]
                        hits = sum(w.lower() in (title + ' ' + content).lower() for w in words)
                        items.append(GatewayKnowledgeItem(
                            id=f'sql_{table.table_name}_{row_id}', source_type='sql', title=title,
                            content=content[:262144], snippet=content[:200],
                            raw_score=min(0.95, 0.5 + 0.15 * hits),
                            provenance={'connector': self.name, 'database': self.config.database,
                                        'table': table.table_name, 'row_id': row_id},
                            metadata={'category': row.get('category', 'database_record'), 'tags': raw_tags},
                        ))
            self.is_connected = True
        except Exception:
            self.is_connected = False
            raise
        return sorted(items, key=lambda item: (-item.raw_score, item.id))[:limit]

    async def health_check(self):
        return await self.run_blocking(self._health_sync)

    def _health_sync(self):
        if not self.enabled:
            return {'status': 'disabled', 'connector': self.name}
        try:
            with self.connection() as conn, conn.cursor() as cur:
                cur.execute('SELECT 1')
                tables = {}
                for table in self.config.tables:
                    # Cheap existence check: no full-table COUNT(*) on a health endpoint.
                    cur.execute(sql.SQL('SELECT 1 FROM {} LIMIT 1').format(sql.Identifier(*table.table_name.split('.'))))
                    tables[table.table_name] = 'available'
            self.is_connected = True
            return {'status': 'healthy', 'connector': self.name, 'database': self.config.database, 'tables': tables}
        except Exception as exc:
            self.is_connected = False
            return {'status': 'unreachable', 'connector': self.name, 'error': type(exc).__name__}

    async def aclose(self):
        await super().aclose()
        if self._pool:
            self._pool.closeall()
