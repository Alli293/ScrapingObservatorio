"""
mundiario.py
Scraper para Mundiario CR (https://www.mundiario.com/costa-rica/)

Sección única: Costa Rica
Paginación: https://www.mundiario.com/costa-rica/?page=N

Estructura listado:
  - Contenedor artículo : div.article-data
  - Título y URL        : div.article-data h2.title > a  (href relativo + title)
  - Fecha               : div[class*='content-info'] span.date-container ("22/02/24")

Estructura artículo:
  - Texto : div[class*='content-data'] → todos los <p>
            (excluye ads, related-content, sharing, autor)
  - Fecha : del listado (span.date-container); fallback meta tag
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

BASE_URL = "https://www.mundiario.com"
SECTION_URL = "https://www.mundiario.com/costa-rica/"

ARTICLE_TIMEOUT = 20_000
DELAY_BETWEEN_ARTICLES = 1.0
DELAY_BETWEEN_PAGES = 1.5
DELAY_SCROLL = 2000

# Modo prueba: limita número de artículos procesados y páginas de sección
TEST_MAX_ARTICLES = 5
TEST_MAX_PAGES = 2


def parse_short_date(text: str) -> str:
    """
    Parsea '22/02/24' → '2024-02-22'
    También '22/02/2024' → '2024-02-22'
    """
    text = text.strip()
    match = re.search(r"(\d{1,2})/(\d{1,2})/(\d{2,4})", text)
    if match:
        day = int(match.group(1))
        month = int(match.group(2))
        year = int(match.group(3))
        if year < 100:
            year += 2000
        return f"{year:04d}-{month:02d}-{day:02d}"
    return ""


def parse_iso_date(raw: str) -> str:
    try:
        dt = datetime.fromisoformat(raw.strip().replace("Z", "+00:00"))
        return dt.astimezone(CR_TZ).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return raw[:10] if raw else ""


def clean_text(text: str) -> str:
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def is_article_url(url: str) -> bool:
    """Artículos de Mundiario tienen formato /articulo/costa-rica/slug/ID.html"""
    if not url:
        return False
    # Acepta tanto relativas (/articulo/...) como absolutas
    if url.startswith("/articulo/"):
        return True
    if url.startswith("https://www.mundiario.com/articulo/"):
        return True
    return False


def make_absolute(href: str) -> str:
    if href.startswith("http"):
        return href
    return BASE_URL + href


class MundiarioCRScraper(BaseScraper):
    """
    Scraper para Mundiario CR (sección Costa Rica).
    Recorre todas las páginas con paginación ?page=N.
    En cada página hace scroll hasta el final antes de pasar a la siguiente.
    """

    SOURCE_NAME = "mundiario"
    BASE_URL = BASE_URL + "/"


    def __init__(self, output_dir="output", log_dir="logs", test_mode: bool = False):
        super().__init__(output_dir=output_dir, log_dir=log_dir)
        self.test_mode = test_mode
        if self.test_mode:
            self.logger.info(f"*** MODO PRUEBA ACTIVO: limitando a {TEST_MAX_ARTICLES} artículos ***")

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
            # PASO 1: Recolectar URLs paginando
            # -------------------------------------------------------
            self.logger.info(f"Recolectando: Costa Rica ({SECTION_URL})")
            article_links = await self._collect_section(context)
            self.logger.info(f"Total URLs únicas: {len(article_links)}")

            # -------------------------------------------------------
            # PASO 2: Visitar cada artículo
            # -------------------------------------------------------
            records = []
            links_list = list(article_links.values())
            if self.test_mode:
                links_list = links_list[:TEST_MAX_ARTICLES]

            for i, link_data in enumerate(links_list):
                self.logger.debug(f"[{i+1}/{len(links_list)}] {link_data['url']}")
                record = await self._scrape_article(context, link_data)
                if record:
                    records.append(record)
                await asyncio.sleep(DELAY_BETWEEN_ARTICLES)

            await browser.close()
            return records

    # ------------------------------------------------------------------
    # Recolección paginada
    # ------------------------------------------------------------------

    async def _collect_section(self, context) -> dict:
        """
        Recorre https://www.mundiario.com/costa-rica/?page=N
        Página 1 = URL base sin parámetro.
        Termina cuando 404 o no hay artículos nuevos.
        """
        collected = {}
        page_num = 1
        max_pages = TEST_MAX_PAGES if self.test_mode else 9999

        while page_num <= max_pages:
            if page_num == 1:
                url = SECTION_URL
            else:
                url = SECTION_URL + f"?page={page_num}"

            page = await context.new_page()
            found_on_page = 0

            try:
                resp = await page.goto(url, wait_until="domcontentloaded", timeout=25_000)

                if resp and resp.status == 404:
                    self.logger.debug(f"  Página {page_num} → 404, fin")
                    break

                await page.wait_for_timeout(1500)

                # Scroll completo antes de extraer
                await self._scroll_to_bottom(page)

                # Extraer tarjetas div.article-data
                found_on_page = await self._extract_cards(page, collected)

                self.logger.debug(
                    f"  Pág {page_num}: {found_on_page} nuevos | "
                    f"total acumulado: {len(collected)}"
                )

                # En modo prueba, detenerse cuando ya hay suficientes links
                if self.test_mode and len(collected) >= TEST_MAX_ARTICLES:
                    self.logger.debug(
                        f"  Modo prueba: {len(collected)} links recolectados, terminando"
                    )
                    break

                # Sin artículos nuevos ni tarjetas en la página → fin
                if found_on_page == 0:
                    all_cards = await page.query_selector_all(
                        "div.article-data, div[class*='article-data']"
                    )
                    if len(all_cards) == 0:
                        self.logger.debug(f"  Sin tarjetas en pág {page_num}, terminando")
                        break

                page_num += 1

            except PlaywrightTimeoutError:
                self.logger.warning(f"  Timeout: {url}")
                break
            except Exception as e:
                self.logger.error(f"  Error en {url}: {e}", exc_info=True)
                break
            finally:
                await page.close()

            await asyncio.sleep(DELAY_BETWEEN_PAGES)

        return collected

    async def _scroll_to_bottom(self, page) -> None:
        """Scroll progresivo hasta el final para activar lazy-loading."""
        prev_height = -1
        for _ in range(8):
            current_height = await page.evaluate("document.body.scrollHeight")
            if current_height == prev_height:
                break
            prev_height = current_height
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(DELAY_SCROLL)

    async def _extract_cards(self, page, collected: dict) -> int:
        """
        Extrae artículos desde div.article-data.
        Busca sin importar jerarquía.
        Retorna número de artículos NUEVOS.
        """
        found_new = 0

        # Buscar div con clase que contenga 'article-data'
        cards = await page.query_selector_all(
            "div.article-data, div[class*='article-data']"
        )

        for card in cards:
            try:
                # Título y URL: h2[class*='title'] > a
                anchor = await card.query_selector(
                    "h2.title a, h2[class*='title'] a, h3.title a"
                )
                if not anchor:
                    # Fallback: cualquier a con href de artículo
                    anchor = await card.query_selector("a[href*='/articulo/']")
                if not anchor:
                    continue

                href = await anchor.get_attribute("href")
                if not href or not is_article_url(href):
                    continue

                url = make_absolute(href)
                if url in collected:
                    continue

                # Título: atributo title del anchor (más limpio) o inner_text
                title = await anchor.get_attribute("title") or ""
                if not title:
                    title = await anchor.inner_text()
                title = clean_text(title)

                # Fecha: div[class*='content-info'] > span.date-container
                pub_date = ""
                info_div = await card.query_selector(
                    "div.content-info, div[class*='content-info']"
                )
                if info_div:
                    date_span = await info_div.query_selector(
                        "span.date-container, span[class*='date']"
                    )
                    if date_span:
                        date_text = await date_span.inner_text()
                        pub_date = parse_short_date(date_text)

                collected[url] = {
                    "url": url,
                    "title": title,
                    "section": "Costa Rica",
                    "publication_date": pub_date,
                }
                found_new += 1

            except Exception as e:
                self.logger.debug(f"Error en tarjeta: {e}")
                continue

        return found_new

    # ------------------------------------------------------------------
    # Scraping del artículo individual
    # ------------------------------------------------------------------

    async def _scrape_article(self, context, link_data: dict) -> dict | None:
        """
        Visita el artículo.
        Texto: div[class*='content-data'] → todos los <p>
               (excluye ads, related-content, sharing, autor)
        Fecha: del listado; fallback meta tag.
        """
        page = await context.new_page()

        try:
            await page.goto(
                link_data["url"], wait_until="domcontentloaded", timeout=ARTICLE_TIMEOUT
            )
            await page.wait_for_timeout(1500)

            # -----------------------------------------------------------
            # Fecha: mejorar con meta si la del listado solo tiene día
            # -----------------------------------------------------------
            publication_date = link_data.get("publication_date", "")

            meta_el = await page.query_selector(
                'meta[property="article:published_time"]'
            )
            if meta_el:
                raw_dt = await meta_el.get_attribute("content")
                if raw_dt:
                    publication_date = parse_iso_date(raw_dt)

            # -----------------------------------------------------------
            # Texto: div[class*='content-data'] sin importar jerarquía
            # -----------------------------------------------------------
            content_div = await page.query_selector(
                "div.content-data, div[class*='content-data']"
            )

            # Fallback: div.content-body
            if not content_div:
                content_div = await page.query_selector(
                    "div.content-body, div[class*='content-body']"
                )

            # Fallback final: article
            if not content_div:
                content_div = await page.query_selector("article")

            if not content_div:
                self.logger.warning(f"Sin contenedor: {link_data['url']}")
                return None

            full_text = await content_div.evaluate("""
                (el) => {
                    const clone = el.cloneNode(true);

                    const remove_sels = [
                        // Publicidad
                        '.ad-slot', '[class*="ad-slot"]', '[class*="oat"]',
                        '[class*="advertisement"]', '[id*="ad"]',
                        // Contenido relacionado
                        '.related-content', '[class*="related"]',
                        // Redes sociales y sharing
                        '.sharrre-tools', '[class*="share"]',
                        '.metadata-body', '[class*="metadata"]',
                        // Autor y tags
                        '.author-profile', '[class*="author"]',
                        '.content-meta-tags', '[class*="meta-tags"]',
                        // Widgets y scripts
                        'script', 'style', 'iframe',
                        'figure', 'figcaption',
                        // Navegación y comentarios
                        'nav', '.navigation', '#comentarios',
                        '[class*="comment"]',
                        // Ads custom
                        '.custom-ads',
                    ];

                    remove_sels.forEach(sel => {
                        try {
                            clone.querySelectorAll(sel).forEach(e => e.remove());
                        } catch(err) {}
                    });

                    const parts = [];
                    clone.querySelectorAll('p').forEach(p => {
                        const text = (p.innerText || p.textContent || '')
                            .replace(/\\s+/g, ' ').trim();
                        if (text.length >= 15) parts.push(text);
                    });

                    return parts.join('\\n\\n');
                }
            """)

            full_text = clean_text(full_text) if full_text else ""

            if not full_text:
                self.logger.warning(f"Sin texto: {link_data['url']}")
                return None

            return {
                "url": link_data["url"],
                "title": link_data["title"],
                "section": link_data["section"],
                "publication_date": publication_date,
                "full_text": full_text,
            }

        except PlaywrightTimeoutError:
            self.logger.warning(f"Timeout: {link_data['url']}")
            return None
        except Exception as e:
            self.logger.error(f"Error en {link_data['url']}: {e}", exc_info=True)
            return None
        finally:
            await page.close()


if __name__ == "__main__":
    scraper = MundiarioCRScraper()
    summary = scraper.run()
    print(summary)
