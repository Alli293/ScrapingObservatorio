import requests
from bs4 import BeautifulSoup
import pandas as pd
import re
import time
from datetime import datetime
from google.colab import files

# -------------------------------------------------------------
# CONFIGURACIÓN
# -------------------------------------------------------------
BASE_SITE   = 'https://acontecer.co.cr'
API_BASE    = 'https://cms.acontecer.co.cr/wp-json/wp/v2'

# IDs de categorías extraídos del JSON embebido
SECCIONES = {
    'nacionales':      2943,
    'internacionales':  450,
    'deportes':        None,  # buscar dinámicamente
    'economia':        None,
    'entretenimiento': None,
    'salud':           None,
    'tecnologia':      None,
    'opinion':         None,
}

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}
DELAY       = 0.5   # más rápido porque es API
PER_PAGE    = 20    # artículos por página
MAX_PAGES   = 5     # páginas por sección (100 artículos máx por sección)

MESES = {
    'enero':'01','febrero':'02','marzo':'03','abril':'04',
    'mayo':'05','junio':'06','julio':'07','agosto':'08',
    'septiembre':'09','octubre':'10','noviembre':'11','diciembre':'12'
}

# -------------------------------------------------------------
# FUNCIONES
# -------------------------------------------------------------
def get_category_id(slug):
    """Obtiene el ID de una categoría por su slug."""
    try:
        r = requests.get(f'{API_BASE}/categories?slug={slug}', headers=HEADERS, timeout=10)
        r.raise_for_status()
        data = r.json()
        if data:
            return data[0]['id']
    except Exception as e:
        print(f"  Error obteniendo ID de {slug}: {e}")
    return None

def clean_html(text):
    """Elimina tags HTML y limpia espacios."""
    if not text:
        return ""
    soup = BeautifulSoup(text, 'html.parser')
    # Eliminar imágenes y links de WhatsApp/Facebook
    for tag in soup.find_all(['img', 'figure', 'noscript']):
        tag.decompose()
    for a in soup.find_all('a', href=True):
        if 'whatsapp' in a['href'] or 'facebook' in a['href']:
            a.decompose()
    text = soup.get_text(separator=' ')
    return re.sub(r'\s+', ' ', text).strip()

def parse_date(date_str):
    """Convierte '2026-04-06T14:16:02' → '2026-04-06'"""
    if not date_str:
        return "Sin fecha"
    return date_str[:10]

def get_posts_page(category_id, page=1):
    """Obtiene una página de artículos de la API."""
    try:
        url = f'{API_BASE}/posts'
        params = {
            'categories': category_id,
            'per_page':   PER_PAGE,
            'page':       page,
            '_embed':     1
        }
        r = requests.get(url, headers=HEADERS, params=params, timeout=15)
        r.raise_for_status()
        return r.json()
    except requests.exceptions.HTTPError as e:
        if '400' in str(e) or '404' in str(e):
            return []  # Sin más páginas
        print(f"  Error HTTP: {e}")
        return []
    except Exception as e:
        print(f"  Error: {e}")
        return []

def extract_post_data(post, section_name):
    """Extrae los campos del objeto JSON de un post."""
    # Título
    title = clean_html(post.get('title', {}).get('rendered', 'Sin titulo'))

    # Fecha
    date = parse_date(post.get('date', ''))

    # Sección (del nombre de categoría)
    section = section_name

    # Contenido completo
    content_html = post.get('content', {}).get('rendered', '')
    content = clean_html(content_html)

    # URL del artículo en el frontend
    slug = post.get('slug', '')
    url = f'{BASE_SITE}/{section_name}/{slug}'

    return {
        'source':           'acontecercr',
        'url':              url,
        'title':            title,
        'publication_date': date,
        'scraping_date':    datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'section':          section,
        'full_text':        content,
        'language':         'es'
    }

# -------------------------------------------------------------
# SCRAPING PRINCIPAL VÍA API
# -------------------------------------------------------------
data = []
urls_vistas = set()

# Primero resolver IDs de secciones que faltan
print("Resolviendo IDs de categorías...")
for slug in list(SECCIONES.keys()):
    if SECCIONES[slug] is None:
        cat_id = get_category_id(slug)
        SECCIONES[slug] = cat_id
        print(f"  {slug} → ID: {cat_id}")
        time.sleep(0.3)

print(f"\nSecciones configuradas: {SECCIONES}\n")

# Scraping por sección
for section_name, category_id in SECCIONES.items():
    if category_id is None:
        print(f"\nSeccion: {section_name.upper()} → ID no encontrado, saltando.")
        continue

    print(f"\nSeccion: {section_name.upper()} (ID: {category_id})")
    total_nuevos = 0

    for page in range(1, MAX_PAGES + 1):
        posts = get_posts_page(category_id, page)
        if not posts:
            print(f"  Página {page}: sin más resultados.")
            break

        nuevos_en_pagina = 0
        for post in posts:
            slug = post.get('slug', '')
            url = f'{BASE_SITE}/{section_name}/{slug}'
            if url in urls_vistas:
                continue
            urls_vistas.add(url)

            row = extract_post_data(post, section_name)
            data.append(row)
            nuevos_en_pagina += 1

        total_nuevos += nuevos_en_pagina
        print(f"  Página {page}: {nuevos_en_pagina} artículos nuevos.")
        time.sleep(DELAY)

    print(f"  Total sección: {total_nuevos} artículos.")

# -------------------------------------------------------------
# RESULTADO FINAL — Schema v1.0
# -------------------------------------------------------------
df = pd.DataFrame(data, columns=[
    'source', 'url', 'title', 'publication_date',
    'scraping_date', 'section', 'full_text', 'language'
])

# Validaciones estándar v1.0
df = df.drop_duplicates(subset='url')
df = df[df['full_text'].str.len() >= 300]
df = df[~df['publication_date'].isin(['Sin fecha', 'Error', ''])]

today_str = datetime.now().strftime('%Y%m%d')
output_file = f'acontecercr_{today_str}.csv'

df.to_csv(output_file, index=False, encoding='utf-8', sep=',', na_rep='NULL')
files.download(output_file)

print(f"\nDataFrame: {len(df)} filas x {len(df.columns)} columnas")
print(f"Archivo guardado: {output_file}")
df.head(8)