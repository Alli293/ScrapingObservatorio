"""
legacy_adapter.py
─────────────────
Adapter que hace compatibles los scrapers legacy con el pipeline moderno.
Ejecuta cada scraper legacy como subprocess, captura su CSV output
y lo retorna al pipeline sin modificar ningún scraper existente.
"""

import os
import sys
import glob
import subprocess
import pandas as pd

from scrapers.base_scraper import BaseScraper

SEPARATOR = "|"
SCHEMA = ['source', 'url', 'title', 'publication_date',
          'scraping_date', 'section', 'full_text', 'language']

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OBSERVATORIO_SCRIPT = os.path.join(PROJECT_ROOT, "scrapers", "observatorio_democratico.py")

SUBPROCESS_TIMEOUT = 600
TEST_MODE_LIMIT = 20


class LegacyScraperAdapter(BaseScraper):
    """
    Adapter para scrapers legacy procedurales (Tipo 1) y WordPress (Tipo 2).

    Ambos tipos comparten el mismo problema: ejecutan toda su lógica al
    correr el archivo y escriben su propio CSV en disco en vez de retornar
    datos al pipeline. Este adapter corre el script como subprocess
    independiente, localiza el CSV resultante y lo convierte al formato
    estándar (lista de dicts con el schema v1.0) para que BaseScraper.run()
    haga el resto (validación, deduplicación, export).

    Uso:
        adapter = LegacyScraperAdapter(
            source_name="acontecercr",
            script_path="scrapers/acontecercr.py",
            output_dir="output",
            log_dir="logs"
        )
        result = adapter.run()
    """

    def __init__(self, source_name: str, script_path: str,
                 output_dir: str, log_dir: str, test_mode: bool = False):
        self.SOURCE_NAME = source_name
        self.script_path = script_path
        self.test_mode = test_mode
        # Los scrapers WordPress (Tipo 2) no tienen archivo propio: su lógica
        # vive en observatorio_democratico.py::procesar_sitio(). Se detecta
        # automáticamente para no requerir un flag extra en el registro.
        self.is_wordpress = os.path.basename(script_path) == "observatorio_democratico.py"
        super().__init__(output_dir=output_dir, log_dir=log_dir)

    def scrape(self) -> list[dict]:
        # 1. Ejecutar el script legacy como subprocess
        self._run_legacy_script()

        # 2. Buscar el CSV que escribió en disco
        csv_path = self._find_csv()
        if not csv_path:
            self.logger.warning(f"No se encontró CSV de salida para '{self.SOURCE_NAME}'.")
            return []

        # 3. Leerlo con pandas
        df = self._read_csv(csv_path)
        if df.empty:
            self.logger.warning(f"CSV vacío para '{self.SOURCE_NAME}': {csv_path}")
            return []

        # 4. Validar que tiene el schema correcto
        df = self._ensure_schema(df)

        # 5. Limitar en modo prueba
        if self.test_mode:
            df = df.head(TEST_MODE_LIMIT)

        self.logger.info(f"'{self.SOURCE_NAME}': {len(df)} registros leídos desde {csv_path}")
        return df.to_dict('records')

    # ------------------------------------------------------------------
    # Paso 1 — ejecutar el script legacy en un proceso separado
    # ------------------------------------------------------------------

    def _run_legacy_script(self) -> None:
        if self.is_wordpress:
            # observatorio_democratico.py procesa TODOS los sitios de SITES
            # dentro de su main(); se pasa el nombre del sitio como argumento
            # por trazabilidad, aunque el script (sin modificar) no lo lea.
            cmd = [sys.executable, OBSERVATORIO_SCRIPT, self.SOURCE_NAME]
        else:
            cmd = [sys.executable, self.script_path]

        try:
            result = subprocess.run(
                cmd,
                cwd=PROJECT_ROOT,
                capture_output=True,
                text=True,
                timeout=SUBPROCESS_TIMEOUT,
            )

            if result.returncode != 0:
                # Esperado: scripts con `from google.colab import files` fallan
                # al final, después de haber escrito su CSV en disco.
                self.logger.warning(
                    f"'{self.SOURCE_NAME}' subprocess terminó con código "
                    f"{result.returncode} (puede ser normal si el script usa "
                    f"google.colab). stderr: {(result.stderr or '').strip()[-1000:]}"
                )
            else:
                self.logger.info(f"'{self.SOURCE_NAME}' subprocess finalizado correctamente.")

            if result.stdout:
                self.logger.debug(f"'{self.SOURCE_NAME}' stdout: {result.stdout.strip()[-1000:]}")

        except subprocess.TimeoutExpired:
            self.logger.warning(
                f"'{self.SOURCE_NAME}' excedió el timeout de {SUBPROCESS_TIMEOUT}s. "
                "Se intentará leer el CSV ya escrito en disco hasta el momento."
            )

    # ------------------------------------------------------------------
    # Paso 2 — localizar el CSV escrito por el script legacy
    # ------------------------------------------------------------------

    def _find_csv(self) -> str | None:
        output_dir = self.output_dir
        if not os.path.isabs(output_dir):
            output_dir = os.path.join(PROJECT_ROOT, output_dir)

        search_dirs = {PROJECT_ROOT, os.path.join(PROJECT_ROOT, "output"), output_dir}

        candidates = set()
        for directory in search_dirs:
            for pattern in (f"{self.SOURCE_NAME}_*.csv", f"{self.SOURCE_NAME}.csv"):
                candidates.update(glob.glob(os.path.join(directory, pattern)))

        if not candidates:
            return None

        return max(candidates, key=os.path.getmtime)

    # ------------------------------------------------------------------
    # Paso 3 — leer el CSV (separador pipe o coma)
    # ------------------------------------------------------------------

    def _read_csv(self, path: str) -> pd.DataFrame:
        try:
            df = pd.read_csv(path, sep=SEPARATOR, encoding="utf-8-sig")
            if df.shape[1] <= 1:
                df = pd.read_csv(path, sep=",", encoding="utf-8-sig")
        except Exception:
            df = pd.read_csv(path, sep=",", encoding="utf-8-sig")
        return df

    # ------------------------------------------------------------------
    # Paso 4 — validar/normalizar contra el schema v1.0
    # ------------------------------------------------------------------

    def _ensure_schema(self, df: pd.DataFrame) -> pd.DataFrame:
        for col in SCHEMA:
            if col not in df.columns:
                df[col] = "NULL"
        return df.fillna("NULL")


