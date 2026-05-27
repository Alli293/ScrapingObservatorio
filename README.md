# Observatorio Democrático — Pipeline de Datos

Sistema de scraping modular para recolección de noticias costarricenses.
Cumple con el **Estándar de Estructura y Validación de Datos v1.0**.

---

## Estructura del proyecto

```
observatorio_democratico/
│
├── main.py                     # Orquestador principal
├── requirements.txt
├── README.md
│
├── scrapers/
│   ├── __init__.py
│   ├── base_scraper.py         # Clase base abstracta (NO modificar)
│   ├── elperiodicocr.py        # El Periódico CR
│   ├── nacion.py               # (próximo)
│   └── ...                     # Agregar un archivo por periódico
│
├── output/                     # CSVs exportados (source_YYYYMMDD.csv)
│   └── elperiodicocr_20260426.csv
│
└── logs/                       # Logs de ejecución y descartados
    ├── elperiodicocr.log
    ├── elperiodicocr_20260426_discarded.csv
    └── execution_report_20260426_120000.json
```

---

## Instalación

```bash
# 1. Instalar dependencias Python
pip install -r requirements.txt

# 2. Instalar navegadores de Playwright
playwright install chromium
```
python -m playwright install chromium
---

## Uso

```bash
# Ejecutar TODOS los scrapers
python main.py

# Ejecutar solo un scraper específico
python main.py --only elperiodicocr

# Ejecutar varios scrapers
python main.py --only elperiodicocr nacion crhoy

# Ver scrapers disponibles
python main.py --list

# Especificar directorios personalizados
python main.py --output /data/corpus --logs /data/logs
```

---

## Schema obligatorio (v1.0)

| Columna            | Tipo     | Descripción                                      |
|--------------------|----------|--------------------------------------------------|
| `source`           | string   | Nombre normalizado del medio (snake_case)        |
| `url`              | string   | URL única del artículo                           |
| `title`            | string   | Titular limpio, sin HTML                         |
| `publication_date` | datetime | `YYYY-MM-DD HH:MM:SS` (UTC-6)                   |
| `scraping_date`    | datetime | `YYYY-MM-DD HH:MM:SS` (UTC-6, automático)        |
| `section`          | string   | Sección del medio                                |
| `full_text`        | string   | Cuerpo periodístico limpio (mín. 300 chars)      |
| `language`         | string   | Código ISO 2 letras (detectado automáticamente)  |

**Formato CSV:** separador `|`, codificación UTF-8, valores nulos como `NULL`.

---

## Agregar un nuevo scraper

1. Crear `scrapers/nuevo_medio.py`
2. Importar y extender `BaseScraper`
3. Definir `SOURCE_NAME`, `BASE_URL` e implementar `scrape()`
4. Registrar en `SCRAPERS_REGISTRY` dentro de `main.py`

```python
# scrapers/nuevo_medio.py
from scrapers.base_scraper import BaseScraper

class NuevoMedioScraper(BaseScraper):
    SOURCE_NAME = "nuevo_medio"
    BASE_URL = "https://www.nuevomedio.cr/"

    def scrape(self) -> list[dict]:
        records = []
        # ... lógica de scraping con Playwright ...
        # Cada dict debe tener: url, title, publication_date, section, full_text
        return records
```

```python
# main.py — SCRAPERS_REGISTRY
SCRAPERS_REGISTRY = {
    ...
    "nuevo_medio": ("scrapers.nuevo_medio", "NuevoMedioScraper"),
}
```

---

## Validaciones automáticas (BaseScraper)

- `source` → inyectado automáticamente desde `SOURCE_NAME`
- `scraping_date` → fecha/hora de ejecución (UTC-6), automático
- `language` → detectado con `langdetect` sobre el `full_text`, automático
- Registros con `full_text < 300` caracteres → descartados al log
- URLs duplicadas → eliminadas, primera ocurrencia se conserva
- `publication_date` nulo → descartado al log
- Todos los descartados se guardan en `logs/source_YYYYMMDD_discarded.csv`
- python -m playwright install chromium


## Side Note — Límite de páginas por sección

El scraper de la revista incluye una limitación intencional de páginas por sección para evitar ejecuciones extremadamente largas durante pruebas o corridas normales.

```python
MAX_PAGES_PER_SECTION = 1 cambiar a 319 para scraping corpus completo

 ## Side Note —  Secciones 
 El scraper de munidiario es una unica seccion y no se acutalzuiza desde el 2024 por lo que se el escraper concisiste en una recolecion historica 

 ## Side Note —  Scrapers test mode 
 algunos scrapers tienen un test mode porque son demasiado grandes para ejecutar el test mode usar  
 python scrapers/noticiasenlineacr.py --test 
 o bien 
 python main.py --only ncrnoticias --test
python main.py --only noticiasenlineacr --test
## Side Note —  Scrapers test mode  
Repretel tiene demasiados articulos algunos muy antiguos asi que se delmito ha extraer del 2023 hacia la actualidad 
