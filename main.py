"""
main.py
Orquestador principal del Observatorio Democrático.

Ejecuta todos los scrapers registrados de forma secuencial,
consolida los resultados y genera un reporte de ejecución.

Uso:
    python main.py
    python main.py --only elperiodicocr 
    python main.py --list
    python main.py --only elperiodicocr --test
"""

import argparse
import sys
import os
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
import importlib
import inspect

# Agregar el directorio raíz al path para importaciones
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# -----------------------------------------------------------------------
# REGISTRO DE SCRAPERS
# -----------------------------------------------------------------------
SCRAPERS_REGISTRY = {
    ##Alli
    "elperiodicocr": ("scrapers.elperiodicocr", "ElPeriodicoCRScraper"),
    "lareaccioncr":  ("scrapers.lareaccioncr",  "LaReaccionCRScraper"),
    "larevistacr":   ("scrapers.larevistacr",   "LaRevistaCRScraper"),
    "latejacr":      ("scrapers.latejacr",      "LaTejaCRScraper"),
    "lavozdegoicoechea": ("scrapers.lavozdegoicoechea", "LaVozDeGoicoecheaScraper"),
    "monumental":        ("scrapers.monumental",        "MonumentalScraper"),
    "mundiario":         ("scrapers.mundiario",         "MundiarioCRScraper"),
    "ncrnoticias":       ("scrapers.ncrnoticias",       "NCRNoticiasScraper"),
    "noticiasenlineacr": ("scrapers.noticiasenlineacr", "NoticiasEnLineaCRScraper"),
    "costaricastar":     ("scrapers.costaricastar",     "CostaRicaStarScraper"),
    "genteopa":          ("scrapers.genteopa",          "GenteOPAScraper"),
    "pulsocr":           ("scrapers.pulsocr",           "PulsoCRScraper"),
    "puroperiodismo":    ("scrapers.puroperiodismo",    "PuroPeriodismoScraper"),
    "repretel":          ("scrapers.repretel",          "RepretelScraper"),
    "rumboeconomico":    ("scrapers.rumboeconomico",    "RumboEconomicoScraper"),
    "sinartdigital":     ("scrapers.sinartdigital",     "SinartDigitalScraper"),
    "telediario":        ("scrapers.telediario",        "TelediarioCRScraper"),
    "teletica":          ("scrapers.teletica",          "TeleticaScraper"),
    "theglobalcr":       ("scrapers.theglobalcr",       "TheGlobalCRScraper"),
    "ticotimes":         ("scrapers.ticotimes",         "TicoTimesScraper"),
    "trivisioncr":       ("scrapers.trivisioncr",       "TrivisionCRScraper"),
    #Gre
    "anexioncr": (
        "scrapers.wordpress_sites",
        "AnexionCRScraper"
    ),

    "guanacastealaaltura": (
        "scrapers.wordpress_sites",
        "GuanacasteALaAlturaScraper"
    ),   
    
    "periodicomensaje": (
        "scrapers.wordpress_sites",
        "PeriodicoMensajeScraper"
    ),
    
    "radiolapampa": (
        "scrapers.wordpress_sites",
        "RadioLaPampaScraper"
    ),

    "tamarindonews": (
        "scrapers.wordpress_sites",
        "TamarindoNewsScraper"
    ),

    "yambaradio": (
        "scrapers.wordpress_sites",
        "YambaRadioScraper"
    ),

    "miprensacr": (
        "scrapers.wordpress_sites",
        "MiPrensaCRScraper"
    ),

    "radiopuertotv": (
        "scrapers.wordpress_sites",
        "RadioPuertoTVScraper"
    ),

    "tvsur": (
        "scrapers.wordpress_sites",
        "TVSurScraper"
    ),

    "ustedseinforma": (
        "scrapers.wordpress_sites",
        "UstedSeInformaScraper"
    ),

    "adiariocr": (
        "scrapers.wordpress_sites",
        "ADiarioCRScraper"
    ),

    "actualidaddeloeste": (
        "scrapers.wordpress_sites",
        "ActualidadDelOesteScraper"
    ),

    "alajuelitahoy": (
        "scrapers.wordpress_sites",
        "AlajuelitaHoyScraper"
    ),

    "alajuelitasoy": (
        "scrapers.wordpress_sites",
        "AlajuelitaSoyScraper"
    ),

    "buzonderodrigo": (
        "scrapers.wordpress_sites",
        "BuzonDeRodrigoScraper"
    ),

    "elcolectivo506": (
        "scrapers.wordpress_sites",
        "ElColectivo506Scraper"
    ),

    "elmonitorcr": (
        "scrapers.wordpress_sites",
        "ElMonitorCRScraper"
    ),

    "elmundo": (
        "scrapers.wordpress_sites",
        "ElMundoScraper"
    ),

    "enlamira": (
        "scrapers.wordpress_sites",
        "EnLaMiraScraper"
    ),  
    
    
    # Legacy / Colab
    #Cami
    "acontecercr": ("scrapers.acontecercr", "AcontecerCRScraper"),
    "eljornalcr":  ("scrapers.eljornal",    "ElJornalCRScraper"),

    # Scrapers adicionales detectados en scrapers/
    "caribeactual": ("scrapers.caribeactual_scraper", "CarribeActualScraper"),
    "presidencia": ("scrapers.presidencia_scraper", "PresidenciaScraper"),
    "puntarenasseoye": ("scrapers.puntarenasseoye", "PuntarenasSeOyeScraper"),
    "ticosland": ("scrapers.ticosland", "TicosLandScraper"),
    "vozdeguanacaste": ("scrapers.vozdeguanacaste", "VozDeGuanacaste"),
    "observatorio_democratico": ("scrapers.observatorio_democratico", "ObservatorioDemocraticoScraper"),
    "acontecer_cr": ("scrapers.acontecer_cr", "AcontecerCrScraper"),
    "alajuela_digital": ("scrapers.alajuela_digital", "AlajuelaDigitalScraper"),
    "amprensa": ("scrapers.amprensa", "AmprensaScraper"),
    "crc_89_1": ("scrapers.crc_89_1", "CRC891Scraper"),
    "crhoy": ("scrapers.crhoy", "CrhoyScraper"),
    "diarioextra": ("scrapers.diarioextra", "DiarioExtraScraper"),
    "digital506": ("scrapers.digital506", "Digital506Scraper"),
    "el_financiero": ("scrapers.el_financiero", "ElFinancieroScraper"),
    "el_jilguero": ("scrapers.el_jilguero", "ElJilgueroScraper"),
    "el_jornal": ("scrapers.el_jornal", "ElJornalScraper"),
    "el_mundo": ("scrapers.el_mundo", "ElMundoScraper"),
    "el_observador": ("scrapers.el_observador", "ElObservadorScraper"),
    "el_seminario": ("scrapers.el_seminario", "ElSeminarioScraper"),
    "el_sol_de_occidente": ("scrapers.el_sol_de_occidente", "ElSolDeOccidenteScraper"),
    "eldelfino": ("scrapers.eldelfino", "ElDelfinoScraper"),
    "elnortehoy": ("scrapers.elnortehoy", "ElNorteHoyScraper"),
    "lanacion": ("scrapers.lanacion", "LaNacionScraper"),
    "larepublica": ("scrapers.larepublica", "LaRepublicaScraper"),
    "noticias_la_garita_costa_rica": ("scrapers.noticias_la_garita_costa_rica", "NoticiasLaGaritaCostaRicaScraper"),
    "periodico_el_mundo": ("scrapers.periodico_el_mundo", "PeriodicoElMundoScraper"),
    "periodico_mi_tierra": ("scrapers.periódico_mi_tierra", "PeriodicoMiTierraScraper"),
    "sancarlosdigital": ("scrapers.sancarlosdigital", "SancarlosDigitalScraper"),
    "seminario": ("scrapers.seminario", "SeminarioScraper"),
}