def get_legacy_registry() -> dict:
    """
    Retorna el registro de todos los scrapers legacy con su script_path.
    Usar para registrar en SCRAPERS_REGISTRY del main.py.

    - Tipo 1 (procedurales, con o sin Colab): apuntan a su propio archivo
      dentro de scrapers/.
    - Tipo 2 (WordPress, ex wordpress_sites.py): todos apuntan a
      observatorio_democratico.py; LegacyScraperAdapter detecta esto
      automáticamente vía os.path.basename(script_path).
    """
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    scrapers_dir = os.path.join(base, "scrapers")
    wordpress_script = os.path.join(scrapers_dir, "observatorio_democratico.py")

    return {
        # ---- Tipo 1: scripts procedurales Colab (24) ----
        "acontecercr":                   os.path.join(scrapers_dir, "acontecercr.py"),
        "acontecer_cr":                  os.path.join(scrapers_dir, "acontecer_cr.py"),
        "alajuela_digital":              os.path.join(scrapers_dir, "alajuela_digital.py"),
        "amprensa":                      os.path.join(scrapers_dir, "amprensa.py"),
        "crc_89_1":                      os.path.join(scrapers_dir, "crc_89_1.py"),
        "crhoy":                         os.path.join(scrapers_dir, "crhoy.py"),
        "diarioextra":                   os.path.join(scrapers_dir, "diarioextra.py"),
        "digital506":                    os.path.join(scrapers_dir, "digital506.py"),
        "el_jilguero":                   os.path.join(scrapers_dir, "el_jilguero.py"),
        "el_jornal":                     os.path.join(scrapers_dir, "el_jornal.py"),
        "el_observador":                 os.path.join(scrapers_dir, "el_observador.py"),
        "el_sol_de_occidente":           os.path.join(scrapers_dir, "el_sol_de_occidente.py"),
        "elnortehoy":                    os.path.join(scrapers_dir, "elnortehoy.py"),
        "noticias_la_garita_costa_rica": os.path.join(scrapers_dir, "noticias_la_garita_costa_rica.py"),
        "periodico_mi_tierra":           os.path.join(scrapers_dir, "periódico_mi_tierra.py"),
        "sancarlosdigital":              os.path.join(scrapers_dir, "sancarlosdigital.py"),
        "el_financiero":                 os.path.join(scrapers_dir, "el_financiero.py"),
        "el_mundo":                      os.path.join(scrapers_dir, "el_mundo.py"),
        "el_seminario":                  os.path.join(scrapers_dir, "el_seminario.py"),
        "eldelfino":                     os.path.join(scrapers_dir, "eldelfino.py"),
        "lanacion":                      os.path.join(scrapers_dir, "lanacion.py"),
        "larepublica":                   os.path.join(scrapers_dir, "larepublica.py"),
        "periodico_el_mundo":            os.path.join(scrapers_dir, "periodico_el_mundo.py"),
        "seminario":                     os.path.join(scrapers_dir, "seminario.py"),

        # ---- Tipo 1: procedural sin Colab ----
        "eljornalcr":                    os.path.join(scrapers_dir, "eljornal.py"),

        # ---- Tipo 2: sitios WordPress, procesados vía observatorio_democratico.py (19) ----
        "anexioncr":           wordpress_script,
        "guanacastealaaltura": wordpress_script,
        "periodicomensaje":    wordpress_script,
        "radiolapampa":        wordpress_script,
        "tamarindonews":       wordpress_script,
        "yambaradio":          wordpress_script,
        "miprensacr":          wordpress_script,
        "radiopuertotv":       wordpress_script,
        "tvsur":               wordpress_script,
        "ustedseinforma":      wordpress_script,
        "adiariocr":           wordpress_script,
        "actualidaddeloeste":  wordpress_script,
        "alajuelitahoy":       wordpress_script,
        "alajuelitasoy":       wordpress_script,
        "buzonderodrigo":      wordpress_script,
        "elcolectivo506":      wordpress_script,
        "elmonitorcr":         wordpress_script,
        "elmundo":             wordpress_script,
        "enlamira":            wordpress_script,
    }
