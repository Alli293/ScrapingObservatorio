"""
health_check.py
───────────────
Verificación liviana de cada sitio antes de lanzar el scraper completo.
Usa requests (sin Playwright) para minimizar tiempo y recursos.

No verifica selectores CSS profundos — solo accesibilidad básica.

Uso independiente:
    python health_check.py                        # verifica todos
    python health_check.py teletica elperiodicocr # verifica específicos
"""

import requests
import time
import sys
from datetime import datetime, timezone, timedelta

CR_TZ            = timezone(timedelta(hours=-6))
TIMEOUT_S        = 10      # segundos máximos por request
MIN_HTML_BYTES   = 5_000   # respuesta mínima esperada (HTML vacío = señal roja)
MAX_RESPONSE_S   = 8.0     # si tarda más de esto, lo marcamos lento

# ── URL de verificación por scraper ──────────────────────────────────────────
# Solo la página principal de listado — no artículos individuales.
HEALTH_URLS: dict[str, str] = {
    "elperiodicocr":     "https://elperiodicocr.com",
    "lareaccioncr":      "https://lareaccioncr.com",
    "larevistacr":       "https://larevistacr.com",
    "latejacr":          "https://lateja.cr",
    "lavozdegoicoechea": "https://lavozdegoicoechea.info",
    "monumental":        "https://www.monumental.co.cr",
    "mundiario":         "https://www.mundiario.com",
    "ncrnoticias":       "https://www.ncrnoticias.com",
    "noticiasenlineacr": "https://www.noticiasenlineacr.com",
    "costaricastar":     "https://www.costaricastar.com",
    "genteopa":          "https://genteopa.com",
    "pulsocr":           "https://pulsocr.com",
    "puroperiodismo":    "https://puroperiodismo.com",
    "repretel":          "https://repretel.com/noticias",
    "rumboeconomico":    "https://rumboeconomico.net",
    "sinartdigital":     "https://sinartdigital.com",
    "telediario":        "https://telediario.cr",
    "teletica":          "https://teletica.com/noticias",
    "theglobalcr":       "https://theglobalcr.com",
    "ticotimes":         "https://ticotimes.net",
    "trivisioncr":       "https://trivisioncr.com",
    "vozdeguanacaste":   "https://vozdeguanacaste.com",
    "ticosland":         "https://ticosland.com",
    "puntarenasseoye":   "https://puntarenasseoye.com",
    "caribeactual":      "https://caribeactual.com",
    "presidencia":       "https://www.presidencia.go.cr/noticias",
    # WordPress sites
    "anexioncr":         "https://anexioncr.com",
    "guanacastealaaltura": "https://guanacastealaaltura.com",
    "periodicomensaje":  "https://periodicomensaje.com",
    "radiolapampa":      "https://radiolapampa.com",
    "tamarindonews":     "https://tamarindonews.com",
    "yambaradio":        "https://yambaradio.com",
    "miprensacr":        "https://miprensacr.com",
    "radiopuertotv":     "https://radiopuertotv.com",
    "tvsur":             "https://tvsur.cr",
    "ustedseinforma":    "https://ustedseinforma.com",
    "adiariocr":         "https://adiariocr.com",
    "actualidaddeloeste":"https://actualidaddeloeste.com",
    "alajuelitahoy":     "https://alajuelitahoy.com",
    "alajuelitasoy":     "https://alajuelitasoy.com",
    "buzonderodrigo":    "https://buzonderodrigo.com",
    "elcolectivo506":    "https://elcolectivo506.com",
    "elmonitorcr":       "https://elmonitorcr.com",
    "elmundo":           "https://elmundo.cr",
    "enlamira":          "https://enlamira.com",
    # Legacy
    "acontecercr":       "https://acontecercr.com",
    "eljornalcr":        "https://eljornalcr.com",
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}


# ─────────────────────────────────────────────────────────────────────────────
def check_one(source: str) -> dict:
    """
    Verifica un sitio. Retorna:
        {
            "source":    str,
            "ok":        bool,
            "status_code": int | None,
            "duration_s":  float,
            "reason":    str,
            "slow":      bool,
        }
    """
    url = HEALTH_URLS.get(source)
    if not url:
        return {
            "source": source, "ok": True,
            "status_code": None, "duration_s": 0,
            "reason": "sin URL de health check (omitiendo)", "slow": False,
        }

    t0 = time.time()
    try:
        resp = requests.get(url, timeout=TIMEOUT_S, headers=HEADERS, allow_redirects=True)
        duration = time.time() - t0
        slow     = duration > MAX_RESPONSE_S

        if resp.status_code >= 400:
            return {
                "source": source, "ok": False,
                "status_code": resp.status_code, "duration_s": round(duration, 2),
                "reason": f"HTTP {resp.status_code}", "slow": slow,
            }

        if len(resp.content) < MIN_HTML_BYTES:
            return {
                "source": source, "ok": False,
                "status_code": resp.status_code, "duration_s": round(duration, 2),
                "reason": f"respuesta demasiado corta ({len(resp.content)} bytes)",
                "slow": slow,
            }

        return {
            "source": source, "ok": True,
            "status_code": resp.status_code, "duration_s": round(duration, 2),
            "reason": "ok", "slow": slow,
        }

    except requests.exceptions.ConnectionError:
        return {
            "source": source, "ok": False,
            "status_code": None, "duration_s": round(time.time() - t0, 2),
            "reason": "conexión rechazada / DNS no resuelve", "slow": False,
        }
    except requests.exceptions.Timeout:
        return {
            "source": source, "ok": False,
            "status_code": None, "duration_s": TIMEOUT_S,
            "reason": f"timeout después de {TIMEOUT_S}s", "slow": True,
        }
    except Exception as e:
        return {
            "source": source, "ok": False,
            "status_code": None, "duration_s": round(time.time() - t0, 2),
            "reason": str(e), "slow": False,
        }


def check_all(sources: list[str] | None = None) -> dict[str, dict]:
    """
    Verifica todos los sitios (o los indicados) en secuencia.
    Retorna dict {source: resultado}.
    """
    targets = sources or list(HEALTH_URLS.keys())
    results = {}
    for src in targets:
        results[src] = check_one(src)
    return results


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────
def _print_results(results: dict):
    ok_count   = sum(1 for r in results.values() if r["ok"])
    fail_count = len(results) - ok_count
    slow_count = sum(1 for r in results.values() if r.get("slow"))

    print(f"\n{'─'*70}")
    print(f"  HEALTH CHECK — {datetime.now(CR_TZ).strftime('%Y-%m-%d %H:%M:%S CR')}")
    print(f"  Sitios verificados: {len(results)}  ✓ {ok_count}  ✗ {fail_count}  ⚠ lentos: {slow_count}")
    print(f"{'─'*70}")

    for src, r in sorted(results.items()):
        icon  = "✓" if r["ok"] else "✗"
        slow  = " ⚠LENTO" if r.get("slow") else ""
        code  = f"[{r['status_code']}]" if r["status_code"] else "[---]"
        print(
            f"  {icon} {src:<25} {code:^7} "
            f"{r['duration_s']:>5.1f}s  {r['reason']}{slow}"
        )
    print(f"{'─'*70}\n")


if __name__ == "__main__":
    sources = sys.argv[1:] if len(sys.argv) > 1 else None
    print("  Ejecutando health check... (sin Playwright, solo HTTP)")
    results = check_all(sources)
    _print_results(results)
