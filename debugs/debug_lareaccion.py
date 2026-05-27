"""
Script de debugging para inspeccionar la estructura de lareaccioncr.com
y encontrar el selector correcto del bloque ARCHIVO
"""
import asyncio
from playwright.async_api import async_playwright
import json

async def debug_archive_structure():
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
            # Probar diferentes URLs base
            base_urls = [
                "https://lareaccioncr.com/",
                "https://lareaccioncr.com/2026/",
                "https://lareaccioncr.com/2026",
            ]
            
            for base_url in base_urls:
                print(f"\n{'='*70}")
                print(f"📄 Probando URL: {base_url}")
                print(f"{'='*70}")
                
                try:
                    await page.goto(base_url, wait_until="domcontentloaded", timeout=20_000)
                    await page.wait_for_timeout(2000)
                    
                    # 1. Buscar el selector wp-block-archives-list (que menciona el código actual)
                    print("\n🔍 BUSCANDO: ul.wp-block-archives-list")
                    archive_wp = await page.query_selector_all("ul.wp-block-archives-list li a")
                    print(f"   Encontrados: {len(archive_wp)} enlaces")
                    if archive_wp and len(archive_wp) <= 10:
                        for i, link in enumerate(archive_wp[:5]):
                            href = await link.get_attribute("href")
                            text = await link.inner_text()
                            print(f"     - {text}: {href}")
                    
                    # 2. Buscar bloques de archivo alternativos
                    archive_selectors = [
                        ("ul.wp-block-archives", "Lista de archivos WordPress"),
                        ("div.wp-block-archives", "Div de archivos WordPress"),
                        ("aside.widget_archive", "Widget de archivo (sidebar)"),
                        ("ul[class*='archive']", "UL con archive en clase"),
                        ("div[class*='archive']", "DIV con archive en clase"),
                        (".sidebar ul", "Listas en sidebar"),
                        ("nav ul", "Navegación con listas"),
                    ]
                    
                    for selector, desc in archive_selectors:
                        els = await page.query_selector_all(selector)
                        if els:
                            print(f"\n✓ {desc}")
                            print(f"   Selector: {selector}")
                            print(f"   Encontrados: {len(els)} elementos")
                            
                            # Para el primero con contenido, mostrar más detalles
                            if selector == "ul.wp-block-archives":
                                for el in els[:2]:
                                    links = await el.query_selector_all("li a")
                                    print(f"     - {len(links)} enlaces dentro")
                                    for link in links[:3]:
                                        text = await link.inner_text()
                                        href = await link.get_attribute("href")
                                        print(f"       • {text.strip()}")
                    
                    # 3. Buscar elementos con palabra "ARCHIVO" o "Archivo"
                    print("\n🔍 BUSCANDO ELEMENTOS CON 'ARCHIVO':")
                    headings = await page.evaluate("""
                        () => {
                            const results = [];
                            document.querySelectorAll('*').forEach(el => {
                                const text = el.innerText || el.textContent || '';
                                if (text.toLowerCase().includes('archivo') && 
                                    (el.tagName === 'H1' || el.tagName === 'H2' || 
                                     el.tagName === 'H3' || el.tagName === 'H4' ||
                                     el.classList.toString().includes('title') ||
                                     el.classList.toString().includes('widget'))) {
                                    results.push({
                                        tag: el.tagName,
                                        class: el.className,
                                        text: text.trim().substring(0, 50),
                                    });
                                }
                            });
                            return results.slice(0, 5);
                        }
                    """)
                    for item in headings:
                        print(f"   {item['tag']}.{item['class']}: {item['text']}")
                    
                    # 4. Inspeccionar estructura general del sidebar
                    print("\n🔍 ESTRUCTURA DEL SIDEBAR:")
                    sidebar_info = await page.evaluate("""
                        () => {
                            const results = [];
                            // Buscar sidebars comunes
                            const sidebars = document.querySelectorAll(
                                'aside, .sidebar, [class*="sidebar"], .widget-area'
                            );
                            
                            sidebars.forEach((sidebar, i) => {
                                const widgets = sidebar.querySelectorAll('[class*="widget"]');
                                const lists = sidebar.querySelectorAll('ul');
                                results.push({
                                    selector: sidebar.className || sidebar.tagName,
                                    widgets: widgets.length,
                                    lists: lists.length,
                                    children: sidebar.children.length,
                                });
                            });
                            return results.slice(0, 5);
                        }
                    """)
                    for sidebar in sidebar_info:
                        print(f"   {sidebar['selector']}: {sidebar['widgets']} widgets, {sidebar['lists']} listas")
                    
                    # 5. Dump parcial del HTML para análisis manual
                    print("\n💾 Guardando HTML para análisis...")
                    html = await page.content()
                    with open("debug_lareaccion.html", "w", encoding="utf-8") as f:
                        f.write(html)
                    print("   ✓ HTML guardado en: debug_lareaccion.html")
                    
                    break  # Si encontramos contenido, no seguir probando URLs
                    
                except Exception as e:
                    print(f"   ❌ Error: {e}")
                    continue
            
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(debug_archive_structure())
