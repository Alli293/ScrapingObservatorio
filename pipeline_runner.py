"""
pipeline_runner.py
──────────────────
Orquestador paralelo del Observatorio Democrático.

Implementa la Opción A de la arquitectura propuesta:
  1. Health check liviano antes de cada scraper
  2. Ejecución paralela controlada (semáforo asyncio)
  3. Reintentos automáticos con backoff exponencial
  4. Estado persistente en SQLite (execution_state.db)
  5. Detección de anomalías comparando contra historial
  6. Modo incremental — omite scrapers que ya corrieron exitosamente hoy

Los scrapers NO se modifican. Todo corre en un ThreadPoolExecutor
(los scrapers son síncronos) orquestado desde asyncio.

Uso:
    python pipeline_runner.py                           # todos los scrapers
    python pipeline_runner.py --only teletica           # uno específico
    python pipeline_runner.py --only teletica repretel  # varios
    python pipeline_runner.py --test                    # modo prueba
    python pipeline_runner.py --workers 5               # controlar concurrencia
    python pipeline_runner.py --skip-health             # omitir health check
    python pipeline_runner.py --incremental             # solo los que faltan
    python pipeline_runner.py --status                  # ver estado actual
"""

import asyncio
import argparse
import sys
import os
import json
import time
import importlib
import inspect
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from execution_state import (
    init_db, record_execution, check_anomaly,
    get_last_run, print_summary as print_state_summary,
)
from health_check import check_one as health_check_one
from main import SCRAPERS_REGISTRY

CR_TZ           = timezone(timedelta(hours=-6))
DEFAULT_WORKERS = 6
MAX_RETRIES     = 2
RETRY_DELAY_S   = 15


# ─────────────────────────────────────────────────────────────────────────────
# EJECUCIÓN SÍNCRONA DE UN SCRAPER
# ─────────────────────────────────────────────────────────────────────────────
def _run_scraper_sync(
    name:       str,
    output_dir: str,
    log_dir:    str,
    test_mode:  bool,
) -> dict:
    if name not in SCRAPERS_REGISTRY:
        return {
            "source": name, "status": "ERROR",
            "error": f"'{name}' no registrado", "duration_s": 0,
            "total_valid": 0, "total_discarded": 0,
        }

    module_path, class_name = SCRAPERS_REGISTRY[name]
    original_cwd = os.getcwd()
    t0 = time.time()

    try:
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        os.chdir(output_dir)

        module       = importlib.import_module(module_path)
        ScraperClass = getattr(module, class_name)
        init_params  = inspect.signature(ScraperClass.__init__).parameters

        if "test_mode" in init_params:
            scraper = ScraperClass(
                output_dir=output_dir, log_dir=log_dir, test_mode=test_mode
            )
        else:
            scraper = ScraperClass(output_dir=output_dir, log_dir=log_dir)

        result               = scraper.run()
        result["duration_s"] = round(time.time() - t0, 2)
        os.chdir(original_cwd)
        return result

    except Exception as exc:
        os.chdir(original_cwd)
        return {
            "source":          name,
            "status":          "ERROR",
            "error":           str(exc),
            "traceback":       traceback.format_exc(),
            "duration_s":      round(time.time() - t0, 2),
            "total_valid":     0,
            "total_discarded": 0,
        }


