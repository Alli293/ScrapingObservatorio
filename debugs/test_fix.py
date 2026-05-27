"""
Test rápido para validar el nuevo selector con el artículo problemático
"""
import asyncio
from playwright.async_api import async_playwright

TARGET_URL = "https://elperiodicocr.com/costa-rica-sale-del-mapa-del-hambre-un-logro-destacado-por-la-fao/"

def clean_text(text: str) -> str:
    """Limpia espacios múltiples y saltos de línea innecesarios."""
    import re
    text = re.sub(r"\s+", " ", text)
    return text.strip()

async def test_new_selector():
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
            
            # Nuevo selector: div.td-post-content
            content_container = await page.query_selector("div.td-post-content")
            
            if not content_container:
                print("⚠️  div.td-post-content no encontrado, intentando article...")
                content_container = await page.query_selector("article")
            
            if content_container:
                p_elements = await content_container.query_selector_all("p")
                print(f"✅ Contenedor encontrado: {len(p_elements)} párrafos")
                
                paragraphs = []
                for p in p_elements:
                    p_text = await p.inner_text()
                    p_text = clean_text(p_text)
                    
                    if not p_text or len(p_text) < 10:
                        continue
                    if "adsbygoogle" in p_text.lower():
                        continue
                    
                    paragraphs.append(p_text)
                
                print(f"✅ Párrafos válidos después de filtrado: {len(paragraphs)}")
                
                if paragraphs:
                    full_text = "\n\n".join(paragraphs)
                    print(f"✅ Texto total: {len(full_text)} caracteres")
                    print(f"\n📋 Primeros 300 caracteres:\n{full_text[:300]}...")
                    print(f"\n✅ EL SCRAPER DEBERÍA FUNCIONAR CORRECTAMENTE")
                else:
                    print("❌ No hay párrafos válidos después del filtrado")
            else:
                print("❌ Contenedor NO encontrado")
            
        except Exception as e:
            print(f"❌ Error: {e}")
            import traceback
            traceback.print_exc()
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(test_new_selector())
