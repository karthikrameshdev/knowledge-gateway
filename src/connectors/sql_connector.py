import logging
from typing import List, Dict, Any, Optional
import psycopg2
from psycopg2.extras import RealDictCursor

from .base import BaseConnector
from ..models import GatewayKnowledgeItem
from ..config import SQLConfig

logger = logging.getLogger("SQLConnector")


class SQLConnector(BaseConnector):
    """PostgreSQL relational database connector for WeftKit and enterprise SQL stores."""

    def __init__(self, config: SQLConfig):
        super().__init__(name="sql_postgres_db", source_type="sql", enabled=config.enabled)
        self.config = config
        self.is_connected = False
        self._test_connection()

    def _get_connection(self):
        return psycopg2.connect(
            host=self.config.host,
            port=self.config.port,
            dbname=self.config.database,
            user=self.config.username,
            password=self.config.password,
            connect_timeout=int(self.config.timeout_seconds),
        )

    def _test_connection(self):
        if not self.enabled:
            return
        try:
            conn = self._get_connection()
            conn.close()
            self.is_connected = True
            logger.info("Connected to PostgreSQL at %s:%s/%s", self.config.host, self.config.port, self.config.database)
        except Exception as e:
            logger.warning("Could not connect to PostgreSQL at %s:%s: %s", self.config.host, self.config.port, e)
            self.is_connected = False

    async def search(
        self,
        query: str,
        tags: List[str],
        top_k: int = 5,
    ) -> List[GatewayKnowledgeItem]:
        if not self.enabled or not self.config.tables:
            return []

        q_clean = query.strip()
        if not q_clean:
            return []

        q_words = [w for w in q_clean.split() if len(w) > 2]
        if not q_words:
            q_words = [q_clean]

        items: List[GatewayKnowledgeItem] = []
        limit_per_table = min(top_k or self.config.max_results, 10)

        try:
            conn = self._get_connection()
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                for table_cfg in self.config.tables:
                    # Construct safe parameterized query
                    # WHERE (col1 ILIKE %s OR col2 ILIKE %s ...)
                    where_clauses = []
                    params = []

                    for col in table_cfg.search_columns:
                        for word in q_words:
                            where_clauses.append(f"{col} ILIKE %s")
                            params.append(f"%{word}%")

                    if not where_clauses:
                        continue

                    sql = f"""
                        SELECT * FROM {table_cfg.table_name}
                        WHERE {' OR '.join(where_clauses)}
                        LIMIT %s;
                    """
                    params.append(limit_per_table)

                    cur.execute(sql, tuple(params))
                    rows = cur.fetchall()

                    for row in rows:
                        row_dict = dict(row)
                        row_id = str(row_dict.get(table_cfg.id_column, "unknown"))
                        title = str(row_dict.get(table_cfg.title_column, f"Record {row_id}"))
                        content = str(row_dict.get(table_cfg.content_column, ""))

                        # Fallback for composite content
                        if not content:
                            content = " | ".join(f"{k}: {v}" for k, v in row_dict.items() if v)

                        snippet = content[:200] + ("..." if len(content) > 200 else "")

                        # Calculate basic lexical match score
                        hits = sum(1 for w in q_words if w.lower() in (title + " " + content).lower())
                        raw_score = min(0.95, 0.50 + 0.15 * hits)

                        raw_tags = row_dict.get("tags", "")
                        parsed_tags = [t.strip() for t in raw_tags.split(",")] if isinstance(raw_tags, str) else []

                        item = GatewayKnowledgeItem(
                            id=f"sql_{table_cfg.table_name}_{row_id}",
                            source_type="sql",
                            title=title,
                            content=content,
                            snippet=snippet,
                            raw_score=round(raw_score, 4),
                            provenance={
                                "connector": "sql_postgres_db",
                                "database": self.config.database,
                                "table": table_cfg.table_name,
                                "row_id": row_id,
                                "host": f"{self.config.host}:{self.config.port}",
                            },
                            metadata={
                                "category": row_dict.get("category", "database_record"),
                                "tags": parsed_tags,
                                "columns": list(row_dict.keys()),
                            },
                        )
                        items.append(item)

            conn.close()
            self.is_connected = True
        except Exception as e:
            logger.debug("PostgreSQL query failed: %s", e)
            self.is_connected = False

        items.sort(key=lambda x: x.raw_score, reverse=True)
        return items[:top_k]

    async def health_check(self) -> Dict[str, Any]:
        if not self.enabled:
            return {"status": "disabled", "connector": self.name}

        try:
            conn = self._get_connection()
            with conn.cursor() as cur:
                cur.execute("SELECT version();")
                db_version = cur.fetchone()[0]

                table_stats = {}
                for t in self.config.tables:
                    try:
                        cur.execute(f"SELECT count(*) FROM {t.table_name};")
                        table_stats[t.table_name] = cur.fetchone()[0]
                    except Exception:
                        table_stats[t.table_name] = "error"

            conn.close()
            self.is_connected = True
            return {
                "status": "healthy",
                "connector": self.name,
                "database": self.config.database,
                "host": f"{self.config.host}:{self.config.port}",
                "tables": table_stats,
                "version": db_version[:50] + "...",
            }
        except Exception as e:
            self.is_connected = False
            return {
                "status": "unreachable",
                "connector": self.name,
                "database": self.config.database,
                "host": f"{self.config.host}:{self.config.port}",
                "error": str(e),
            }
