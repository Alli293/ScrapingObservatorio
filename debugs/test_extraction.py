"""
Debug script para probar la extracción de artículos.
Verifica si la corrección funciona en uno de los artículos problemáticos.
"""

import asyncio
from playwright.async_api import async_playwright
import re

CR_TZ_OFFSET = -6

def clean_text(text: str) -> str:
    """Limpia espacios múltiples y saltos de línea innecesarios."""
    text = re.sub(r"\s+", " ", text)
    return text.strip()


async def test_article_extraction():
    """Prueba la extracción de un artículo."""
    
    # Una de las URLs que antes fallaba
    test_url = "https://elperiodicocr.com/fmi-plantea-nueva-reforma-fiscal-propone-impuestos-a-canasta-basica-salario-escolar-y-renta/"
    
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
            print(f"📄 Cargando: {test_url}")
            await page.goto(test_url, wait_until="domcontentloaded", timeout=10_000)
            await page.wait_for_timeout(1500)

            # Extraer texto
            paragraphs_collected = []

            # Intentar primero con td-post-content
            main_content = await page.query_selector("div.td-post-content")
            
            print(f"\n✓ div.td-post-content encontrado: {main_content is not None}")
            
            if main_content:
                p_elements = await main_content.query_selector_all("p")
                print(f"✓ Párrafos en td-post-content: {len(p_elements)}")
                
                for i, p in enumerate(p_elements):
                    p_text = await p.inner_text()
                    p_text = clean_text(p_text)

                    if not p_text or len(p_text) < 10:
                        continue
                    if "adsbygoogle" in p_text.lower():
                        continue
                    if "leer más" in p_text.lower():
                        continue

                    paragraphs_collected.append(p_text)
                    if i < 3:
                        print(f"  [{i+1}] {p_text[:80]}...")

            # Deduplicar
            seen = set()
            unique_paragraphs = []
            for p in paragraphs_collected:
                if p not in seen:
                    seen.add(p)
                    unique_paragraphs.append(p)

            full_text = "\n\n".join(unique_paragraphs)

            print(f"\n{'='*80}")
            print(f"✅ RESULTADO:")
            print(f"   Párrafos extraídos: {len(unique_paragraphs)}")
            print(f"   Caracteres totales: {len(full_text)}")
            print(f"\n📝 Primeros 300 caracteres del texto:")
            print(f"   {full_text[:300]}...")
            print(f"{'='*80}")

            if len(full_text) > 100:
                print("\n✨ ¡Extracción exitosa!")
                return True
            else:
                print("\n❌ No se extrajo suficiente texto")
                return False

        except Exception as e:
            print(f"❌ Error: {e}")
            import traceback
            traceback.print_exc()
            return False
        finally:
            await page.close()
            await browser.close()


if __name__ == "__main__":
    result = asyncio.run(test_article_extraction())
    exit(0 if result else 1)
