import pathlib
import re
from pathlib import Path

root = Path('scrapers')
files = sorted([p.name for p in root.glob('*.py')])
ignore = {'base_scraper.py','observatorio_adapter.py','wordpress_adapter.py','wordpress_sites.py','__init__.py'}
registered = set()
text = Path('main.py').read_text(encoding='utf-8')
for match in re.finditer(r'"([a-z0-9_]+)"\s*:\s*\(', text):
    registered.add(match.group(1))

missing_files = [f for f in files if f not in ignore and f[:-3] not in registered]

for f in missing_files:
    data = Path('scrapers') / f
    content = data.read_text(encoding='utf-8', errors='ignore')
    class_lines = [line.strip() for line in content.splitlines() if line.strip().startswith('class ')]
    has_df = 'df =' in content or 'df=' in content
    has_df_var = 'df4' in content or 'df6' in content or 'df8' in content or 'df3' in content or 'params' in content
    print(f'-- {f} -- class={len(class_lines)} df={has_df}')
    if class_lines:
        for line in class_lines:
            print(line)
    print()

print('COUNT MISSING', len(missing_files))
