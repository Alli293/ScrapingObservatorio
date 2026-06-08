"""debug_sinartdigital.py — encuentra el contenedor de texto del articulo"""
import asyncio, json, sys, io
from playwright.async_api import async_playwright

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

URL = "https://sinartdigital.com/trecenoticias/nacionales/item/invitan-a-jovenes-a-reflexionar-sobre-la-conexion-humana-en-tiempos-de-pantallas?category_id=28"

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await (await browser.new_context()).new_page()
        await page.goto(URL, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(2000)

        info = await page.evaluate("""
            () => {
                const r = {};

                // div.item (ZOO framework) - hijos y parrafos
                const itemDiv = document.querySelector("div.item");
                if (itemDiv) {
                    r.item_children = Array.from(itemDiv.children).map(c =>
                        c.tagName + "." + (c.className||"").trim().replace(/\\s+/g, ".")
                    );
                    const ps = Array.from(itemDiv.querySelectorAll("p"))
                        .filter(p => (p.innerText||"").trim().length > 50);
                    r.item_p_count = ps.length;
                    r.item_p_sample = ps.slice(0,3).map(p => (p.innerText||"").trim().substring(0,100));
                } else {
                    r.item_div = "NOT FOUND";
                }

                // Selectores ZOO/Joomla comunes
                const sels = [
                    "div.pos-full", "div.pos-body", "div.pos-text",
                    "div.item-body", "div[itemprop='articleBody']",
                    "div.article-body", "span[itemprop='articleBody']",
                    "div.news-article-text"
                ];
                r.sels = {};
                sels.forEach(s => {
                    const el = document.querySelector(s);
                    r.sels[s] = el ? el.innerText.trim().substring(0, 80) : null;
                });

                // Top-5 divs con mas texto puro
                const allDivs = Array.from(document.querySelectorAll("div"));
                r.text_rich = allDivs
                    .map(d => ({ cls: (d.className||"").substring(0,60), id: d.id, len: (d.innerText||"").trim().length, kids: d.children.length }))
                    .filter(d => d.len > 400 && d.kids < 10)
                    .sort((a,b) => b.len - a.len)
                    .slice(0,5);

                return r;
            }
        """)
        print(json.dumps(info, indent=2, ensure_ascii=False))
        await browser.close()

asyncio.run(main())
