#!/usr/bin/env python
"""
output_cleaner.py
Valida los archivos CSV generados por ScrapingObservatorio.

Comprueba:
- columnas obligatorias
- ausencia de valores nulos o vacíos
- duplicados por URL
- formato correcto de fechas
- ausencia de HTML en los campos de texto
- longitud mínima de full_text
"""

import argparse
import json
import os
import re
from datetime import datetime
from pathlib import Path

import pandas as pd

REQUIRED_COLUMNS = [
    "source",
    "url",
    "title",
    "publication_date",
    "scraping_date",
    "section",
    "full_text",
    "language",
]
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
MIN_TEXT_LENGTH = 300
HTML_PATTERN = re.compile(r"<[^>]+>")


def load_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(
        path,
        sep="|",
        dtype=str,
        keep_default_na=False,
        na_values=["NULL"],
        encoding="utf-8",
    )
    return df.where(pd.notna(df), None)


def format_issue(issue_type: str, value: str, count: int, details: str = "") -> dict:
    return {
        "type": issue_type,
        "value": value,
        "count": count,
        "details": details,
    }


def validate_file(path: Path) -> dict:
    report = {
        "file": str(path),
        "ok": True,
        "issues": [],
        "counts": {},
    }

    if not path.exists():
        report["ok"] = False
        report["issues"].append(format_issue("missing_file", str(path), 1, "El archivo no existe"))
        return report

    try:
        df = load_csv(path)
    except Exception as exc:
        report["ok"] = False
        report["issues"].append(format_issue("read_error", str(exc), 1, "No se pudo leer el CSV"))
        return report

    missing_columns = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing_columns:
        report["ok"] = False
        report["issues"].append(
            format_issue(
                "missing_columns",
                ", ".join(missing_columns),
                len(missing_columns),
                f"Columnas obligatorias ausentes: {missing_columns}"
            )
        )
        return report

    report["counts"]["rows"] = len(df)
    report["counts"]["columns"] = len(df.columns)

    # Detectar filas con nulos o cadenas vacías en columnas obligatorias
    null_issues = []
    for col in REQUIRED_COLUMNS:
        if df[col].isna().any() or df[col].astype(str).str.strip().eq("").any():
            invalid = df[df[col].isna() | df[col].astype(str).str.strip().eq("")]
            count = len(invalid)
            null_issues.append((col, count))
            report["ok"] = False
            report["issues"].append(
                format_issue(
                    "missing_value",
                    col,
                    count,
                    f"{count} filas con valor nulo o vacío en '{col}'"
                )
            )

    # Duplicados por URL
    if "url" in df.columns:
        duplicate_mask = df["url"].duplicated(keep=False)
        duplicate_count = int(duplicate_mask.sum())
        if duplicate_count:
            report["ok"] = False
            report["issues"].append(
                format_issue(
                    "duplicate_url",
                    "url",
                    duplicate_count,
                    f"{duplicate_count} filas duplicadas en columna 'url'"
                )
            )

    # Validar fechas
    for col in ["publication_date", "scraping_date"]:
        raw_values = df[col].astype(str).fillna("")
        parsed = pd.to_datetime(raw_values, format=DATE_FORMAT, errors="coerce")
        invalid = parsed.isna() & raw_values.ne("")
        count = int(invalid.sum())
        if count:
            bad_values = raw_values[invalid].unique().tolist()[:5]
            report["ok"] = False
            report["issues"].append(
                format_issue(
                    "invalid_date_format",
                    col,
                    count,
                    f"{count} valores no siguen el formato {DATE_FORMAT}; ejemplos: {bad_values}"
                )
            )

    # Validar HTML en texto
    for col in ["title", "section", "full_text"]:
        raw_values = df[col].astype(str).fillna("")
        html_mask = raw_values.str.contains(HTML_PATTERN, na=False)
        count = int(html_mask.sum())
        if count:
            report["ok"] = False
            report["issues"].append(
                format_issue(
                    "html_detected",
                    col,
                    count,
                    f"{count} filas contienen etiquetas HTML en '{col}'"
                )
            )

    # Validar longitud mínima de full_text
    if "full_text" in df.columns:
        length_mask = df["full_text"].astype(str).fillna("").str.len() < MIN_TEXT_LENGTH
        count = int(length_mask.sum())
        if count:
            report["ok"] = False
            report["issues"].append(
                format_issue(
                    "short_full_text",
                    "full_text",
                    count,
                    f"{count} filas con full_text menor a {MIN_TEXT_LENGTH} caracteres"
                )
            )

    report["counts"]["missing_columns"] = len(missing_columns)
    return report


def collect_csv_files(path: Path) -> list[Path]:
    if path.is_file():
        return [path]
    if path.is_dir():
        return sorted(path.glob("*.csv"))
    raise ValueError(f"Ruta desconocida: {path}")


def print_report(report: dict):
    print(f"Validando: {report['file']}")
    print(f"  Resultado: {'OK' if report['ok'] else 'ERROR'}")
    print(f"  Filas: {report['counts'].get('rows', 0)}")
    print(f"  Columnas: {report['counts'].get('columns', 0)}")
    if report["issues"]:
        for issue in report["issues"]:
            print(f"    - {issue['type']} [{issue['value']}]: {issue['details']}")
    print()


def save_report(report: dict, output_dir: Path):
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = output_dir / f"validation_report_{timestamp}.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    return report_path


def main():
    parser = argparse.ArgumentParser(
        description="Valida los CSV de salida generados por ScrapingObservatorio."
    )
    parser.add_argument(
        "path",
        type=str,
        help="Archivo CSV o directorio con archivos CSV a validar"
    )
    parser.add_argument(
        "--report",
        type=str,
        default="logs",
        help="Directorio para guardar el reporte JSON de validación"
    )

    args = parser.parse_args()
    target = Path(args.path)
    output_dir = Path(args.report)

    files = collect_csv_files(target)
    if not files:
        raise SystemExit(f"No se encontraron archivos CSV en: {target}")

    overall = {
        "checked_files": len(files),
        "valid_files": 0,
        "invalid_files": 0,
        "files": [],
    }

    for file_path in files:
        report = validate_file(file_path)
        overall["files"].append(report)
        if report["ok"]:
            overall["valid_files"] += 1
        else:
            overall["invalid_files"] += 1
        print_report(report)

    overall_report_path = save_report(overall, output_dir)
    print(f"Reporte global guardado en: {overall_report_path}")
    print(f"Archivos validados: {overall['checked_files']}")
    print(f"Archivos OK: {overall['valid_files']}")
    print(f"Archivos con errores: {overall['invalid_files']}")

    if overall["invalid_files"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
