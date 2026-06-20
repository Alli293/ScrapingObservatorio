"""
corpus_builder.py
─────────────────
Agente Actualizador — Fase 1: Constructor del corpus maestro.

Lee todos los CSVs individuales de output/ y los consolida en un
único archivo corpus maestro versionado, sin duplicados por URL.

Uso:
    python corpus_builder.py                         # usa output/ y corpus/
    python corpus_builder.py --output output/        # directorio de CSVs
    python corpus_builder.py --corpus data/master/   # directorio destino
    python corpus_builder.py --dry-run               # muestra stats sin guardar
"""

import os
import sys
import argparse
import pandas as pd
from pathlib import Path
from datetime import datetime, timezone, timedelta

CR_TZ = timezone(timedelta(hours=-6))

# Schema v1.0 obligatorio
REQUIRED_COLUMNS = [
    "source", "url", "title", "publication_date",
    "scraping_date", "section", "full_text", "language",
]
SEPARATOR = "|"


# ─────────────────────────────────────────────────────────────────────────────
def _log(msg: str):
    ts = datetime.now(CR_TZ).strftime("%H:%M:%S")
    print(f"  [{ts}] {msg}")


def _find_csvs(output_dir: str) -> list[Path]:
    """Encuentra todos los CSVs en el directorio de output."""
    p = Path(output_dir)
    if not p.exists():
        _log(f"ERROR: directorio {output_dir} no existe")
        sys.exit(1)
    csvs = sorted(p.glob("*.csv"))
    # Excluir archivos de descartados
    csvs = [f for f in csvs if "_discarded" not in f.name]
    return csvs


def _read_csv_safe(path: Path) -> pd.DataFrame | None:
    """Lee un CSV con manejo de errores."""
    try:
        df = pd.read_csv(
            path,
            sep=SEPARATOR,
            dtype=str,
            on_bad_lines="skip",
            encoding="utf-8-sig",
        )
        # Verificar columnas mínimas
        missing = [c for c in ["source", "url", "full_text"] if c not in df.columns]
        if missing:
            _log(f"  ⚠ {path.name} — columnas faltantes: {missing} — omitiendo")
            return None
        return df
    except Exception as e:
        _log(f"  ✗ {path.name} — error de lectura: {e}")
        return None


