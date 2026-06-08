"""debug_teletica.py — inspecciona estructura del listado de Teletica"""
import asyncio, json, io, sys
from playwright.async_api import async_playwright

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

URL = "https://www.teletica.com/noticias/nacional/sucesos"

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
            locale="es-CR",
            viewport={"width": 1280, "height": 900},
        )
        await context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', { get: () => undefined });"
        )
        page = await context.new_page()
        await page.goto(URL, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(3000)

        info = await page.evaluate("""
            () => {
                const r = {};

                // Selector original
                r.nota_link_count = document.querySelectorAll('a.nota-link').length;

                // Buscar todos los <a> cuyo href apunte a un artículo de teletica
                const allLinks = Array.from(document.querySelectorAll('a[href]'))
                    .filter(a => {
                        const h = a.href || '';
                        return h.includes('teletica.com') && !h.includes('/noticias/') &&
                               !h.includes('/autor/') && h.split('/').length > 5;
                    });
                r.article_links_count = allLinks.length;
                r.article_links_sample = allLinks.slice(0, 4).map(a => ({
                    href: a.href,
                    class: a.className.substring(0, 80),
                    parent_class: (a.parentElement?.className || '').substring(0, 80)
                }));

                // Clases de los primeros articles/divs con bastante texto
                const containers = Array.from(document.querySelectorAll('article, [class*="nota"], [class*="card"], [class*="item"]'))
                    .slice(0, 6)
                    .map(el => ({
                        tag: el.tagName,
                        cls: el.className.substring(0, 100),
                        link_href: (el.querySelector('a[href]') || {}).href || null,
                        h2_text: ((el.querySelector('h2') || {}).innerText || '').trim().substring(0, 60)
                    }));
                r.containers = containers;

                // h2 con links dentro
                const h2s = Array.from(document.querySelectorAll('h2 a[href], h3 a[href]'))
                    .slice(0, 4)
                    .map(a => ({ href: a.href, text: (a.innerText||'').trim().substring(0,60), class: a.className }));
                r.heading_links = h2s;

                return r;
            }
        """)
        print(json.dumps(info, indent=2, ensure_ascii=False))
        await browser.close()

asyncio.run(main())
