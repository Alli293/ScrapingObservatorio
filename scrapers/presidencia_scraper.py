import asyncio
from datetime import datetime, timezone
from playwright.async_api import async_playwright
from scrapers.base_scraper import BaseScraper

BASE_URL = "https://www.presidencia.go.cr"
NEWS_URL = f"{BASE_URL}/noticias"

TEST_MAX_ARTICLES = 8


def parse_iso_date(dt_attr: str) -> str:
    """'2025-03-06T18:29:27+00:00' → '2025-03-06'"""
    try:
        return dt_attr[:10]
    except Exception:
        return dt_attr


class PresidenciaScraper(BaseScraper):
    SOURCE_NAME = "presidencia"
    BASE_URL    = BASE_URL

    def __init__(
        self,
        output_dir,
        log_dir,
        test_mode: bool = False,
        date_from: str | None = None,
        date_to:   str | None = None,
    ):
        """
        Parameters
        ----------
        test_mode : bool
            If True, limit to TEST_MAX_ARTICLES articles.
        date_from : str | None
            ISO date string 'YYYY-MM-DD'. Only include articles on or after
            this date. Useful for incremental re-runs.
        date_to : str | None
            ISO date string 'YYYY-MM-DD'. Only include articles on or before
            this date.
        """
        super().__init__(output_dir=output_dir, log_dir=log_dir)
        self.test_mode = test_mode
        self.date_from = datetime.fromisoformat(date_from).date() if date_from else None
        self.date_to   = datetime.fromisoformat(date_to).date()   if date_to   else None

    def scrape(self) -> list[dict]:
        return asyncio.run(self._scrape_async())

    # ------------------------------------------------------------------
    # Phase 1 – collect article links from the single listing page
    # ------------------------------------------------------------------
    async def _collect_links(self, browser) -> list[dict]:
        links = []
        seen: set[str] = set()
        page = await browser.new_page()
        try:
            await page.goto(NEWS_URL, timeout=30000, wait_until="domcontentloaded")
            await page.wait_for_timeout(1000)

            rows = await page.query_selector_all("div.item-news.views-row")
            for row in rows:
                # Title + href
                title_el = await row.query_selector("span.title a")
                if not title_el:
                    continue
                href  = await title_el.get_attribute("href")
                title = (await title_el.inner_text()).strip()
                if not href:
                    continue
                # Resolve relative URL
                full_url = href if href.startswith("http") else f"{BASE_URL}{href}"

                # Date from <time datetime="...">
                time_el = await row.query_selector("time.datetime")
                date_raw = ""
                if time_el:
                    date_raw = await time_el.get_attribute("datetime") or ""
                pub_date_str = parse_iso_date(date_raw) if date_raw else "NULL"

                # Apply date filters
                if pub_date_str != "NULL":
                    try:
                        pub_date = datetime.fromisoformat(pub_date_str).date()
                        if self.date_from and pub_date < self.date_from:
                            continue
                        if self.date_to and pub_date > self.date_to:
                            continue
                    except ValueError:
                        pass

                if full_url not in seen:
                    seen.add(full_url)
                    links.append({
                        "url":              full_url,
                        "title":            title,
                        "section":          "presidencia",
                        "publication_date": pub_date_str,
                    })

        except Exception as e:
            self.log(f"Error collecting links: {e}")
        finally:
            await page.close()

        return links

    # ------------------------------------------------------------------
    # Phase 2 – visit each article and extract content
    # ------------------------------------------------------------------
    async def _scrape_article(self, browser, link_data: dict) -> dict | None:
        url = link_data["url"]
        page = await browser.new_page()
        try:
            await page.goto(url, timeout=30000, wait_until="domcontentloaded")
            await page.wait_for_timeout(500)

            # Title (on-page h1 if present, fallback to collected title)
            title_el = await page.query_selector("h1")
            title = (await title_el.inner_text()).strip() if title_el else link_data.get("title", "")

            # Publication date: re-read from article page if available
            pub_date = link_data.get("publication_date", "NULL")
            time_el = await page.query_selector("time.datetime")
            if time_el:
                dt_attr = await time_el.get_attribute("datetime") or ""
                if dt_attr:
                    pub_date = parse_iso_date(dt_attr)

            # Full text: all <p> inside the body field div
            content_div = await page.query_selector(
                "div.field--name-body"
            )
            full_text = ""
            if content_div:
                paras = await content_div.query_selector_all("p")
                parts = []
                for p in paras:
                    txt = (await p.inner_text()).strip()
                    if txt:
                        parts.append(txt)
                full_text = " ".join(parts)

            await page.close()

            if len(full_text) < 300:
                self.log(f"Skipping (short content): {url}")
                return None

            return {
                "url":              url,
                "title":            title,
                "section":          link_data.get("section", "presidencia"),
                "publication_date": pub_date,
                "full_text":        full_text,
            }

        except Exception as e:
            self.log(f"Error scraping article {url}: {e}")
            await page.close()
            return None

    # ------------------------------------------------------------------
    # Orchestrator
    # ------------------------------------------------------------------
    async def _scrape_async(self) -> list[dict]:
        results = []
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True, args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
            ])

            self.log("Phase 1: collecting article links…")
            if self.date_from or self.date_to:
                self.log(
                    f"  Date filter: from={self.date_from or 'any'} "
                    f"to={self.date_to or 'any'}"
                )
            links = await self._collect_links(browser)
            self.log(f"Found {len(links)} articles matching filters.")

            if self.test_mode:
                links = links[:TEST_MAX_ARTICLES]
                self.log(f"Test mode: capped at {len(links)} articles.")

            self.log("Phase 2: scraping articles…")
            for i, link_data in enumerate(links, 1):
                self.log(f"  [{i}/{len(links)}] {link_data['url']}")
                article = await self._scrape_article(browser, link_data)
                if article:
                    results.append(article)

            await browser.close()

        self.log(f"Done. {len(results)} articles collected.")
        return results
