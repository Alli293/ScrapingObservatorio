"""
lareaccioncr.py
Scraper para La Reacción CR (https://lareaccioncr.com/2026/)

Características del sitio:
- WordPress con tema Mikado (mkd-*)
- NO tiene scroll infinito — tiene paginación por categorías y archivo mensual
- Dos fuentes de URLs:
    1. Todas las categorías del sitio (12 categorías conocidas)
    2. Archivo mensual (ul.wp-block-archives-list en sidebar)
- Tarjeta de listado: div.mkd-pt-two-content-top-holder-cell
    - Título y URL: h3.mkd-pt-two-title > a.mkd-pt-link
    - Fecha en listado: div.mkd-post-info-date (texto "7 de abril de 2026")
- Artículo individual:
    - Contenedor: div.mkd-blog-holder > article > div.mkd-post-content
    - Texto: div.mkd-post-text — extrae p, ul/li, blockquote, strong
    - Fecha: div.mkd-post-info-date[itemprop="dateCreated"]
    - Sección: div.mkd-post-info-category > a (primera categoría)
- Filtro: ignorar URLs que contengan /category/ (son páginas de listado, no artículos)
- Filtro: ignorar URLs con video embebido como único contenido
"""

import asyncio
import re
from datetime import datetime, timezone, timedelta

from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scrapers.base_scraper import BaseScraper

CR_TZ = timezone(timedelta(hours=-6))

BASE_URL = "https://lareaccioncr.com/2026/"

# Categorías conocidas del sitio
CATEGORIES = [
    "digalo",
    "aqui-hay-tema",
    "mando",
    "desafio",
    "destacados",
    "municipales",
    "geopolitica",
    "mercados",
    "politica",
    "protagonistas",
    "reacciones",
    "tendencias",
]

ARTICLE_TIMEOUT = 20_000
DELAY_BETWEEN_ARTICLES = 1.0
DELAY_BETWEEN_PAGES = 1.5

# Meses en español para parsear fechas textuales
MESES_ES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4,
    "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
    "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
}


def parse_date_es(text: str) -> str:
    """
    Parsea fechas en español como '7 de abril de 2026'
    Retorna formato YYYY-MM-DD.
    """
    text = text.strip().lower()
    match = re.search(r"(\d{1,2})\s+de\s+(\w+)\s+de\s+(\d{4})", text)
    if match:
        day = int(match.group(1))
        month = MESES_ES.get(match.group(2), 0)
        year = int(match.group(3))
        if month:
            return f"{year:04d}-{month:02d}-{day:02d}"
    return text


def clean_text(text: str) -> str:
    """Limpia espacios múltiples y saltos de línea innecesarios."""
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def is_article_url(url: str) -> bool:
    """Filtra URLs que NO son artículos (categorías, autores, páginas, etc.)."""
    if not url or not url.startswith("https://lareaccioncr.com/2026/"):
        return False
    # Excluir páginas de categoría, autor, archivo, tag
    exclude_patterns = [
        "/category/", "/author/", "/tag/", "/page/",
        "/#", "/?", "/wp-", "/feed",
    ]
    for pat in exclude_patterns:
        if pat in url:
            return False
    # URL de artículo tiene al menos año/mes/día/slug
    # Ejemplo: /2026/2026/04/07/slug/
    path = url.replace("https://lareaccioncr.com/2026/", "")
    parts = [p for p in path.split("/") if p]
    return len(parts) >= 4  # año/mes/día/slug


