"""
Script para debuggear un artículo específico y ver su estructura HTML
"""
import asyncio
from playwright.async_api import async_playwright

TARGET_URL = "https://elperiodicocr.com/costa-rica-sale-del-mapa-del-hambre-un-logro-destacado-por-la-fao/"

async def debug_article():
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
            print(f"📄 Visitando: {TARGET_URL}")
            await page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=20_000)
            await page.wait_for_timeout(3000)
            
            # Buscar diferentes selectores de contenido
            print("\n🔍 ANÁLISIS DE SELECTORES:")
            
            # 1. tdb-block-inner
            blocks = await page.query_selector_all("div.tdb-block-inner")
            print(f"✓ div.tdb-block-inner: {len(blocks)} encontrados")
            
            # 2. Párrafos dentro de tdb-block-inner
            if blocks:
                for i, block in enumerate(blocks[:3]):  # primeros 3
                    ps = await block.query_selector_all("p")
                    print(f"  - Bloque {i}: {len(ps)} párrafos")
            
            # 3. td-post-content
            td_content = await page.query_selector("div.td-post-content")
            if td_content:
                ps_content = await td_content.query_selector_all("p")
                print(f"✓ div.td-post-content: {len(ps_content)} párrafos")
            else:
                print("✗ div.td-post-content: NO ENCONTRADO")
            
            # 4. entry-content
            entry = await page.query_selector("div.entry-content")
            if entry:
                ps_entry = await entry.query_selector_all("p")
                print(f"✓ div.entry-content: {len(ps_entry)} párrafos")
            else:
                print("✗ div.entry-content: NO ENCONTRADO")
            
            # 5. Párrafos globales
            all_ps = await page.query_selector_all("p")
            print(f"✓ Párrafos totales en la página: {len(all_ps)}")
            
            # 6. Contenedores principales (buscar por clases comunes)
            print("\n📦 CONTENEDORES PRINCIPALES:")
            main_selectors = [
                ("article", "article"),
                ("div[role='main']", "div[role='main']"),
                ("div.post", "div.post"),
                ("div.article", "div.article"),
                ("main", "main"),
            ]
            
            for selector, label in main_selectors:
                el = await page.query_selector(selector)
                if el:
                    print(f"✓ {label}: ENCONTRADO")
                    ps = await el.query_selector_all("p")
                    print(f"  - {len(ps)} párrafos dentro")
            
            # Mostrar un extracto del texto del contenedor principal
            print("\n📋 TEXTO EXTRAÍDO (primeros 500 caracteres):")
            page_text = await page.inner_text()
            print(page_text[:500] + "...")
            
            # Guardar el HTML para inspección
            full_html = await page.content()
            with open("debug_article.html", "w", encoding="utf-8") as f:
                f.write(full_html)
            print("\n✅ HTML guardado en: debug_article.html")
            
        except Exception as e:
            print(f"❌ Error: {e}")
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(debug_article())
