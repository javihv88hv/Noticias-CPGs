"""
Regenera el HTML de la web procesando correos nuevos (.msg) y combinándolos
con las noticias ya existentes en noticias.json.

USO:
  python rebuild.py --new-emails carpeta_con_msg --existing noticias.json --template template.html --out boletin-fb.html

Si no hay correos nuevos, simplemente regenera el HTML con los datos existentes.
"""
import os
import sys
import json
import argparse
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from extract_news import extract_from_msg
from classify import classify_news


def collect_from_dir(directory):
    """Procesa todos los .msg de un directorio (recursivo)."""
    items = []
    if not directory or not os.path.isdir(directory):
        return items
    for root, _, files in os.walk(directory):
        for fname in files:
            if not fname.endswith(('.msg', '.eml')):
                continue
            path = os.path.join(root, fname)
            try:
                result = extract_from_msg(path)
                for it in result['items']:
                    it['date'] = result['date'].isoformat() if result['date'] else None
                    it['source'] = result['source']
                    items.append(it)
            except Exception as e:
                print(f'  Error en {fname}: {e}', file=sys.stderr)
    return items


def deduplicate(items):
    """Deduplica por (título normalizado, fuente abreviada)."""
    seen = {}
    for it in items:
        norm_title = ' '.join((it.get('title') or '').lower().split())
        source_short = (it.get('source') or '').split(' ')[0]
        key = (norm_title, source_short)
        if key not in seen:
            seen[key] = it
        else:
            # Mantener el que tenga mejor descripción
            existing = seen[key]
            if len(it.get('summary') or '') > len(existing.get('summary') or ''):
                seen[key] = it
    return list(seen.values())


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--new-emails', help='Directorio con .msg nuevos (opcional)')
    p.add_argument('--existing', default='noticias.json',
                   help='JSON con las noticias ya procesadas')
    p.add_argument('--template', default='template.html',
                   help='Plantilla HTML donde inyectar los datos')
    p.add_argument('--out', default='boletin-fb.html',
                   help='HTML resultante')
    args = p.parse_args()
    
    # 1. Cargar noticias existentes
    existing = []
    if os.path.exists(args.existing):
        with open(args.existing, 'r', encoding='utf-8') as f:
            existing = json.load(f)
        print(f'Noticias existentes: {len(existing):,}')
    
    # 2. Procesar correos nuevos
    new_items = []
    if args.new_emails:
        print(f'Procesando .msg de: {args.new_emails}')
        new_items = collect_from_dir(args.new_emails)
        print(f'Noticias extraídas de correos nuevos: {len(new_items):,}')
    
    # 3. Combinar y deduplicar
    combined = existing + new_items
    deduped = deduplicate(combined)
    print(f'Total tras deduplicar: {len(deduped):,}')
    
    # 4. Reclasificar todas (sectores y empresas) - rápido y consistente
    print('Clasificando noticias…')
    deduped = classify_news(deduped)
    
    # 5. Ordenar por fecha descendente
    deduped.sort(
        key=lambda x: x.get('date') or '',
        reverse=True
    )
    
    # 6. Guardar JSON actualizado
    with open(args.existing, 'w', encoding='utf-8') as f:
        json.dump(deduped, f, ensure_ascii=False, separators=(',', ':'))
    print(f'JSON actualizado: {args.existing}')
    
    # 7. Generar HTML inyectando datos en la plantilla
    with open(args.template, 'r', encoding='utf-8') as f:
        template = f.read()
    
    data_min = json.dumps(deduped, ensure_ascii=False, separators=(',', ':'))
    data_script = f'<script>window.__NEWS_DATA__ = {data_min};</script>\n<script>'
    marker = '<script>\n  /* ============ DATA INJECTION ============ */'
    
    if marker in template:
        html = template.replace(marker, data_script + '\n  /* ============ DATA INJECTION ============ */')
    else:
        # La plantilla ya tiene datos: reemplazar el bloque
        import re
        html = re.sub(
            r'<script>window\.__NEWS_DATA__ = \[.*?\];</script>',
            f'<script>window.__NEWS_DATA__ = {data_min};</script>',
            template,
            count=1,
            flags=re.DOTALL
        )
    
    with open(args.out, 'w', encoding='utf-8') as f:
        f.write(html)
    
    size_mb = os.path.getsize(args.out) / 1024 / 1024
    print(f'HTML generado: {args.out} ({size_mb:.2f} MB)')
    
    # Stats
    from collections import Counter
    sources = Counter(n.get('source') for n in deduped)
    print('\nNoticias por fuente:')
    for s, c in sources.most_common():
        print(f'  {c:5,}  {s}')


if __name__ == '__main__':
    main()