# ─────────────────────────────────────────────────────────────────────────────
# WORKER ASYNC
# ─────────────────────────────────────────────────────────────────────────────
async def _worker(
    name:         str,
    semaphore:    asyncio.Semaphore,
    executor:     ThreadPoolExecutor,
    output_dir:   str,
    log_dir:      str,
    test_mode:    bool,
    skip_health:  bool,
    incremental:  bool,
    loop:         asyncio.AbstractEventLoop,
) -> dict:

    async with semaphore:
        ts_start = time.time()
        today    = datetime.now(CR_TZ).strftime("%Y-%m-%d")

        # ── 0. Modo incremental ──────────────────────────────────────────────
        if incremental:
            last = get_last_run(name)
            if last and last["status"] == "OK" and last["run_date"] == today:
                _log(
                    f"⊘  [{name}] ya corrió hoy "
                    f"({last['total_valid']} artículos) — saltando"
                )
                return {
                    "source":          name,
                    "status":          "SKIPPED_INCREMENTAL",
                    "total_valid":     last["total_valid"],
                    "total_discarded": last["total_discarded"],
                    "duration_s":      0,
                    "health_ok":       True,
                    "reason":          "ya corrió exitosamente hoy",
                }

        _log(f"▶  [{name}] iniciando")

        # ── 1. Health check ──────────────────────────────────────────────────
        health_ok = True
        if not skip_health:
            hc        = await loop.run_in_executor(executor, health_check_one, name)
            health_ok = hc["ok"]
            if not health_ok:
                _log(f"✗  [{name}] health check FALLÓ — {hc['reason']} (omitiendo)")
                record_execution(
                    source=name, status="SKIPPED",
                    health_ok=False, error_msg=hc["reason"],
                )
                return {
                    "source":          name,
                    "status":          "SKIPPED",
                    "error":           hc["reason"],
                    "total_valid":     0,
                    "total_discarded": 0,
                    "duration_s":      round(time.time() - ts_start, 2),
                    "health_ok":       False,
                }
            if hc.get("slow"):
                _log(
                    f"⚠  [{name}] sitio lento ({hc['duration_s']:.1f}s) "
                    f"— continuando igual"
                )

        # ── 2. Ejecución con reintentos ──────────────────────────────────────
        result  = None
        attempt = 0
        while attempt <= MAX_RETRIES:
            if attempt > 0:
                delay = RETRY_DELAY_S * attempt
                _log(f"↺  [{name}] reintento {attempt}/{MAX_RETRIES} en {delay}s...")
                await asyncio.sleep(delay)

            result = await loop.run_in_executor(
                executor,
                _run_scraper_sync,
                name, output_dir, log_dir, test_mode,
            )

            if result.get("status") == "OK":
                break
            attempt += 1

        result["health_ok"] = health_ok

        # ── 3. Registrar en SQLite ───────────────────────────────────────────
        valid     = result.get("total_valid", 0)
        discarded = result.get("total_discarded", 0)
        duration  = result.get("duration_s", round(time.time() - ts_start, 2))
        status    = result.get("status", "ERROR")
        err_msg   = result.get("error") if status != "OK" else None

        record_execution(
            source=name, status=status,
            total_valid=valid, total_discarded=discarded,
            duration_s=duration, health_ok=health_ok,
            error_msg=err_msg,
        )

        # ── 4. Detección de anomalías ────────────────────────────────────────
        if status == "OK":
            anomaly = check_anomaly(name, valid)
            if anomaly["anomaly"]:
                level = anomaly["level"].upper()
                _log(f"⚠  [{name}] ANOMALÍA [{level}]: {anomaly['reason']}")
                result["anomaly"] = anomaly
            else:
                result["anomaly"] = None
            _log(f"✓  [{name}] {valid} artículos válidos en {duration:.1f}s")
        else:
            err_short = (err_msg or "")[:80]
            _log(f"✗  [{name}] ERROR tras {attempt} intento(s): {err_short}")

        return result


# ─────────────────────────────────────────────────────────────────────────────
# ORQUESTADOR PRINCIPAL
# ─────────────────────────────────────────────────────────────────────────────
async def run_pipeline(
    to_run:      list[str],
    output_dir:  str  = "output",
    log_dir:     str  = "logs",
    test_mode:   bool = False,
    workers:     int  = DEFAULT_WORKERS,
    skip_health: bool = False,
    incremental: bool = False,
) -> list[dict]:

    init_db()
    semaphore = asyncio.Semaphore(workers)
    loop      = asyncio.get_event_loop()

    _log(
        f"Pipeline paralelo — {len(to_run)} scrapers — "
        f"{workers} workers — "
        f"{'incremental' if incremental else 'completo'}"
    )
    if skip_health:
        _log("Health check desactivado (--skip-health)")
    if incremental:
        _log("Modo incremental: se saltarán scrapers que ya corrieron hoy con éxito")

    with ThreadPoolExecutor(max_workers=workers) as executor:
        tasks = [
            _worker(
                name=name,
                semaphore=semaphore,
                executor=executor,
                output_dir=output_dir,
                log_dir=log_dir,
                test_mode=test_mode,
                skip_health=skip_health,
                incremental=incremental,
                loop=loop,
            )
            for name in to_run
        ]
        results = await asyncio.gather(*tasks, return_exceptions=False)

    return list(results)


