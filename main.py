"""
main.py
Orquestador principal del Observatorio Democrático.

Ejecuta todos los scrapers registrados de forma secuencial,
consolida los resultados y genera un reporte de ejecución.

Uso:
    python main.py                    # Ejecuta todos los scrapers
    python main.py --only elperiodicocr  # Ejecuta solo un scraper específico
    python main.py --list             # Lista scrapers disponibles
"""

import argparse
import sys
import os
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Agregar el directorio raíz al path para importaciones
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# -----------------------------------------------------------------------
# REGISTRO DE SCRAPERS
# Agregar aquí cada nuevo scraper que se desarrolle.
# Formato: "nombre_clave": ("módulo", "ClaseScraper")
# -----------------------------------------------------------------------
SCRAPERS_REGISTRY = {
    "elperiodicocr": ("scrapers.elperiodicocr", "ElPeriodicoCRScraper"),
    "lareaccioncr":  ("scrapers.lareaccioncr",  "LaReaccionCRScraper"),
    "larevistacr":   ("scrapers.larevistacr",   "LaRevistaCRScraper"),
    "latejacr":      ("scrapers.latejacr",      "LaTejaCRScraper"),
    "lavozdegoicoechea": ("scrapers.lavozdegoicoechea", "LaVozDeGoicoecheaScraper"),
    "monumental":        ("scrapers.monumental",        "MonumentalScraper"),
    "mundiario":         ("scrapers.mundiario",         "MundiarioScraper"),
    "ncrnoticias":       ("scrapers.ncrnoticias",       "NCRNoticiasScraper"),
    "noticiasenlineacr": ("scrapers.noticiasenlineacr", "NoticiasEnLineaCRScraper"),
    # Próximos scrapers — agregar aquí:
    # "nacion":        ("scrapers.nacion",        "NacionScraper"),
    # "crhoy":         ("scrapers.crhoy",          "CRHoyScraper"),
    # "teletica":      ("scrapers.teletica",        "TeleticaScraper"),
    # "diarioextra":   ("scrapers.diarioextra",     "DiarioExtraScraper"),
    # "repretel":      ("scrapers.repretel",        "ReprettelScraper"),
    # "semanario":     ("scrapers.semanario",       "SemanaroScraper"),
    # "insidecostarica": ("scrapers.insidecostarica", "InsideCostaRicaScraper"),
    # "ameliarueda":   ("scrapers.ameliarueda",    "AmeliaRuedaScraper"),
    # "monumental":    ("scrapers.monumental",     "MonumentalScraper"),
    # "observador":    ("scrapers.observador",     "ObservadorScraper"),
    # "elpais_cr":     ("scrapers.elpais_cr",      "ElPaisCRScraper"),
    # "elmundo_cr":    ("scrapers.elmundo_cr",     "ElMundoCRScraper"),
    # "delfino":       ("scrapers.delfino",        "DelfinoScraper"),
    # "estrategia_cr": ("scrapers.estrategia_cr",  "EstrategiaCRScraper"),
    # "larepublica":   ("scrapers.larepublica",    "LaRepublicaScraper"),
    # "confidencial_cr": ("scrapers.confidencial_cr", "ConfidencialCRScraper"),
    # "burgos_cr":     ("scrapers.burgos_cr",      "BurgosCRScraper"),
    # "vozdeguanacaste": ("scrapers.vozdeguanacaste", "VozDeGuanacasteScraper"),
}

CR_TZ = timezone(timedelta(hours=-6))


def load_scraper_class(module_path: str, class_name: str):
    """Importa dinámicamente una clase de scraper."""
    import importlib
    module = importlib.import_module(module_path)
    return getattr(module, class_name)


def run_scraper(
    name: str,
    output_dir: str = "output",
    log_dir: str = "logs",
    test_mode: bool = False,
) -> dict:
    """Carga y ejecuta un scraper por nombre."""
    if name not in SCRAPERS_REGISTRY:
        return {"source": name, "status": "ERROR", "error": f"Scraper '{name}' no registrado"}

    module_path, class_name = SCRAPERS_REGISTRY[name]

    try:
        ScraperClass = load_scraper_class(module_path, class_name)
        import inspect
        init_params = inspect.signature(ScraperClass.__init__).parameters
        if "test_mode" in init_params:
            scraper = ScraperClass(output_dir=output_dir, log_dir=log_dir, test_mode=test_mode)
        else:
            if test_mode:
                print(f"        ⚠ {name} no tiene modo prueba, ejecutando normal")
            scraper = ScraperClass(output_dir=output_dir, log_dir=log_dir)
        return scraper.run()
    except ImportError as e:
        return {"source": name, "status": "ERROR", "error": f"Error de importación: {e}"}
    except Exception as e:
        return {"source": name, "status": "ERROR", "error": str(e)}


