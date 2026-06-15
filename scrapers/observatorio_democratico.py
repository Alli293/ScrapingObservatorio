# ============================================================
# SCRAPER: Observatorio_Democratico
# ============================================================
#
# REQUISITOS PARA EJECUTAR:
#
# 1. Instalar dependencias Python:
#      pip install requests beautifulsoup4 pandas urllib3
#
# Ejecutar con:
#      python Observatorio_Democratico.py
#
# NOTAS IMPORTANTES:
#   - Este scraper usa la API REST de WordPress (/wp-json/wp/v2/posts)
#     por lo que funciona únicamente con sitios basados en WordPress.
#   - Genera un CSV individual por cada sitio de la lista SITES.
#   - Para limitar la cantidad de páginas descargadas (modo test),
#     cambiar max_pages=None por max_pages=2 en la función main().
#   - Los archivos de salida y el log se guardan en el directorio
#     desde donde se ejecute el script.
# ============================================================

import requests
import re
import datetime
import pandas as pd
from bs4 import BeautifulSoup
import time
import urllib3

# Disable SSL warnings for pages with misconfigured certificates
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# =========================================================
# CONFIGURACIÓN MAESTRA
# =========================================================

# Lista de todos los portales noticiosos requeridos
SITES = [
    {"url": "https://anexioncr.com", "name": "anexioncr"},
    {"url": "https://guanacastealaaltura.com", "name": "guanacastealaaltura"},
    {"url": "https://periodicomensaje.com", "name": "periodicomensaje"},
    {"url": "https://radiolapampa.net", "name": "radiolapampa"},
    {"url": "https://tamarindonews.com", "name": "tamarindonews"},
    {"url": "https://yambaradio.com", "name": "yambaradio"},
    {"url": "https://miprensacr.com", "name": "miprensacr"},
    # {"url": "https://radiobahiapuerto.com", "name": "radiobahiapuerto"}, # Usualmente requiere Playwright, pero intentaremos WP
    {"url": "https://radiopuertotv.net", "name": "radiopuertotv"},
    {"url": "https://tvsur.co.cr", "name": "tvsur"},
    {"url": "https://ustedseinforma.com", "name": "ustedseinforma"},
    {"url": "https://adiariocr.com", "name": "adiariocr"},
    {"url": "https://actualidaddeloeste.com", "name": "actualidaddeloeste"},
    {"url": "https://alajuelitahoy.com", "name": "alajuelitahoy"},
    {"url": "https://alajuelitasoy.com", "name": "alajuelitasoy"},
    {"url": "https://buzonderodrigo.com", "name": "buzonderodrigo"},
    # {"url": "https://canalaltavision.com", "name": "canalaltavision"}, # En caso de que funcione
    {"url": "https://elcolectivo506.com", "name": "elcolectivo506"},
    {"url": "https://elmonitorcr.com", "name": "elmonitorcr"},
    {"url": "https://elmundo.cr", "name": "elmundo"},
    {"url": "https://enlamiracr.com", "name": "enlamira"}
]

# Timezone de Costa Rica
TZ_CR = datetime.timezone(datetime.timedelta(hours=-6))
TIMESTAMP = datetime.datetime.now(TZ_CR).strftime('%Y%m%d_%H%M%S')
LOG_TXT = f"log_master_{TIMESTAMP}.txt"

# Límite absoluto seguro para celdas de Excel (limita a 30,000 caracteres)
MAX_TEXT_LENGTH = 30000

# Limpiador drástico de Emojis que arruinan la codificación
STRICT_PATTERN = re.compile(r'[^\w\s\.,;:!?\-\(\)áéíóúÁÉÍÓÚñÑüÜ"\'/¿¡]', flags=re.UNICODE)

def log_msg(msg):
    with open(LOG_TXT, "a", encoding="utf-8") as f:
        f.write(f"[{datetime.datetime.now(TZ_CR).strftime('%H:%M:%S')}] {msg}\n")
    print(msg)

def clean_extreme(text):
    """
    Rutina blindada contra rupturas de línea en CSV.
    Elimina caracteres de escape ocultos y limita el string.
    """
    if not isinstance(text, str): return ""

    # 1. Quitar HTML
    if '<' in text and '>' in text:
        try:
            soup = BeautifulSoup(text, "html.parser")
            text = soup.get_text(separator=' ')
        except:
            pass

    # 2. Remover Emojis super locos
    text = STRICT_PATTERN.sub('', text)

    # 3. Remover basuras repetitivas de Emojis fallidos (ej. ???)
    text = re.sub(r'\?{2,}\s*', ' ', text)

    # 4. Remover TODO salto de línea, retorno de carro y tabulador (CRÍTICO PARA EXCEL)
    text = text.replace('\r', ' ').replace('\n', ' ').replace('\t', ' ')

    # 5. Escapar las comillas dobles y sencillas que suelen romper CSV si se abren y no cierran
    text = text.replace('"', "'").replace('\u201c', "'").replace('\u201d', "'")

    # 6. Transformar el "pipe" en un guion, ya que usaremos pipe como separador de columnas
    text = text.replace('|', '-')

    # 7. Reducción de espacios extra
    text = re.sub(r'\s+', ' ', text).strip()

    # 8. Limitar para que Excel no colapse al volcar a una celda (Límite Excel: 32,767 caracteres)
    if len(text) > MAX_TEXT_LENGTH:
        text = text[:MAX_TEXT_LENGTH] + "... [truncado]"

    return text

