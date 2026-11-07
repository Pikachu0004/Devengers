"""
Devengers High-Performance Turso (libSQL) Cloud SQLite Client.
Zero external dependencies - built entirely on Python standard library (urllib.request, json, base64).

Provides a drop-in SQLite3 DB-API 2.0 compatible interface over Turso's /v2/pipeline HTTP REST API.
Enables instant persistence on Render Free Tier (which has ephemeral disks) without requiring C-extensions
or packages that fail to compile on Python 3.14.
"""

import os
import json
import base64
import sqlite3
import urllib.request
import urllib.error
from typing import Any, Dict, List, Optional, Tuple, Union

class TursoError(Exception):
    """Base error for Turso client."""
    pass

class TursoOperationalError(sqlite3.OperationalError, TursoError):
    """Raised for SQL syntax, duplicate column, or table errors (matches sqlite3.OperationalError)."""
    pass

class TursoIntegrityError(sqlite3.IntegrityError, TursoError):
    """Raised for constraint violations (matches sqlite3.IntegrityError)."""
    pass

class TursoRow:
    """Row object that supports both dict-like key access and tuple-like index access (matching sqlite3.Row)."""
    def __init__(self, cols: List[str], values: List[Any]):
        self._cols = cols
        self._values = values
        self._map = {col.lower(): val for col, val in zip(cols, values)}
        self._orig_map = {col: val for col, val in zip(cols, values)}

    def __getitem__(self, key: Union[int, str]) -> Any:
        if isinstance(key, int):
            return self._values[key]
        if isinstance(key, str):
            lower_key = key.lower()
            if lower_key in self._map:
                return self._map[lower_key]
            raise KeyError(f"Column '{key}' not found in TursoRow ({list(self._orig_map.keys())})")
        raise TypeError(f"Row indices must be integer or string, not {type(key).__name__}")

    def get(self, key: str, default: Any = None) -> Any:
        return self._map.get(key.lower(), default)

    def keys(self) -> List[str]:
        return list(self._cols)

    def values(self) -> List[Any]:
        return list(self._values)

    def items(self) -> List[Tuple[str, Any]]:
        return list(self._orig_map.items())

    def __iter__(self):
        return iter(self._values)

    def __len__(self) -> int:
        return len(self._values)

    def __contains__(self, key: str) -> bool:
        return key.lower() in self._map

    def __repr__(self) -> str:
        return f"<TursoRow {self._orig_map}>"


def _serialize_arg(val: Any) -> Dict[str, Any]:
    """Serializes a Python parameter into Hrana protocol value specification."""
    if val is None:
        return {"type": "null"}
    if isinstance(val, bool):
        return {"type": "integer", "value": "1" if val else "0"}
    if isinstance(val, int):
        return {"type": "integer", "value": str(val)}
    if isinstance(val, float):
        return {"type": "float", "value": val}
    if isinstance(val, bytes):
        return {"type": "blob", "base64": base64.b64encode(val).decode("ascii")}
    return {"type": "text", "value": str(val)}


def _deserialize_cell(cell: Dict[str, Any]) -> Any:
    """Deserializes a Hrana cell dictionary into a native Python value."""
    cell_type = cell.get("type", "null")
    if cell_type == "null":
        return None
    if cell_type == "integer":
        return int(cell.get("value", 0))
    if cell_type == "float":
        return float(cell.get("value", 0.0))
    if cell_type == "text":
        return cell.get("value", "")
    if cell_type == "blob":
        b64 = cell.get("base64", "")
        return base64.b64decode(b64) if b64 else b""
    return cell.get("value")