def print_banner():
    print("""
╔══════════════════════════════════════════════════════════════╗
║         OBSERVATORIO DEMOCRÁTICO — Pipeline de Datos         ║
║                  Estándar de Datos v1.0                      ║
╚══════════════════════════════════════════════════════════════╝
""")


def print_summary(results: list[dict], start_time: datetime):
    """Imprime el resumen final de ejecución."""
    elapsed = (datetime.now(CR_TZ) - start_time).total_seconds()

    total_valid = sum(r.get("total_valid", 0) for r in results if r.get("status") == "OK")
    total_discarded = sum(r.get("total_discarded", 0) for r in results if r.get("status") == "OK")
    ok_count = sum(1 for r in results if r.get("status") == "OK")
    error_count = sum(1 for r in results if r.get("status") == "ERROR")

    print("\n" + "═" * 60)
    print("  RESUMEN DE EJECUCIÓN")
    print("═" * 60)
    print(f"  Scrapers ejecutados : {len(results)}")
    print(f"  Exitosos            : {ok_count}")
    print(f"  Con errores         : {error_count}")
    print(f"  Artículos válidos   : {total_valid}")
    print(f"  Artículos descart.  : {total_discarded}")
    print(f"  Tiempo total        : {elapsed:.1f}s")
    print("═" * 60)

    print("\n  Detalle por fuente:")
    print("  " + "-" * 55)
    for r in results:
        status_icon = "✓" if r.get("status") == "OK" else "✗"
        if r.get("status") == "OK":
            print(
                f"  {status_icon} {r['source']:<25} "
                f"válidos={r.get('total_valid', 0):>5}  "
                f"descart.={r.get('total_discarded', 0):>4}"
            )
        else:
            print(f"  {status_icon} {r['source']:<25} ERROR: {r.get('error', 'desconocido')}")
    print()


def save_execution_report(results: list[dict], log_dir: str):
    """Guarda el reporte de ejecución como JSON."""
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    date_str = datetime.now(CR_TZ).strftime("%Y%m%d_%H%M%S")
    report_path = os.path.join(log_dir, f"execution_report_{date_str}.json")

    report = {
        "execution_date": datetime.now(CR_TZ).strftime("%Y-%m-%d %H:%M:%S"),
        "scrapers_run": len(results),
        "results": results,
    }

    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"  Reporte guardado: {report_path}")


def main():
    print_banner()

    parser = argparse.ArgumentParser(
        description="Orquestador de scrapers — Observatorio Democrático"
    )
    parser.add_argument(
        "--only",
        type=str,
        nargs="+",
        metavar="SCRAPER",
        help="Ejecutar solo los scrapers indicados (ej: --only elperiodicocr nacion)",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="Listar todos los scrapers disponibles y salir",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="output",
        help="Directorio de salida para los CSV (default: output)",
    )
    parser.add_argument(
        "--logs",
        type=str,
        default="logs",
        help="Directorio para logs (default: logs)",
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Modo prueba: ejecuta versión reducida (solo scrapers que lo soporten)",
    )

    args = parser.parse_args()

    # Listar scrapers disponibles
    if args.list:
        print("Scrapers disponibles:")
        for name in SCRAPERS_REGISTRY:
            module, cls = SCRAPERS_REGISTRY[name]
            print(f"  - {name:<25} ({module}.{cls})")
        sys.exit(0)

    # Determinar qué scrapers ejecutar
    if args.only:
        to_run = []
        for name in args.only:
            if name not in SCRAPERS_REGISTRY:
                print(f"  ADVERTENCIA: Scraper '{name}' no encontrado en el registro.")
            else:
                to_run.append(name)
        if not to_run:
            print("  No hay scrapers válidos para ejecutar.")
            sys.exit(1)
    else:
        to_run = list(SCRAPERS_REGISTRY.keys())

    print(f"  Scrapers a ejecutar: {', '.join(to_run)}")
    print(f"  Modo prueba        : {'SÍ' if args.test else 'No'}")
    print(f"  Directorio salida  : {args.output}/")
    print(f"  Directorio logs    : {args.logs}/\n")

    start_time = datetime.now(CR_TZ)
    results = []

    for i, name in enumerate(to_run):
        print(f"  [{i+1}/{len(to_run)}] Iniciando: {name}")
        result = run_scraper(name, output_dir=args.output, log_dir=args.logs, test_mode=args.test)
        results.append(result)

        if result.get("status") == "OK":
            print(
                f"        → {result.get('total_valid', 0)} artículos válidos, "
                f"{result.get('total_discarded', 0)} descartados"
            )
        else:
            print(f"        → ERROR: {result.get('error', 'desconocido')}")

    # Reporte final
    print_summary(results, start_time)
    save_execution_report(results, args.logs)


if __name__ == "__main__":
    main()