def parse_date(date_str):
    try:
        dt = datetime.datetime.fromisoformat(date_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=TZ_CR)
        return dt.strftime('%Y-%m-%d %H:%M:%S')
    except:
        return datetime.datetime.now(TZ_CR).strftime('%Y-%m-%d %H:%M:%S')

def procesar_sitio(site_dict, max_pages=None):
    base_url = site_dict["url"]
    name = site_dict["name"]

    log_msg(f"\n==============================================")
    log_msg(f"Iniciando Extracción API para: {name.upper()}")
    log_msg(f"Target URL: {base_url}")
    log_msg(f"==============================================")

    session = requests.Session()
    # Headers para mimetizar navegador
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json"
    })

    # 1. Obtener Categorías
    cat_mapping = {}
    try:
        c_url = f"{base_url}/wp-json/wp/v2/categories"
        c_req = session.get(c_url, params={"per_page": 100}, timeout=10, verify=False)
        if c_req.status_code == 200:
            for cat in c_req.json():
                cat_mapping[cat['id']] = cat['name']
        log_msg(f"-> Mapeadas {len(cat_mapping)} categorías.")
    except Exception as e:
        log_msg(f"-> Advertencia: No se pudieron mapear categorías ({e}). Todo irá como 'Noticias'.")

    # 2. Descarga Histórica Recursiva
    dataset = []
    page = 1
    posts_url = f"{base_url}/wp-json/wp/v2/posts"

    while True:
        try:
            resp = session.get(posts_url, params={"per_page": 100, "page": page}, timeout=25, verify=False)

            if resp.status_code != 200:
                if "rest_post_invalid_page_number" in resp.text or resp.status_code == 400:
                    log_msg(f"-> Fin del historial alcanzado en la página {page-1}.")
                else:
                    log_msg(f"-> El sitio rechazó la solicitud (código {resp.status_code}). Abortando sitio.")
                break

            data = resp.json()
            if not data:
                break

            for post in data:
                link = post.get("link", "")
                title_raw = post.get("title", {}).get("rendered", "")
                content_raw = post.get("content", {}).get("rendered", "")
                date_raw = post.get("date", "")

                cats_ids = post.get("categories", [])
                section_raw = "Noticias"
                if cats_ids and len(cat_mapping) > 0:
                    section_raw = cat_mapping.get(cats_ids[0], "Noticias")

                title_clean = clean_extreme(title_raw)
                content_clean = clean_extreme(content_raw)

                if not title_clean and not content_clean:
                    continue

                dataset.append({
                    "source": name,
                    "url": link,
                    "title": title_clean,
                    "publication_date": parse_date(date_raw) if date_raw else "N/A",
                    "scraping_date": datetime.datetime.now(TZ_CR).strftime('%Y-%m-%d %H:%M:%S'),
                    "section": clean_extreme(section_raw),
                    "full_text": content_clean,
                    "language": "es"
                })

            log_msg(f"-> [{name}] Página {page} extraida (+{len(data)} ítems)")

            # Respaldo de seguridad intermedio local
            if page % 10 == 0:
                df_temp = pd.DataFrame(dataset)
                df_temp.to_csv(f"{name}_backup.csv", index=False, encoding='utf-8-sig', sep='|')

            if max_pages and page >= max_pages:
                log_msg(f"-> Límite artificial de test ({max_pages} pags) alcanzado.")
                break

            page += 1
            time.sleep(1)  # Precaución anti-ban

        except requests.exceptions.RequestException as e:
            log_msg(f"-> Falla de conexión crítica en página {page}: {e}. Abortando {name}.")
            break
        except Exception as e:
            log_msg(f"-> Excepción en {name} pag {page}: {e}")
            break

    # 3. Guardado final del CSV por sitio
    if dataset:
        df = pd.DataFrame(dataset)
        df = df.drop_duplicates(subset=['url'])
        df = df[['source', 'url', 'title', 'publication_date', 'scraping_date', 'section', 'full_text', 'language']]

        final_filename = f"{name}_{datetime.datetime.now(TZ_CR).strftime('%Y%m%d')}.csv"
        df.to_csv(final_filename, index=False, encoding='utf-8-sig', sep='|')
        log_msg(f"SUCCESS: {len(df)} registros totales consolidados en {final_filename}")

        # Descarga automática en Google Colab (ignorado fuera de Colab)
        try:
            from google.colab import files
            log_msg(f"-> Forzando descarga automática del archivo {final_filename} al navegador...")
            files.download(final_filename)
        except ImportError:
            pass

    else:
        log_msg(f"WARNING: API vacía o inalcanzable para {name}.")


def main():
    with open(LOG_TXT, "w", encoding="utf-8") as f:
        f.write(f"=== MASTER SCRAPER INICIADO ({TIMESTAMP}) ===\n")

    # IMPORTANTE: max_pages se usa sólo para testear (ej. max_pages=2).
    # Usar max_pages=None para descargar el historial completo.
    import sys

    # Filtro opcional: si se pasa un nombre de sitio como argumento,
    # procesar solo ese sitio. Si no se pasa argumento, procesar todos.
    _site_filter = sys.argv[1] if len(sys.argv) > 1 else None

    for site in SITES:
        if _site_filter and site.get("name", "").lower() != _site_filter.lower():
            continue
        procesar_sitio(site)


if __name__ == "__main__":
    main()
