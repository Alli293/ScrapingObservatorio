"""
Debug script para inspeccionar la estructura de artículos de El Periódico CR
que no están siendo extraídos correctamente.
"""

import asyncio
from playwright.async_api import async_playwright
import json

# URLs problemáticas del último run
PROBLEM_URLS = [
    "https://elperiodicocr.com/fmi-plantea-nueva-reforma-fiscal-propone-impuestos-a-canasta-basica-salario-escolar-y-renta/",
    "https://elperiodicocr.com/contraloria-no-dio-al-mopt-el-nuevo-puente-de-la-platina/",
    "https://elperiodicocr.com/israel-y-hezbola-continuan-en-fuego-cruzado-pese-a-los-anuncios-de-donald-trump/",
]


async def debug_article(url: str):
    """Inspecciona la estructura HTML de un artículo."""
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
        page = await context.new_page()

        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=10_000)
            await page.wait_for_timeout(1500)

            # Investigar qué divs de contenido existen
            print(f"\n{'='*80}")
            print(f"URL: {url}")
            print('='*80)

            # Buscar todos los divs principales de contenido
            structures = await page.evaluate("""
            () => {
                const result = {
                    tdb_block_inner: document.querySelectorAll('div.tdb-block-inner').length,
                    article_content: document.querySelectorAll('div.article-content').length,
                    entry_content: document.querySelectorAll('div.entry-content').length,
                    td_post_content: document.querySelectorAll('div.td-post-content').length,
                    tdb_post_content: document.querySelectorAll('div.tdb-post-content').length,
                    post_content: document.querySelectorAll('div.post-content').length,
                };
                return result;
            }
            """)

            print("\n📊 Contenedores encontrados:")
            for container, count in structures.items():
                if count > 0:
                    print(f"  ✓ {container}: {count}")

            # Obtener los primeros párrafos en diferentes contenedores
            paragraph_data = await page.evaluate("""
            () => {
                const result = {};

                // En tdb-block-inner
                const blocks = document.querySelectorAll('div.tdb-block-inner');
                if (blocks.length > 0) {
                    result.tdb_block_inner = {
                        count: blocks.length,
                        paragraphs: Array.from(blocks[0].querySelectorAll('p')).slice(0, 2).map(p => p.innerText.substring(0, 100))
                    };
                }

                // En article-content
                const articleContent = document.querySelector('div.article-content');
                if (articleContent) {
                    result.article_content = {
                        count: 1,
                        paragraphs: Array.from(articleContent.querySelectorAll('p')).slice(0, 2).map(p => p.innerText.substring(0, 100))
                    };
                }

                // En td-post-content
                const tdPostContent = document.querySelector('div.td-post-content');
                if (tdPostContent) {
                    result.td_post_content = {
                        count: 1,
                        paragraphs: Array.from(tdPostContent.querySelectorAll('p')).slice(0, 2).map(p => p.innerText.substring(0, 100))
                    };
                }

                // En tdb-post-content
                const tdbPostContent = document.querySelector('div.tdb-post-content');
                if (tdbPostContent) {
                    result.tdb_post_content = {
                        count: 1,
                        paragraphs: Array.from(tdbPostContent.querySelectorAll('p')).slice(0, 2).map(p => p.innerText.substring(0, 100))
                    };
                }

                // Todos los párrafos en la página
                const allPs = document.querySelectorAll('p');
                result.all_paragraphs = {
                    total: allPs.length,
                    first_few: Array.from(allPs).slice(0, 3).map(p => p.innerText.substring(0, 100))
                };

                return result;
            }
            """)

            print("\n📝 Párrafos encontrados:")
            print(json.dumps(paragraph_data, indent=2, ensure_ascii=False))

            # Obtener el HTML principal para análisis
            main_content = await page.evaluate("""
            () => {
                // Buscar el contenedor principal de contenido
                const containers = [
                    document.querySelector('div.td-post-content'),
                    document.querySelector('div.article-content'),
                    document.querySelector('article'),
                    document.querySelector('div.post-content'),
                ];

                for (let cont of containers) {
                    if (cont) {
                        const html = cont.innerHTML;
                        if (html.length > 0) {
                            return {
                                container: cont.className,
                                html_preview: html.substring(0, 500),
                                total_length: html.length
                            };
                        }
                    }
                }

                return { message: "No se encontró contenedor principal" };
            }
            """)

            print("\n🔍 Contenedor principal:")
            print(json.dumps(main_content, indent=2, ensure_ascii=False))

        except Exception as e:
            print(f"❌ Error: {e}")
        finally:
            await page.close()
            await browser.close()


async def main():
    """Ejecuta el debug para todas las URLs."""
    for url in PROBLEM_URLS:
        await debug_article(url)
        await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.run(main())