# ─────────────────────────────────────────────────────────────────────────────
# RESUMEN FINAL
# ─────────────────────────────────────────────────────────────────────────────
def _print_pipeline_summary(results: list[dict], elapsed: float):
    ok          = [r for r in results if r.get("status") == "OK"]
    errors      = [r for r in results if r.get("status") == "ERROR"]
    skipped_hc  = [r for r in results if r.get("status") == "SKIPPED"]
    skipped_inc = [r for r in results if r.get("status") == "SKIPPED_INCREMENTAL"]
    anomaly     = [r for r in ok if r.get("anomaly")]

    total_valid     = sum(r.get("total_valid", 0) for r in ok)
    total_discarded = sum(r.get("total_discarded", 0) for r in ok)
    total_valid_inc = sum(r.get("total_valid", 0) for r in skipped_inc)

    print(f"\n{'═'*65}")
    print("  RESUMEN PIPELINE PARALELO")
    print(f"{'═'*65}")
    print(f"  Scrapers totales       : {len(results)}")
    print(f"  Exitosos esta corrida  : {len(ok)}")
    print(f"  Ya tenían datos (hoy)  : {len(skipped_inc)}")
    print(f"  Omitidos (health fail) : {len(skipped_hc)}")
    print(f"  Con error              : {len(errors)}")
    print(f"  Con anomalía           : {len(anomaly)}")
    print(f"  ─────────────────────────────────────────────────")
    print(f"  Artículos esta corrida : {total_valid}")
    if skipped_inc:
        print(f"  Artículos prev. hoy    : {total_valid_inc}")
        print(f"  Total del día          : {total_valid + total_valid_inc}")
    print(f"  Descartados            : {total_discarded}")
    print(f"  Tiempo esta corrida    : {elapsed:.1f}s ({elapsed/60:.1f} min)")
    print(f"{'═'*65}")

    if errors:
        print("\n  Scrapers con error:")
        for r in errors:
            err = (r.get("error") or "")[:70]
            print(f"    ✗ {r['source']:<25} {err}")

    if skipped_hc:
        print("\n  Omitidos por health check:")
        for r in skipped_hc:
            print(f"    ⊘ {r['source']:<25} {r.get('error','')}")

    if anomaly:
        print("\n  Anomalías detectadas:")
        for r in anomaly:
            a = r["anomaly"]
            print(f"    ⚠ {r['source']:<25} [{a['level'].upper()}] {a['reason']}")

    print()


def _save_report(results: list[dict], log_dir: str):
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    ts   = datetime.now(CR_TZ).strftime("%Y%m%d_%H%M%S")
    path = os.path.join(log_dir, f"pipeline_report_{ts}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({
            "run_ts":  datetime.now(CR_TZ).isoformat(),
            "results": results,
        }, f, ensure_ascii=False, indent=2)
    _log(f"Reporte guardado: {path}")


def _log(msg: str):
    ts = datetime.now(CR_TZ).strftime("%H:%M:%S")
    print(f"  [{ts}] {msg}")


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────
def main():
    print("""
╔══════════════════════════════════════════════════════════════╗
║      OBSERVATORIO DEMOCRÁTICO — Pipeline Paralelo v2.0       ║
╚══════════════════════════════════════════════════════════════╝
""")

    parser = argparse.ArgumentParser(
        description="Pipeline paralelo — Observatorio Democrático"
    )
    parser.add_argument(
        "--only", nargs="+", metavar="SCRAPER",
        help="Ejecutar solo scrapers específicos"
    )
    parser.add_argument("--output",      default="output")
    parser.add_argument("--logs",        default="logs")
    parser.add_argument("--test",        action="store_true",
                        help="Modo prueba (limita artículos)")
    parser.add_argument("--workers",     type=int, default=DEFAULT_WORKERS,
                        help=f"Scrapers en paralelo (default: {DEFAULT_WORKERS})")
    parser.add_argument("--skip-health", action="store_true",
                        help="Omitir health check")
    parser.add_argument("--incremental", action="store_true",
                        help="Saltar scrapers que ya corrieron exitosamente hoy")
    parser.add_argument("--status",      action="store_true",
                        help="Mostrar estado actual y salir")

    args = parser.parse_args()

    if args.status:
        print_state_summary()
        sys.exit(0)

    if args.only:
        to_run  = [n for n in args.only if n in SCRAPERS_REGISTRY]
        missing = [n for n in args.only if n not in SCRAPERS_REGISTRY]
        if missing:
            print(f"  ADVERTENCIA: no encontrados → {', '.join(missing)}")
        if not to_run:
            print("  Sin scrapers válidos.")
            sys.exit(1)
    else:
        to_run = list(SCRAPERS_REGISTRY.keys())

    print(f"  Scrapers a ejecutar : {len(to_run)}")
    print(f"  Workers paralelos   : {args.workers}")
    print(f"  Modo prueba         : {'SÍ' if args.test else 'No'}")
    print(f"  Health check        : {'No' if args.skip_health else 'SÍ'}")
    print(f"  Incremental         : {'SÍ — salta los que ya corrieron hoy' if args.incremental else 'No'}")
    print(f"  Output              : {args.output}/")
    print(f"  Logs                : {args.logs}/\n")

    t0 = time.time()

    results = asyncio.run(run_pipeline(
        to_run      = to_run,
        output_dir  = args.output,
        log_dir     = args.logs,
        test_mode   = args.test,
        workers     = args.workers,
        skip_health = args.skip_health,
        incremental = args.incremental,
    ))

    elapsed = time.time() - t0
    _print_pipeline_summary(results, elapsed)
    _save_report(results, args.logs)


if __name__ == "__main__":
    main()