class LaReaccionCRScraper(BaseScraper):
    """
    Scraper para La Reacción CR.
    Estrategia de recolección:
      1. Visita cada categoría y pagina hasta el final
      2. Visita cada URL del archivo mensual y pagina hasta el final
      3. Deduplica URLs y visita cada artículo para extraer texto completo
    """

    SOURCE_NAME = "lareaccioncr"
    BASE_URL = BASE_URL


    def __init__(self, output_dir="output", log_dir="logs"):
        super().__init__(output_dir=output_dir, log_dir=log_dir)

    def scrape(self) -> list[dict]:
        return asyncio.run(self._scrape_async())

    async def _scrape_async(self) -> list[dict]:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                locale="es-CR",
            )

            # -------------------------------------------------------
            # PASO 1: Recolectar URLs del archivo mensual desde home
            # -------------------------------------------------------
            archive_urls = await self._get_archive_urls(context)
            self.logger.info(f"Archivos mensuales encontrados: {len(archive_urls)}")

            # -------------------------------------------------------
            # PASO 2: Recolectar artículos de categorías y archivos
            # -------------------------------------------------------
            article_links = {}  # url -> {url, title, section, publication_date}

            # Desde categorías
            for cat in CATEGORIES:
                cat_url = f"{BASE_URL}category/{cat}/"
                self.logger.info(f"Scrapendo categoría: {cat}")
                links = await self._collect_from_listing(context, cat_url, section_hint=cat)
                for link in links:
                    if link["url"] not in article_links:
                        article_links[link["url"]] = link
                await asyncio.sleep(DELAY_BETWEEN_PAGES)

            # Desde archivo mensual
            for arch_url in archive_urls:
                self.logger.info(f"Scrapendo archivo: {arch_url}")
                links = await self._collect_from_listing(context, arch_url, section_hint="")
                for link in links:
                    if link["url"] not in article_links:
                        article_links[link["url"]] = link
                await asyncio.sleep(DELAY_BETWEEN_PAGES)

            self.logger.info(f"Total URLs únicas recolectadas: {len(article_links)}")

            # -------------------------------------------------------
            # PASO 3: Visitar cada artículo y extraer texto completo
            # -------------------------------------------------------
            records = []
            links_list = list(article_links.values())

            for i, link_data in enumerate(links_list):
                self.logger.debug(f"[{i+1}/{len(links_list)}] {link_data['url']}")
                record = await self._scrape_article(context, link_data)
                if record:
                    records.append(record)
                await asyncio.sleep(DELAY_BETWEEN_ARTICLES)

            await browser.close()
            return records

    # ------------------------------------------------------------------
    # Recolección de URLs del archivo mensual
    # ------------------------------------------------------------------

    async def _get_archive_urls(self, context) -> list[str]:
        """
        Visita la home y extrae los enlaces del bloque de archivo mensual.
        Selector: ul.wp-block-archives-list li a
        """
        page = await context.new_page()
        archive_urls = []
        try:
            await page.goto(BASE_URL, wait_until="domcontentloaded", timeout=30_000)
            await page.wait_for_timeout(2000)

            links = await page.query_selector_all("ul.wp-block-archives-list li a")
            for link in links:
                href = await link.get_attribute("href")
                if href:
                    archive_urls.append(href.strip())
        except Exception as e:
            self.logger.error(f"Error obteniendo archivo mensual: {e}")
        finally:
            await page.close()
        return archive_urls

    # ------------------------------------------------------------------
    # Recolección de URLs desde una página de listado (categoría o archivo)
    # Con paginación (page/2/, page/3/, ...)
    # ------------------------------------------------------------------

    async def _collect_from_listing(
        self, context, base_listing_url: str, section_hint: str
    ) -> list[dict]:
        """
        Navega una URL de listado (categoría o archivo mensual) y todas sus páginas.
        Extrae: URL, título, fecha (texto), sección del listado.
        """
        collected = []
        page_num = 1

        while True:
            if page_num == 1:
                url = base_listing_url
            else:
                # WordPress usa /page/N/ para paginación
                url = base_listing_url.rstrip("/") + f"/page/{page_num}/"

            page = await context.new_page()
            found_on_page = 0

            try:
                resp = await page.goto(url, wait_until="domcontentloaded", timeout=25_000)

                # Si la página no existe (404), detenemos la paginación
                if resp and resp.status == 404:
                    self.logger.debug(f"Página {page_num} no existe ({url}), fin paginación")
                    break

                await page.wait_for_timeout(1500)

                # -----------------------------------------------------------
                # Extraer desde tarjetas mkd-pt-two (últimas noticias / featured)
                # -----------------------------------------------------------
                cards = await page.query_selector_all("div.mkd-pt-two-content-top-holder-cell")
                for card in cards:
                    try:
                        # Título y URL
                        title_anchor = await card.query_selector("h3.mkd-pt-two-title a.mkd-pt-link")
                        if not title_anchor:
                            continue
                        href = await title_anchor.get_attribute("href")
                        title = await title_anchor.inner_text()

                        if not href or not is_article_url(href):
                            continue

                        # Fecha textual desde el listado
                        date_el = await card.query_selector("div.mkd-post-info-date")
                        pub_date = ""
                        if date_el:
                            date_text = await date_el.inner_text()
                            pub_date = parse_date_es(date_text)

                        # Sección: usar hint de categoría si disponible
                        section = section_hint

                        collected.append({
                            "url": href.strip(),
                            "title": clean_text(title),
                            "section": section,
                            "publication_date": pub_date,
                        })
                        found_on_page += 1

                    except Exception as e:
                        self.logger.debug(f"Error en tarjeta mkd-pt-two: {e}")
                        continue

                # -----------------------------------------------------------
                # Extraer desde artículos mkd-blog-holder (listado estándar)
                # -----------------------------------------------------------
                articles = await page.query_selector_all(
                    "div.mkd-blog-holder article.mkd-post-content-inner, "
                    "div.mkd-blog-holder article div.mkd-post-content-inner"
                )
                # Selector más amplio: cualquier article dentro de mkd-blog-holder
                articles_broad = await page.query_selector_all(
                    "div.mkd-blog-holder article"
                )
                for art in articles_broad:
                    try:
                        title_anchor = await art.query_selector(
                            "h3.mkd-post-title a, h2.mkd-post-title a"
                        )
                        if not title_anchor:
                            continue
                        href = await title_anchor.get_attribute("href")
                        title = await title_anchor.inner_text()

                        if not href or not is_article_url(href):
                            continue

                        # Fecha
                        date_el = await art.query_selector("div.mkd-post-info-date")
                        pub_date = ""
                        if date_el:
                            date_text = await date_el.inner_text()
                            pub_date = parse_date_es(date_text)

                        # Sección desde categoría del artículo
                        section = section_hint
                        cat_el = await art.query_selector("div.mkd-post-info-category a")
                        if cat_el:
                            section = clean_text(await cat_el.inner_text())

                        collected.append({
                            "url": href.strip(),
                            "title": clean_text(title),
                            "section": section,
                            "publication_date": pub_date,
                        })
                        found_on_page += 1

                    except Exception as e:
                        self.logger.debug(f"Error en article mkd-blog: {e}")
                        continue

                self.logger.debug(
                    f"  Página {page_num} de {base_listing_url}: {found_on_page} artículos"
                )

                # Si no encontramos nada en esta página, terminamos
                if found_on_page == 0:
                    break

                page_num += 1

            except PlaywrightTimeoutError:
                self.logger.warning(f"Timeout en listado: {url}")
                break
            except Exception as e:
                self.logger.error(f"Error en listado {url}: {e}")
                break
            finally:
                await page.close()

            await asyncio.sleep(DELAY_BETWEEN_PAGES)

        return collected

    # ------------------------------------------------------------------
    # Scraping del artículo individual
    # ------------------------------------------------------------------

    async def _scrape_article(self, context, link_data: dict) -> dict | None:
        """
        Visita un artículo individual.
        Extrae:
        - full_text desde div.mkd-post-text (p, ul/li, blockquote, strong)
        - publication_date desde div[itemprop="dateCreated"].mkd-post-info-date
        - section desde div.mkd-post-info-category (primera categoría)
        """
        page = await context.new_page()

        try:
            await page.goto(link_data["url"], wait_until="domcontentloaded", timeout=ARTICLE_TIMEOUT)
            await page.wait_for_timeout(1500)

            # -----------------------------------------------------------
            # Buscar div.mkd-post-text sin importar jerarquía
            # -----------------------------------------------------------
            post_text_block = await page.query_selector("div.mkd-post-text")
            if not post_text_block:
                # Fallback: buscar mkd-post-content
                post_text_block = await page.query_selector("div.mkd-post-content")

            full_text = ""

            if post_text_block:
                full_text = await self._extract_text_from_block(post_text_block)

            if not full_text:
                self.logger.warning(f"Sin texto: {link_data['url']}")
                return None

            # -----------------------------------------------------------
            # Fecha de publicación (desde el artículo, más confiable)
            # -----------------------------------------------------------
            publication_date = link_data.get("publication_date", "")

            date_el = await page.query_selector(
                'div[itemprop="dateCreated"].mkd-post-info-date, '
                'div.mkd-post-info-date[itemprop="dateCreated"]'
            )
            if date_el:
                date_text = await date_el.inner_text()
                parsed = parse_date_es(date_text)
                if parsed and len(parsed) == 10:  # YYYY-MM-DD
                    publication_date = parsed

            # -----------------------------------------------------------
            # Sección: primera categoría del artículo
            # -----------------------------------------------------------
            section = link_data.get("section", "")
            cat_el = await page.query_selector("div.mkd-post-info-category a")
            if cat_el:
                section = clean_text(await cat_el.inner_text())

            return {
                "url": link_data["url"],
                "title": link_data["title"],
                "section": section,
                "publication_date": publication_date,
                "full_text": full_text,
            }

        except PlaywrightTimeoutError:
            self.logger.warning(f"Timeout: {link_data['url']}")
            return None
        except Exception as e:
            self.logger.error(f"Error scrapeando {link_data['url']}: {e}", exc_info=True)
            return None
        finally:
            await page.close()

    async def _extract_text_from_block(self, block) -> str:
        """
        Extrae texto limpio de un bloque HTML.
        Incluye: p, li (de ul/ol), blockquote > p, texto de strong/em inline.
        Excluye: divs de anuncios, navegación, comentarios, related posts.
        """
        paragraphs = []

        # Seleccionar todos los elementos de contenido textual dentro del bloque
        # Usamos JavaScript para extraer el texto de forma estructurada
        text_content = await block.evaluate("""
            (el) => {
                // Clonar para no modificar el DOM original
                const clone = el.cloneNode(true);

                // Eliminar elementos no deseados
                const remove_selectors = [
                    '.mkd-blog-single-navigation',
                    '.mkd-author-description',
                    '.mkd-comment-holder',
                    '.mkd-comment-form',
                    '.mkd-related-posts-holder',
                    '.mkd-single-tags-holder',
                    '.mkd-post-info',
                    '.mkd-post-image',
                    'script',
                    'style',
                    'iframe',
                    'figure',
                    'nav',
                    '.wp-block-embed',
                    '.sharedaddy',
                    '#jp-post-flair',
                ];
                remove_selectors.forEach(sel => {
                    clone.querySelectorAll(sel).forEach(el => el.remove());
                });

                // Extraer texto de elementos relevantes
                const results = [];
                const elements = clone.querySelectorAll(
                    'p, li, blockquote p, h1, h2, h3, h4'
                );

                elements.forEach(el => {
                    const text = el.innerText || el.textContent || '';
                    const cleaned = text.replace(/\\s+/g, ' ').trim();
                    if (cleaned.length > 10) {
                        results.push(cleaned);
                    }
                });

                return results.join('\\n\\n');
            }
        """)

        return clean_text(text_content) if text_content else ""


# Ejecución directa para pruebas
if __name__ == "__main__":
    scraper = LaReaccionCRScraper()
    summary = scraper.run()
    print(summary)
