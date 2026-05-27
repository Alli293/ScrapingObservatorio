"""
pulsocr.py
Scraper para Pulso CR (https://www.pulsocr.com/)

Secciones (7):
  - Economía    : https://www.pulsocr.com/economia/
  - Nación      : https://www.pulsocr.com/nacion/
  - Locales     : https://www.pulsocr.com/locales/
  - Judiciales  : https://www.pulsocr.com/judiciales/
  - Tecnología  : https://www.pulsocr.com/tecnologia/
  - Cultura     : https://www.pulsocr.com/cultura/
  - General     : https://www.pulsocr.com/general/

Paginación: /seccion/page/N/  (WordPress estándar)

Estructura listado:
  - Título y URL : div[class*='read-title'] h3 a
  - (fecha en listado no siempre disponible, se extrae en el artículo)

Estructura artículo:
  - Fecha : div[class*='item-metadata'] span[class*='posts-date']
            ("enero 16, 2026" → 2026-01-16)
  - Texto : div[class*='entry-content'] → todos los <p>
            (excluye autor, tags, navegación, compartir)

Deduplicación global entre secciones.
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

BASE_URL = "https://www.pulsocr.com"

SECTIONS = [
    ("https://www.pulsocr.com/economia/",   "Economía"),
    ("https://www.pulsocr.com/nacion/",     "Nación"),
    ("https://www.pulsocr.com/locales/",    "Locales"),
    ("https://www.pulsocr.com/judiciales/", "Judiciales"),
    ("https://www.pulsocr.com/tecnologia/", "Tecnología"),
    ("https://www.pulsocr.com/cultura/",    "Cultura"),
    ("https://www.pulsocr.com/general/",    "General"),
]

ARTICLE_TIMEOUT = 20_000
DELAY_BETWEEN_ARTICLES = 1.0
DELAY_BETWEEN_PAGES = 1.5
DELAY_BETWEEN_SECTIONS = 2.0
DELAY_SCROLL = 1800

MESES_ES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4,
    "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
    "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
}


def parse_date_es_long(text: str) -> str:
    """
    Parsea 'enero 16, 2026' → '2026-01-16'
    También maneja 'enero 16 de 2026' o '16 de enero de 2026'.
    """
    text = text.strip().lower()

    # Formato "mes DD, YYYY"
    match = re.search(r"(\w+)\s+(\d{1,2}),?\s+(\d{4})", text)
    if match:
        month = MESES_ES.get(match.group(1), 0)
        day = int(match.group(2))
        year = int(match.group(3))
        if month:
            return f"{year:04d}-{month:02d}-{day:02d}"

    # Formato "DD de mes de YYYY"
    match2 = re.search(r"(\d{1,2})\s+de\s+(\w+)\s+de\s+(\d{4})", text)
    if match2:
        day = int(match2.group(1))
        month = MESES_ES.get(match2.group(2), 0)
        year = int(match2.group(3))
        if month:
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
    if not url or not url.startswith("https://www.pulsocr.com/"):
        return False
    exclude = ["/author/", "/tag/", "/page/", "/category/",
               "/?", "/#", "/wp-", "/feed"]
    for pat in exclude:
        if pat in url:
            return False
    # Excluir URLs de sección base (sin slug de artículo)
    path = url.replace("https://www.pulsocr.com/", "").strip("/")
    parts = [p for p in path.split("/") if p]
    # Artículos tienen al menos seccion/slug
    return len(parts) >= 2


class PulsoCRScraper(BaseScraper):
    """
    Scraper para Pulso CR.
    7 secciones con paginación WordPress /page/N/.
    Scroll al final en cada página antes de avanzar.
    Deduplicación global entre secciones.
    """

    SOURCE_NAME = "pulsocr"
    BASE_URL = BASE_URL + "/"


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
            # PASO 1: Recolectar URLs con deduplicación global
            # -------------------------------------------------------
            article_links = {}

            for section_url, section_name in SECTIONS:
                self.logger.info(f"Recolectando: {section_name} ({section_url})")
                links = await self._collect_section(context, section_url, section_name)

                new_count = 0
                for link in links:
                    if link["url"] not in article_links:
                        article_links[link["url"]] = link
                        new_count += 1

                self.logger.info(
                    f"  → {len(links)} encontrados | {new_count} nuevos | "
                    f"Total: {len(article_links)}"
                )
                await asyncio.sleep(DELAY_BETWEEN_SECTIONS)

            self.logger.info(f"Total URLs únicas: {len(article_links)}")

            # -------------------------------------------------------
            # PASO 2: Visitar cada artículo
            # -------------------------------------------------------
            records = []
            for i, link_data in enumerate(article_links.values()):
                self.logger.debug(f"[{i+1}/{len(article_links)}] {link_data['url']}")
                record = await self._scrape_article(context, link_data)
                if record:
                    records.append(record)
                await asyncio.sleep(DELAY_BETWEEN_ARTICLES)

            await browser.close()
            return records

    # ------------------------------------------------------------------
    # Recolección paginada
    # ------------------------------------------------------------------

    async def _collect_section(
        self, context, base_url: str, section_name: str
    ) -> list[dict]:
        """
        Recorre todas las páginas de la sección con paginación /page/N/.
        En cada página: scroll completo → extrae tarjetas → siguiente página.
        """
        collected = {}
        page_num = 1

        while True:
            url = base_url if page_num == 1 else base_url.rstrip("/") + f"/page/{page_num}/"
            page = await context.new_page()
            found_on_page = 0

            try:
                resp = await page.goto(url, wait_until="domcontentloaded", timeout=25_000)

                if resp and resp.status == 404:
                    self.logger.debug(f"  Página {page_num} → 404, fin de sección")
                    break

                await page.wait_for_timeout(1500)
                await self._scroll_to_bottom(page)

                found_on_page = await self._extract_cards(page, collected, section_name)

                self.logger.debug(
                    f"  [{section_name}] Pág {page_num}: "
                    f"{found_on_page} nuevos | total: {len(collected)}"
                )

                # Sin tarjetas → fin de sección
                if found_on_page == 0:
                    all_titles = await page.query_selector_all(
                        "div[class*='read-title'], h3.entry-title"
                    )
                    if len(all_titles) == 0:
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

        return list(collected.values())

    async def _scroll_to_bottom(self, page) -> None:
        """Scroll progresivo hasta el final para lazy-loading."""
        prev_height = -1
        for _ in range(6):
            h = await page.evaluate("document.body.scrollHeight")
            if h == prev_height:
                break
            prev_height = h
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(DELAY_SCROLL)

    async def _extract_cards(
        self, page, collected: dict, section_name: str
    ) -> int:
        """
        Extrae tarjetas buscando div[class*='read-title'] sin jerarquía.
        """
        found_new = 0

        cards = await page.query_selector_all(
            "div.read-title, div[class*='read-title']"
        )

        for card in cards:
            try:
                anchor = await card.query_selector("h3 a, h2 a, a[href]")
                if not anchor:
                    continue

                href = await anchor.get_attribute("href")
                if not href or not is_article_url(href):
                    continue
                if href in collected:
                    continue

                title = clean_text(await anchor.inner_text())
                if not title:
                    continue

                collected[href] = {
                    "url": href.strip(),
                    "title": title,
                    "section": section_name,
                    "publication_date": "",  # se extrae al visitar el artículo
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
        Fecha : div[class*='item-metadata'] span[class*='posts-date']
        Texto : div[class*='entry-content'] → todos los <p>
        """
        page = await context.new_page()

        try:
            await page.goto(
                link_data["url"], wait_until="domcontentloaded", timeout=ARTICLE_TIMEOUT
            )
            await page.wait_for_timeout(1500)

            # -----------------------------------------------------------
            # Fecha: span[class*='posts-date'] dentro de div[class*='item-metadata']
            # Buscar sin jerarquía
            # -----------------------------------------------------------
            publication_date = ""

            date_span = await page.query_selector(
                "span.item-metadata.posts-date, "
                "span[class*='posts-date'], "
                "div[class*='item-metadata'] span[class*='date']"
            )
            if date_span:
                date_text = await date_span.inner_text()
                publication_date = parse_date_es_long(date_text)

            # Fallback: meta tag
            if not publication_date:
                meta_el = await page.query_selector(
                    'meta[property="article:published_time"]'
                )
                if meta_el:
                    raw_dt = await meta_el.get_attribute("content")
                    if raw_dt:
                        publication_date = parse_iso_date(raw_dt)

            # -----------------------------------------------------------
            # Sección: intentar refinar desde breadcrumb o categoría
            # -----------------------------------------------------------
            section = link_data.get("section", "")
            try:
                cat_el = await page.query_selector(
                    "span[class*='cat-links'] a, "
                    "a[rel='category tag'], "
                    "[class*='category'] a"
                )
                if cat_el:
                    cat_text = clean_text(await cat_el.inner_text())
                    if cat_text:
                        section = cat_text
            except Exception:
                pass

            # -----------------------------------------------------------
            # Texto: div[class*='entry-content'] sin jerarquía
            # Extraer todos los <p> excluyendo autor, tags, navegación
            # -----------------------------------------------------------
            content_div = await page.query_selector(
                "div.entry-content, div[class*='entry-content']"
            )

            # Fallback: div.read-details
            if not content_div:
                content_div = await page.query_selector(
                    "div.read-details, div[class*='read-details']"
                )

            if not content_div:
                content_div = await page.query_selector("article")

            if not content_div:
                self.logger.warning(f"Sin contenedor: {link_data['url']}")
                return None

            full_text = await content_div.evaluate("""
                (el) => {
                    const clone = el.cloneNode(true);

                    const remove_sels = [
                        // Autor
                        '.morenews-author-bio', '[class*="author-bio"]',
                        '[class*="author-box"]', '[class*="author-info"]',
                        // Tags y metadatos
                        '[class*="tags-links"]', '[class*="post-item-metadata"]',
                        '[class*="entry-meta"]',
                        // Navegación entre artículos
                        'nav', '.navigation', '[class*="post-navigation"]',
                        '[class*="nav-links"]',
                        // Redes sociales
                        '[class*="share"]', '[class*="social"]',
                        // Publicidad
                        '[class*="ad-"]', '[id*="ad"]',
                        // Artículos relacionados
                        '[class*="related"]',
                        // Scripts, estilos, figuras
                        'script', 'style', 'iframe',
                        'figure', 'figcaption',
                        // Comentarios
                        '#comments', '.comments-area',
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
                "section": section,
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
    scraper = PulsoCRScraper()
    summary = scraper.run()
    print(summary)
