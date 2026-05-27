"""
Script de test para validar el scraper de lareaccioncr.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from scrapers.lareaccioncr import LaReaccionCRScraper

def test_scraper():
    """Ejecuta un test básico del scraper."""
    print("\n" + "="*70)
    print("🧪 TEST DEL SCRAPER LaReaccionCR")
    print("="*70)
    
    scraper = LaReaccionCRScraper()
    
    print("\n📍 Iniciando scraping...")
    print(f"   BASE_URL: {scraper.BASE_URL}")
    print(f"   SOURCE_NAME: {scraper.SOURCE_NAME}")
    
    records = scraper.scrape()
    
    print("\n" + "="*70)
    print("📊 RESULTADOS")
    print("="*70)
    
    if records:
        print(f"\n✅ Total de artículos extraídos: {len(records)}")
        print(f"\n📋 Primeros 5 artículos:")
        for i, record in enumerate(records[:5], 1):
            text_len = len(record.get("full_text", ""))
            print(f"\n   {i}. {record['title'][:60]}...")
            print(f"      URL: {record['url'][:70]}...")
            print(f"      Texto: {text_len} caracteres")
            print(f"      Sección: {record.get('section', 'N/A')}")
            print(f"      Fecha: {record.get('publication_date', 'N/A')}")
        
        # Estadísticas
        text_lengths = [len(r.get("full_text", "")) for r in records]
        avg_length = sum(text_lengths) / len(text_lengths) if text_lengths else 0
        min_length = min(text_lengths) if text_lengths else 0
        max_length = max(text_lengths) if text_lengths else 0
        
        print(f"\n📈 Estadísticas de extracción:")
        print(f"   Longitud promedio: {avg_length:.0f} caracteres")
        print(f"   Longitud mínima: {min_length} caracteres")
        print(f"   Longitud máxima: {max_length} caracteres")
        
        # Categorías
        sections = set(r.get("section", "") for r in records)
        print(f"\n📂 Categorías encontradas: {len(sections)}")
        for sec in sorted(sections)[:10]:
            if sec:
                print(f"   - {sec}")
    else:
        print("\n❌ No se extrajeron artículos")
    
    print("\n" + "="*70)
    print("✅ TEST COMPLETADO")
    print("="*70 + "\n")

if __name__ == "__main__":
    test_scraper()
