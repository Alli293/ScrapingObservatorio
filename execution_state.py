"""
execution_state.py
──────────────────
Capa de estado persistente del pipeline — SQLite.

Registra cada ejecución de scraper (fecha, artículos, errores, duración)
y permite detectar anomalías comparando contra el historial.

Uso independiente:
    python execution_state.py          # muestra resumen del estado actual
    python execution_state.py --reset  # borra el historial (cuidado)
"""

import sqlite3
import os
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

CR_TZ     = timezone(timedelta(hours=-6))
DB_PATH   = os.path.join(os.path.dirname(os.path.abspath(__file__)), "execution_state.db")

# ── Umbrales de anomalía ──────────────────────────────────────────────────────
ANOMALY_DROP_PCT   = 50   # caída > 50% respecto al promedio histórico = anomalía
ANOMALY_MIN_RUNS   = 3    # necesita al menos N ejecuciones previas para comparar
ANOMALY_ZERO_RUNS  = 2    # X ejecuciones consecutivas en 0 = alerta crítica


# ─────────────────────────────────────────────────────────────────────────────
# INICIALIZACIÓN
# ─────────────────────────────────────────────────────────────────────────────
def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Crea las tablas si no existen."""
    with _get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS executions (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                source          TEXT    NOT NULL,
                run_date        TEXT    NOT NULL,   -- ISO date YYYY-MM-DD
                run_ts          TEXT    NOT NULL,   -- ISO datetime completo
                status          TEXT    NOT NULL,   -- OK | ERROR | SKIPPED
                total_valid     INTEGER DEFAULT 0,
                total_discarded INTEGER DEFAULT 0,
                duration_s      REAL    DEFAULT 0,
                health_ok       INTEGER DEFAULT 1,  -- 1 = pasó health check
                error_msg       TEXT    DEFAULT NULL,
                notes           TEXT    DEFAULT NULL
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_source_date
            ON executions(source, run_date)
        """)
        conn.commit()


