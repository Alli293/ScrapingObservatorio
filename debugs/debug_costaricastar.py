"""
debug_costaricastar.py
Inspecciona la estructura HTML real del listado de Costa Rica Star
para identificar los selectores correctos.
"""
import asyncio
from playwright.async_api import async_playwright

URL = "https://news.co.cr/costa-rica/"

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="en-US",
        )
        page = await context.new_page()
        await page.goto(URL, wait_until="domcontentloaded", timeout=30_000)
        await page.wait_for_timeout(3000)

        print(f"\n=== URL cargada: {page.url} ===\n")

        # 1. Probar selector original
        old = await page.query_selector_all("div.titulcate a.post-title")
        print(f"Selector original 'div.titulcate a.post-title': {len(old)} resultados")

        # 2. Buscar cualquier <a> con href que parezca artículo
        info = await page.evaluate("""
            () => {
                const result = {};

                // Contar h2/h3 con links
                result.h2_links = document.querySelectorAll('h2 a[href]').length;
                result.h3_links = document.querySelectorAll('h3 a[href]').length;

                // Clases de los primeros 5 articles
                const articles = document.querySelectorAll('article');
                result.article_count = articles.length;
                result.article_classes = Array.from(articles).slice(0, 3).map(a => a.className);

                // Clases de h2 con links
                const h2s = document.querySelectorAll('h2 a[href]');
                result.h2_sample = Array.from(h2s).slice(0, 3).map(a => ({
                    href: a.href,
                    text: (a.innerText || '').trim().substring(0, 60),
                    parent_class: a.closest('h2')?.className || '',
                    grandparent_class: a.closest('h2')?.parentElement?.className || ''
                }));

                // Clases de h3 con links
                const h3s = document.querySelectorAll('h3 a[href]');
                result.h3_sample = Array.from(h3s).slice(0, 3).map(a => ({
                    href: a.href,
                    text: (a.innerText || '').trim().substring(0, 60),
                    parent_class: a.closest('h3')?.className || '',
                    grandparent_class: a.closest('h3')?.parentElement?.className || ''
                }));

                // Buscar divs con clase que parezca contenedor de posts
                const postDivs = document.querySelectorAll(
                    '[class*="post"],[class*="article"],[class*="entry"],[class*="card"]'
                );
                const divClasses = new Set();
                Array.from(postDivs).slice(0, 20).forEach(d => {
                    d.className.split(' ').forEach(c => {
                        if (c && (c.includes('post') || c.includes('article') || c.includes('entry') || c.includes('card')))
                            divClasses.add(c);
                    });
                });
                result.post_classes = Array.from(divClasses);

                return result;
            }
        """)

        import json
        print(json.dumps(info, indent=2, ensure_ascii=False))

        await browser.close()

asyncio.run(main())