CR_TZ = timezone(timedelta(hours=-6))


# -----------------------------------------------------------------------
# EJECUCIÓN DE SCRAPERS
# -----------------------------------------------------------------------
def run_scraper(
    name: str,
    output_dir: str = "output",
    log_dir: str = "logs",
    test_mode: bool = False,
) -> dict:
    """Carga y ejecuta un scraper por nombre."""

    if name not in SCRAPERS_REGISTRY:
        return {
            "source": name,
            "status": "ERROR",
            "error": f"Scraper '{name}' no registrado"
        }

    module_path, class_name = SCRAPERS_REGISTRY[name]

    original_cwd = os.getcwd()

    try:

        # -------------------------------------------------
        # PREPARAR OUTPUT
        # -------------------------------------------------
        Path(output_dir).mkdir(parents=True, exist_ok=True)

        # Cambiar temporalmente al output/
        os.chdir(output_dir)

        # -------------------------------------------------
        # IMPORTAR MÓDULO
        # -------------------------------------------------
        module = importlib.import_module(module_path)

        # -------------------------------------------------
        # CASO 1:
        # SCRAPER MODERNO BASADO EN CLASE
        # -------------------------------------------------
        if hasattr(module, class_name):

            ScraperClass = getattr(module, class_name)

            init_params = inspect.signature(
                ScraperClass.__init__
            ).parameters

            if "test_mode" in init_params:

                scraper = ScraperClass(
                    output_dir=output_dir,
                    log_dir=log_dir,
                    test_mode=test_mode
                )

            else:

                if test_mode:
                    print(
                        f"        ⚠ {name} no tiene modo prueba, ejecutando normal"
                    )

                scraper = ScraperClass(
                    output_dir=output_dir,
                    log_dir=log_dir
                )

            result = scraper.run()
            return result

        # -------------------------------------------------
        # CASO 2:
        # SCRIPT LEGACY / COLAB
        # -------------------------------------------------
        else:

            print(
                f"        ⚠ {name} ejecutado como script legacy"
            )

            # Detectar DataFrame automáticamente
            total_valid = 0

            if hasattr(module, "df"):
                try:
                    total_valid = len(module.df)
                except:
                    pass

            return {
                "source": name,
                "status": "OK",
                "total_valid": total_valid,
                "total_discarded": 0,
            }

    except ImportError as e:

        return {
            "source": name,
            "status": "ERROR",
            "error": f"Error de importación: {e}"
        }

    except Exception as e:

        return {
            "source": name,
            "status": "ERROR",
            "error": str(e)
        }

    finally:
        try:
            os.chdir(original_cwd)
        except Exception:
            pass


