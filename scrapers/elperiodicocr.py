"""
elperiodicocr.py
Scraper para El Periódico CR (https://www.elperiodicocr.com/)

Características del sitio:
- Contenido dinámico (JavaScript)
- Scroll infinito (sin paginación numérica)
- Estructura basada en temas de WordPress (Tagdiv)
- Contenedor principal: div con clase que contiene 'td_block'
- Cada noticia: div.td-module-container
- Título y URL: h2.entry-title a
- Sección: a.td-post-category
- Fecha: time.entry-date[datetime]
- Texto artículo: div.tdb-block-inner > p (ignorando ads)
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

# URL de últimas noticias (scroll infinito)
LISTING_URL = "https://www.elperiodicocr.com/ultimas-noticias/"

# Número máximo de scrolls en la página de listado
MAX_SCROLLS = 15

# Timeout por página de artículo (ms)
ARTICLE_TIMEOUT = 20_000

# Pausa entre artículos para no sobrecargar el servidor (segundos)
DELAY_BETWEEN_ARTICLES = 1.0


def clean_text(text: str) -> str:
    """Limpia espacios múltiples y saltos de línea innecesarios."""
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def parse_date(raw_datetime: str) -> str:
    """
    Parsea el atributo datetime de <time> a formato YYYY-MM-DD HH:MM:SS
    Ejemplo entrada: '2026-04-24T15:24:24-06:00'
    """
    try:
        dt = datetime.fromisoformat(raw_datetime)
        # Normalizar a UTC-6
        dt_cr = dt.astimezone(CR_TZ)
        return dt_cr.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return raw_datetime  # retorna tal cual si no se puede parsear


class ElPeriodicoCRScraper(BaseScraper):
    """
    Scraper para El Periódico CR.
    Navega la página de últimas noticias con scroll infinito,
    recolecta URLs de artículos y visita cada uno para extraer el texto completo.
    """

    SOURCE_NAME = "elperiodicocr"
    BASE_URL = "https://www.elperiodicocr.com/"


    def __init__(self, output_dir="output", log_dir="logs"):
        super().__init__(output_dir=output_dir, log_dir=log_dir)

    def scrape(self) -> list[dict]:
        """Punto de entrada sincrónico que lanza el scraper async."""
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
            # PASO 1: Recolectar URLs desde la página de listado
            # -------------------------------------------------------
            article_links = await self._collect_article_links(context)
            self.logger.info(f"Total URLs recolectadas: {len(article_links)}")

            # -------------------------------------------------------
            # PASO 2: Visitar cada artículo y extraer datos
            # -------------------------------------------------------
            records = []
            for i, link_data in enumerate(article_links):
                self.logger.debug(f"[{i+1}/{len(article_links)}] Procesando: {link_data['url']}")
                record = await self._scrape_article(context, link_data)
                if record:
                    records.append(record)
                await asyncio.sleep(DELAY_BETWEEN_ARTICLES)

            await browser.close()
            return records

    async def _collect_article_links(self, context) -> list[dict]:
        """
        Navega la página de listado con scroll infinito.
        Recolecta URL, título y sección de cada tarjeta de noticia.
        """
        page = await context.new_page()
        collected = {}  # url -> {url, title, section}

        try:
            await page.goto(LISTING_URL, wait_until="domcontentloaded", timeout=30_000)
            await page.wait_for_timeout(2000)

            for scroll_num in range(MAX_SCROLLS):
                # Extraer artículos visibles actualmente
                cards = await page.query_selector_all("div.td-module-container")

                for card in cards:
                    try:
                        # URL y título desde h2.entry-title a
                        title_anchor = await card.query_selector("h2.entry-title a")
                        if not title_anchor:
                            continue

                        url = await title_anchor.get_attribute("href")
                        title = await title_anchor.inner_text()

                        if not url or url in collected:
                            continue

                        # Sección desde a.td-post-category
                        section_el = await card.query_selector("a.td-post-category")
                        section = (await section_el.inner_text()) if section_el else ""

                        collected[url] = {
                            "url": url.strip(),
                            "title": clean_text(title),
                            "section": clean_text(section),
                        }
                    except Exception as e:
                        self.logger.debug(f"Error extrayendo tarjeta: {e}")
                        continue

                self.logger.info(
                    f"Scroll {scroll_num + 1}/{MAX_SCROLLS} | "
                    f"Artículos acumulados: {len(collected)}"
                )

                # Scroll hacia abajo para cargar más contenido
                prev_count = len(collected)
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await page.wait_for_timeout(2500)

                # Verificar si se cargaron nuevos artículos
                cards_after = await page.query_selector_all("div.td-module-container")
                if len(cards_after) == len(cards) and scroll_num > 2:
                    self.logger.info("No se cargaron nuevos artículos. Finalizando scroll.")
                    break

        except Exception as e:
            self.logger.error(f"Error en recolección de listado: {e}", exc_info=True)
        finally:
            await page.close()

        return list(collected.values())

    async def _scrape_article(self, context, link_data: dict) -> dict | None:
        """
        Visita un artículo individual y extrae:
        - full_text (todos los <p> del contenido, sin ads)
        - publication_date (desde <time class='entry-date'>)
        Combina con los datos del listado (url, title, section).
        """
        page = await context.new_page()

        try:
            await page.goto(link_data["url"], wait_until="domcontentloaded", timeout=ARTICLE_TIMEOUT)
            await page.wait_for_timeout(1500)

            # -----------------------------------------------------------
            # Extraer fecha de publicación
            # -----------------------------------------------------------
            publication_date = None
            time_el = await page.query_selector("time.entry-date")
            if time_el:
                raw_dt = await time_el.get_attribute("datetime")
                if raw_dt:
                    publication_date = parse_date(raw_dt)

            # Si no se encontró en el artículo, buscar en meta tags
            if not publication_date:
                meta_el = await page.query_selector('meta[property="article:published_time"]')
                if meta_el:
                    raw_dt = await meta_el.get_attribute("content")
                    if raw_dt:
                        publication_date = parse_date(raw_dt)

            # -----------------------------------------------------------
            # Extraer texto completo
            # Busca div.tdb-block-inner sin importar jerarquía,
            # luego toma todos los <p> dentro (excluyendo los de ads)
            # -----------------------------------------------------------
            full_text = ""

            # Buscar TODOS los divs con clase tdb-block-inner en el documento
            # (sin restricción de jerarquía)
            content_blocks = await page.query_selector_all("div.tdb-block-inner")

            paragraphs_collected = []

            for block in content_blocks:
                # Verificar que este bloque tenga párrafos de contenido real
                # (no bloques de publicidad)
                block_html = await block.inner_html()

                # Saltar bloques que solo tienen publicidad
                if "adsbygoogle" in block_html and "<p>" not in block_html:
                    continue

                # Extraer todos los <p> directos e indirectos del bloque
                p_elements = await block.query_selector_all("p")

                for p in p_elements:
                    # Verificar que el <p> no esté dentro de un elemento de ad
                    # evaluando su texto
                    p_text = await p.inner_text()
                    p_text = clean_text(p_text)

                    # Filtrar párrafos vacíos o de publicidad
                    if not p_text or len(p_text) < 10:
                        continue
                    if "adsbygoogle" in p_text.lower():
                        continue

                    paragraphs_collected.append(p_text)

            # Deduplicar párrafos manteniendo orden
            seen = set()
            unique_paragraphs = []
            for p in paragraphs_collected:
                if p not in seen:
                    seen.add(p)
                    unique_paragraphs.append(p)

            full_text = "\n\n".join(unique_paragraphs)

            # -----------------------------------------------------------
            # Construir registro
            # -----------------------------------------------------------
            if not full_text:
                self.logger.warning(f"Sin texto extraído: {link_data['url']}")
                return None

            return {
                "url": link_data["url"],
                "title": link_data["title"],
                "section": link_data["section"],
                "publication_date": publication_date,
                "full_text": full_text,
                # source, scraping_date y language se inyectan en BaseScraper
            }

        except PlaywrightTimeoutError:
            self.logger.warning(f"Timeout al cargar artículo: {link_data['url']}")
            return None
        except Exception as e:
            self.logger.error(f"Error scrapeando {link_data['url']}: {e}", exc_info=True)
            return None
        finally:
            await page.close()


# Permite ejecutar el scraper directamente para pruebas
if __name__ == "__main__":
    scraper = ElPeriodicoCRScraper()
    summary = scraper.run()
    print(summary)