class TursoCursor:
    """Cursor implementation for Turso libSQL pipeline."""
    def __init__(self, conn: "TursoConnection"):
        self.conn = conn
        self.description: Optional[List[Tuple]] = None
        self.rowcount: int = -1
        self.lastrowid: Optional[int] = None
        self._rows: List[TursoRow] = []
        self._idx: int = 0

    def execute(self, sql: str, params: Optional[Union[Tuple, List, Dict]] = None) -> "TursoCursor":
        clean_sql = sql.strip().rstrip(";")
        # Filter out PRAGMA WAL statements (Turso manages its own replication)
        if clean_sql.upper().startswith("PRAGMA JOURNAL_MODE"):
            self.rowcount = 0
            self.description = []
            self._rows = []
            self._idx = 0
            return self

        stmt: Dict[str, Any] = {"sql": clean_sql}
        if params:
            if isinstance(params, (tuple, list)):
                stmt["args"] = [_serialize_arg(p) for p in params]
            elif isinstance(params, dict):
                stmt["named_args"] = [
                    {"name": k.lstrip(":$@"), "value": _serialize_arg(v)}
                    for k, v in params.items()
                ]

        res = self.conn._execute_pipeline([stmt])
        cols = [c.get("name", f"col_{i}") for i, c in enumerate(res.get("cols", []))]
        self.description = [(c, None, None, None, None, None, None) for c in cols] if cols else None
        self.rowcount = res.get("affected_row_count", 0)
        self.lastrowid = res.get("last_insert_rowid")

        raw_rows = res.get("rows", [])
        self._rows = [
            TursoRow(cols, [_deserialize_cell(cell) for cell in r])
            for r in raw_rows
        ]
        self._idx = 0
        return self

    def executemany(self, sql: str, seq_of_params: List[Union[Tuple, List, Dict]]) -> "TursoCursor":
        total_affected = 0
        last_id = None
        for params in seq_of_params:
            self.execute(sql, params)
            total_affected += self.rowcount
            if self.lastrowid is not None:
                last_id = self.lastrowid
        self.rowcount = total_affected
        self.lastrowid = last_id
        return self

    def executescript(self, sql_script: str) -> "TursoCursor":
        stmts = [s.strip() for s in sql_script.split(";") if s.strip()]
        for stmt in stmts:
            self.execute(stmt)
        return self

    def fetchone(self) -> Optional[TursoRow]:
        if self._idx < len(self._rows):
            row = self._rows[self._idx]
            self._idx += 1
            return row
        return None

    def fetchall(self) -> List[TursoRow]:
        if self._idx < len(self._rows):
            rows = self._rows[self._idx:]
            self._idx = len(self._rows)
            return rows
        return []

    def fetchmany(self, size: Optional[int] = None) -> List[TursoRow]:
        if size is None:
            size = 1
        end = min(self._idx + size, len(self._rows))
        rows = self._rows[self._idx:end]
        self._idx = end
        return rows

    def close(self):
        self._rows = []
        self._idx = 0


class TursoConnection:
    """Connection implementation targeting Turso's /v2/pipeline HTTPS endpoint."""
    def __init__(self, database_url: str, auth_token: str):
        # Normalize database URL
        url = database_url.strip()
        if url.startswith("libsql://"):
            url = "https://" + url[len("libsql://"):]
        if not url.startswith("http://") and not url.startswith("https://"):
            url = f"https://{url}"
        self.base_url = url.rstrip("/")
        self.pipeline_url = f"{self.base_url}/v2/pipeline"
        self.auth_token = auth_token.strip()
        self.row_factory = TursoRow

    def cursor(self) -> TursoCursor:
        return TursoCursor(self)

    def execute(self, sql: str, params: Optional[Union[Tuple, List, Dict]] = None) -> TursoCursor:
        cur = self.cursor()
        return cur.execute(sql, params)

    def executescript(self, sql_script: str) -> TursoCursor:
        cur = self.cursor()
        return cur.executescript(sql_script)

    def commit(self):
        """No-op on stateless REST pipeline; statements auto-commit immediately upon execute."""
        pass

    def rollback(self):
        """No-op on stateless REST pipeline."""
        pass

    def close(self):
        """No-op for HTTP stateless connection."""
        pass

    def _execute_pipeline(self, stmts: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Executes one or more statements in a single atomic Turso pipeline request."""
        requests_payload = [{"type": "execute", "stmt": stmt} for stmt in stmts]
        requests_payload.append({"type": "close"})

        payload_bytes = json.dumps({"requests": requests_payload}).encode("utf-8")
        req = urllib.request.Request(
            self.pipeline_url,
            data=payload_bytes,
            headers={
                "Authorization": f"Bearer {self.auth_token}",
                "Content-Type": "application/json",
                "User-Agent": "DevengersPlatform/1.0"
            },
            method="POST"
        )

        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                resp_bytes = resp.read()
                data = json.loads(resp_bytes.decode("utf-8"))
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Turso HTTP Error {e.code}: {err_body}") from e
        except Exception as e:
            raise RuntimeError(f"Turso Connection Error: {e}") from e

        results = data.get("results", [])
        if not results:
            return {}

        first = results[0]
        if first.get("type") == "error":
            err_obj = first.get("error", {})
            err_msg = err_obj.get("message", "Unknown Turso Error")
            if "constraint" in err_msg.lower():
                raise TursoIntegrityError(f"Turso SQL Error: {err_msg}")
            raise TursoOperationalError(f"Turso SQL Error: {err_msg}")

        return first.get("response", {}).get("result", {})


def is_turso_configured() -> bool:
    """Returns True if Turso credentials are present in environment."""
    url = os.environ.get("TURSO_DATABASE_URL", "").strip() or os.environ.get("DEVENGERS_TURSO_URL", "").strip()
    token = os.environ.get("TURSO_AUTH_TOKEN", "").strip() or os.environ.get("DEVENGERS_TURSO_TOKEN", "").strip()
    return bool(url and token)


def get_turso_connection() -> Optional[TursoConnection]:
    """Builds and returns a TursoConnection if configured, otherwise None."""
    url = os.environ.get("TURSO_DATABASE_URL", "").strip() or os.environ.get("DEVENGERS_TURSO_URL", "").strip()
    token = os.environ.get("TURSO_AUTH_TOKEN", "").strip() or os.environ.get("DEVENGERS_TURSO_TOKEN", "").strip()
    if url and token:
        return TursoConnection(url, token)
    return None