# -----------------------------------------------------------------------
# UI
# -----------------------------------------------------------------------
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

    total_valid = sum(
        r.get("total_valid", 0)
        for r in results
        if r.get("status") == "OK"
    )

    total_discarded = sum(
        r.get("total_discarded", 0)
        for r in results
        if r.get("status") == "OK"
    )

    ok_count = sum(
        1 for r in results
        if r.get("status") == "OK"
    )

    error_count = sum(
        1 for r in results
        if r.get("status") == "ERROR"
    )

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

            print(
                f"  {status_icon} {r['source']:<25} "
                f"ERROR: {r.get('error', 'desconocido')}"
            )

    print()


# -----------------------------------------------------------------------
# REPORTES
# -----------------------------------------------------------------------
def save_execution_report(results: list[dict], log_dir: str):
    """Guarda el reporte de ejecución como JSON."""

    Path(log_dir).mkdir(parents=True, exist_ok=True)

    date_str = datetime.now(CR_TZ).strftime("%Y%m%d_%H%M%S")

    report_path = os.path.join(
        log_dir,
        f"execution_report_{date_str}.json"
    )

    report = {
        "execution_date": datetime.now(CR_TZ).strftime("%Y-%m-%d %H:%M:%S"),
        "scrapers_run": len(results),
        "results": results,
    }

    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"  Reporte guardado: {report_path}")


# -----------------------------------------------------------------------
# MAIN
# -----------------------------------------------------------------------
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
        help="Ejecutar solo scrapers específicos"
    )

    parser.add_argument(
        "--list",
        action="store_true",
        help="Listar scrapers disponibles"
    )

    parser.add_argument(
        "--output",
        type=str,
        default="output",
        help="Directorio de salida"
    )

    parser.add_argument(
        "--logs",
        type=str,
        default="logs",
        help="Directorio de logs"
    )

    parser.add_argument(
        "--test",
        action="store_true",
        help="Modo prueba"
    )

    args = parser.parse_args()

    # -------------------------------------------------
    # LISTAR SCRAPERS
    # -------------------------------------------------
    if args.list:

        print("Scrapers disponibles:")

        for name in SCRAPERS_REGISTRY:

            module, cls = SCRAPERS_REGISTRY[name]

            print(
                f"  - {name:<25} ({module}.{cls})"
            )

        sys.exit(0)

    # -------------------------------------------------
    # DETERMINAR SCRAPERS A EJECUTAR
    # -------------------------------------------------
    if args.only:

        to_run = []

        for name in args.only:

            if name not in SCRAPERS_REGISTRY:

                print(
                    f"  ADVERTENCIA: Scraper '{name}' no encontrado."
                )

            else:

                to_run.append(name)

        if not to_run:

            print("  No hay scrapers válidos.")
            sys.exit(1)

    else:

        to_run = list(SCRAPERS_REGISTRY.keys())

    print(f"  Scrapers a ejecutar: {', '.join(to_run)}")
    print(f"  Modo prueba        : {'SÍ' if args.test else 'No'}")
    print(f"  Directorio salida  : {args.output}/")
    print(f"  Directorio logs    : {args.logs}/\n")

    start_time = datetime.now(CR_TZ)

    results = []

    # -------------------------------------------------
    # EJECUTAR SCRAPERS
    # -------------------------------------------------
    for i, name in enumerate(to_run):

        print(f"  [{i+1}/{len(to_run)}] Iniciando: {name}")

        try:
            result = run_scraper(
                name,
                output_dir=args.output,
                log_dir=args.logs,
                test_mode=args.test
            )
        except Exception as e:
            result = {
                "source": name,
                "status": "ERROR",
                "error": str(e)
            }

        results.append(result)

        if result.get("status") == "OK":

            print(
                f"        → {result.get('total_valid', 0)} artículos válidos, "
                f"{result.get('total_discarded', 0)} descartados"
            )

        else:

            print(
                f"        → ERROR: {result.get('error', 'desconocido')}"
            )

    # -------------------------------------------------
    # RESUMEN FINAL
    # -------------------------------------------------
    print_summary(results, start_time)

    save_execution_report(results, args.logs)


if __name__ == "__main__":
    main()