# ─────────────────────────────────────────────────────────────────────────────
# ESCRITURA
# ─────────────────────────────────────────────────────────────────────────────
def record_execution(
    source:          str,
    status:          str,
    total_valid:     int  = 0,
    total_discarded: int  = 0,
    duration_s:      float = 0.0,
    health_ok:       bool = True,
    error_msg:       str  = None,
    notes:           str  = None,
):
    """Registra el resultado de una ejecución."""
    init_db()
    now = datetime.now(CR_TZ)
    with _get_conn() as conn:
        conn.execute("""
            INSERT INTO executions
                (source, run_date, run_ts, status,
                 total_valid, total_discarded, duration_s,
                 health_ok, error_msg, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            source,
            now.strftime("%Y-%m-%d"),
            now.isoformat(),
            status,
            total_valid,
            total_discarded,
            round(duration_s, 2),
            1 if health_ok else 0,
            error_msg,
            notes,
        ))
        conn.commit()


# ─────────────────────────────────────────────────────────────────────────────
# LECTURA
# ─────────────────────────────────────────────────────────────────────────────
def get_last_run(source: str) -> dict | None:
    """Retorna el último registro de ejecución para una fuente."""
    init_db()
    with _get_conn() as conn:
        row = conn.execute("""
            SELECT * FROM executions
            WHERE source = ?
            ORDER BY run_ts DESC
            LIMIT 1
        """, (source,)).fetchone()
    return dict(row) if row else None


def get_history(source: str, limit: int = 10) -> list[dict]:
    """Retorna el historial de ejecuciones para una fuente."""
    init_db()
    with _get_conn() as conn:
        rows = conn.execute("""
            SELECT * FROM executions
            WHERE source = ?
            ORDER BY run_ts DESC
            LIMIT ?
        """, (source, limit)).fetchall()
    return [dict(r) for r in rows]


def get_avg_articles(source: str, last_n: int = 7) -> float | None:
    """Promedio de artículos válidos de las últimas N ejecuciones exitosas."""
    init_db()
    with _get_conn() as conn:
        row = conn.execute("""
            SELECT AVG(total_valid) as avg_v
            FROM (
                SELECT total_valid FROM executions
                WHERE source = ? AND status = 'OK'
                ORDER BY run_ts DESC
                LIMIT ?
            )
        """, (source, last_n)).fetchone()
    return row["avg_v"] if row and row["avg_v"] is not None else None


def get_all_sources_summary() -> list[dict]:
    """Resumen del estado actual de todas las fuentes."""
    init_db()
    with _get_conn() as conn:
        rows = conn.execute("""
            SELECT
                e.source,
                e.run_date        AS last_run_date,
                e.status          AS last_status,
                e.total_valid     AS last_valid,
                e.total_discarded AS last_discarded,
                e.duration_s      AS last_duration,
                e.health_ok       AS last_health,
                e.error_msg       AS last_error,
                COUNT(e2.id)      AS total_runs
            FROM executions e
            JOIN executions e2 ON e2.source = e.source
            WHERE e.id = (
                SELECT id FROM executions
                WHERE source = e.source
                ORDER BY run_ts DESC LIMIT 1
            )
            GROUP BY e.source
            ORDER BY e.source
        """).fetchall()
    return [dict(r) for r in rows]


# ─────────────────────────────────────────────────────────────────────────────
# DETECCIÓN DE ANOMALÍAS
# ─────────────────────────────────────────────────────────────────────────────
def check_anomaly(source: str, current_valid: int) -> dict:
    """
    Compara el resultado actual con el historial y detecta anomalías.

    Retorna:
        {
            "anomaly": bool,
            "level":   "ok" | "warning" | "critical",
            "reason":  str
        }
    """
    init_db()
    history = get_history(source, limit=10)
    ok_runs = [h for h in history if h["status"] == "OK"]

    # No hay suficiente historial para comparar
    if len(ok_runs) < ANOMALY_MIN_RUNS:
        return {"anomaly": False, "level": "ok", "reason": "historial insuficiente"}

    # Verificar ceros consecutivos
    recent = ok_runs[:ANOMALY_ZERO_RUNS]
    if all(r["total_valid"] == 0 for r in recent) and current_valid == 0:
        return {
            "anomaly": True,
            "level":   "critical",
            "reason":  f"{ANOMALY_ZERO_RUNS + 1} ejecuciones consecutivas con 0 artículos",
        }

    # Verificar caída porcentual
    avg = get_avg_articles(source, last_n=7)
    if avg and avg > 0:
        drop_pct = ((avg - current_valid) / avg) * 100
        if drop_pct > ANOMALY_DROP_PCT:
            return {
                "anomaly": True,
                "level":   "warning",
                "reason":  f"caída del {drop_pct:.0f}% vs promedio ({avg:.0f} → {current_valid})",
            }

    return {"anomaly": False, "level": "ok", "reason": "normal"}


# ─────────────────────────────────────────────────────────────────────────────
# CLI — resumen rápido
# ─────────────────────────────────────────────────────────────────────────────
def print_summary():
    summary = get_all_sources_summary()
    if not summary:
        print("  Sin datos en execution_state.db todavía.")
        return

    print(f"\n{'─'*75}")
    print(f"  {'FUENTE':<25} {'ÚLTIMA EJE':^12} {'ESTADO':^8} {'VÁLIDOS':>7} {'DURACIÓN':>9}")
    print(f"{'─'*75}")
    for s in summary:
        icon = "✓" if s["last_status"] == "OK" else "✗"
        dur  = f"{s['last_duration']:.0f}s" if s["last_duration"] else "-"
        print(
            f"  {icon} {s['source']:<24} {s['last_run_date']:^12} "
            f"{s['last_status']:^8} {s['last_valid']:>7} {dur:>9}"
        )
    print(f"{'─'*75}\n")


if __name__ == "__main__":
    import sys
    if "--reset" in sys.argv:
        confirm = input("¿Borrar todo el historial? (escribe 'SI' para confirmar): ")
        if confirm == "SI":
            os.remove(DB_PATH)
            print("  Historial borrado.")
        else:
            print("  Cancelado.")
    else:
        print_summary()