def build_corpus(
    output_dir: str = "output",
    corpus_dir: str = "corpus",
    dry_run:    bool = False,
) -> dict:
    """
    Construye el corpus maestro consolidado.

    Retorna un dict con estadísticas de la construcción.
    """
    print("""
╔══════════════════════════════════════════════════════════════╗
║      OBSERVATORIO DEMOCRÁTICO — Corpus Builder               ║
╚══════════════════════════════════════════════════════════════╝
""")

    # ── 1. Encontrar CSVs ────────────────────────────────────────────────────
    csvs = _find_csvs(output_dir)
    _log(f"CSVs encontrados: {len(csvs)}")
    if not csvs:
        _log("ERROR: no hay CSVs en el directorio de output")
        sys.exit(1)

    # ── 2. Leer y consolidar ─────────────────────────────────────────────────
    frames     = []
    read_ok    = 0
    read_error = 0
    total_raw  = 0

    for csv_path in csvs:
        df = _read_csv_safe(csv_path)
        if df is None:
            read_error += 1
            continue
        _log(f"  ✓ {csv_path.name:<45} {len(df):>6} filas")
        total_raw += len(df)
        frames.append(df)
        read_ok += 1

    if not frames:
        _log("ERROR: ningún CSV pudo leerse correctamente")
        sys.exit(1)

    _log(f"\nCSVs leídos: {read_ok} OK, {read_error} con error")
    _log(f"Total filas brutas: {total_raw:,}")

    # ── 3. Concatenar ────────────────────────────────────────────────────────
    corpus = pd.concat(frames, ignore_index=True)

    # ── 4. Eliminar duplicados por URL ───────────────────────────────────────
    antes      = len(corpus)
    corpus     = corpus.drop_duplicates(subset=["url"], keep="first")
    duplicados = antes - len(corpus)
    _log(f"Duplicados eliminados por URL: {duplicados:,}")

    # ── 5. Eliminar filas sin full_text ──────────────────────────────────────
    corpus = corpus[corpus["full_text"].notna() & (corpus["full_text"].str.strip() != "") & (corpus["full_text"] != "NULL")]
    sin_texto = antes - duplicados - len(corpus)
    if sin_texto > 0:
        _log(f"Filas sin full_text eliminadas: {sin_texto:,}")

    # ── 6. Eliminar filas sin URL ────────────────────────────────────────────
    corpus = corpus[corpus["url"].notna() & (corpus["url"].str.strip() != "") & (corpus["url"] != "NULL")]

    # ── 7. Ordenar por fecha descendente ────────────────────────────────────
    if "publication_date" in corpus.columns:
        corpus = corpus.sort_values("publication_date", ascending=False, na_position="last")

    corpus = corpus.reset_index(drop=True)

    # ── 8. Estadísticas por fuente ───────────────────────────────────────────
    print(f"\n{'─'*60}")
    print(f"  {'FUENTE':<25} {'ARTÍCULOS':>10}")
    print(f"{'─'*60}")
    by_source = corpus.groupby("source").size().sort_values(ascending=False)
    for source, count in by_source.items():
        print(f"  {source:<25} {count:>10,}")
    print(f"{'─'*60}")
    print(f"  {'TOTAL':<25} {len(corpus):>10,}")
    print(f"{'─'*60}\n")

    stats = {
        "csvs_leidos":    read_ok,
        "csvs_error":     read_error,
        "total_raw":      total_raw,
        "duplicados":     duplicados,
        "total_final":    len(corpus),
        "fuentes":        int(corpus["source"].nunique()),
    }

    if dry_run:
        _log("Modo dry-run — no se guarda ningún archivo")
        return stats

    # ── 9. Guardar corpus versionado ─────────────────────────────────────────
    Path(corpus_dir).mkdir(parents=True, exist_ok=True)
    fecha     = datetime.now(CR_TZ).strftime("%Y%m%d")
    version   = _next_version(corpus_dir, fecha)
    filename  = f"corpus_observatorio_v{version}_{fecha}.csv"
    out_path  = os.path.join(corpus_dir, filename)

    corpus.to_csv(out_path, sep=SEPARATOR, index=False, encoding="utf-8")

    _log(f"Corpus guardado: {out_path}")
    _log(f"Versión        : v{version}")
    _log(f"Total artículos: {len(corpus):,}")
    _log(f"Fuentes        : {stats['fuentes']}")

    stats["output_file"] = out_path
    stats["version"]     = version

    return stats


def _next_version(corpus_dir: str, fecha: str) -> int:
    """Determina el siguiente número de versión del corpus."""
    existing = list(Path(corpus_dir).glob(f"corpus_observatorio_v*_{fecha}.csv"))
    if not existing:
        return 1
    versions = []
    for f in existing:
        try:
            v = int(f.stem.split("_v")[1].split("_")[0])
            versions.append(v)
        except Exception:
            pass
    return max(versions) + 1 if versions else 1


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="Corpus Builder — Observatorio Democrático"
    )
    parser.add_argument("--output",  default="output",
                        help="Directorio con los CSVs individuales")
    parser.add_argument("--corpus",  default="corpus",
                        help="Directorio donde se guarda el corpus maestro")
    parser.add_argument("--dry-run", action="store_true",
                        help="Muestra estadísticas sin guardar")

    args = parser.parse_args()

    # Resolver rutas absolutas
    base_dir   = os.path.dirname(os.path.abspath(__file__))
    output_dir = os.path.join(base_dir, args.output) if not os.path.isabs(args.output) else args.output
    corpus_dir = os.path.join(base_dir, args.corpus) if not os.path.isabs(args.corpus) else args.corpus

    build_corpus(
        output_dir = output_dir,
        corpus_dir = corpus_dir,
        dry_run    = args.dry_run,
    )


if __name__ == "__main__":
    main()
