"""
Extractor de noticias de las dos newsletters: Alimarket y Financial Food.
Lee los .msg, parsea texto plano, identifica titulares y enlaces,
desenvuelve URLs de SafeLinks y genera registros estructurados.
"""
import os
import re
import sys
import json
from datetime import datetime
from urllib.parse import unquote, parse_qs, urlparse
from email.utils import parsedate_to_datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from msg_parser import parse_msg


# ============================================================
# Helpers
# ============================================================
SAFELINK_RE = re.compile(r'<(https?://[^>]+)>')
URL_INLINE_RE = re.compile(r'https?://\S+')

def unwrap_safelink(url: str) -> str:
    """Desenvuelve URLs de Microsoft SafeLinks."""
    if 'safelinks.protection.outlook.com' in url:
        try:
            qs = parse_qs(urlparse(url).query)
            if 'url' in qs:
                return unquote(qs['url'][0])
        except Exception:
            pass
    return url


def parse_date_from_headers(headers: str) -> datetime:
    """Extrae la fecha del email de las cabeceras MIME."""
    if not headers:
        return None
    # Busca línea Date:
    for line in headers.split('\n'):
        if line.lower().startswith('date:'):
            try:
                return parsedate_to_datetime(line[5:].strip())
            except Exception:
                pass
    return None


# ============================================================
# Extractor: Financial Food
# ============================================================
# Estructura: titular en línea propia, URL del titular, descripción, "Leer más" + URL
def extract_financialfood(text: str) -> list:
    """Extrae noticias de Financial Food."""
    # Tokenizar: separar URLs en marcadores y trabajar con líneas
    # Reemplazamos cada URL <...> por un token URL_N y guardamos las URLs en un dict
    urls = []
    def replace_url(m):
        urls.append(unwrap_safelink(m.group(1)))
        return f'\x00URL{len(urls)-1}\x00'
    
    text2 = SAFELINK_RE.sub(replace_url, text)
    # Tabs a espacios, líneas limpias
    text2 = text2.replace('\t', ' ')
    text2 = re.sub(r' +', ' ', text2)
    lines = [l.strip() for l in text2.split('\n')]
    # Filtrar líneas vacías o solo whitespace, mantener tokens URL como sus propias líneas
    
    items = []
    i = 0
    seen_titles = set()
    while i < len(lines):
        line = lines[i]
        # Skip vacías, líneas que son solo URLs, o publicidad/headers
        if (not line
            or re.fullmatch(r'(\x00URL\d+\x00\s*)+', line)
            or 'PUBLICIDAD' in line
            or line.lower().startswith('leer más')
            or line.lower().startswith('si no visualiza')
            or line.lower().startswith('publicidad')
            or 'mailpoet_router' in line.lower()):
            i += 1
            continue
        
        # Es un titular si es una frase larga sin URLs y la siguiente no vacía es URL+descripción+leer más
        # Heurística: tiene >25 chars, no es texto del pie/header
        if len(line) > 25 and 'mailto:' not in line and not line.startswith('Boletín'):
            # Verificar si parece un titular (no contiene marca de URL, no es pie de página)
            if '\x00URL' in line:
                # podría tener URL embebida; quitarla y ver si queda titular
                clean = re.sub(r'\x00URL\d+\x00', '', line).strip()
                if len(clean) < 25:
                    i += 1
                    continue
                line = clean
            
            # Filtros para descartar líneas de pie de página, suscripción, etc.
            lower = line.lower()
            if any(skip in lower for skip in [
                'darse de baja', 'unsubscribe', 'mailpoet', 'política de privacidad',
                'gestiona las newsletter', 'enviado a:', 'aviso legal',
                'has recibido este mail', 'es un mail automático',
                'añadir', 'libreta de direcciones', 'redes sociales',
                'ver en el navegador', 'siguenos', 'síguenos',
                'newsletter', 'boletin', 'boletín', 'noticias destacadas',
                'noticias de', 'todas las noticias',
            ]) and len(line) < 80:
                i += 1
                continue
            
            # Buscar la URL "leer más" más próxima (siguientes ~10 líneas)
            url = None
            description = None
            j = i + 1
            scan_limit = min(i + 12, len(lines))
            while j < scan_limit:
                ln = lines[j].strip()
                if not ln:
                    j += 1
                    continue
                # Si contiene "Leer más", capturar URL embebida
                if 'leer más' in ln.lower():
                    m = re.search(r'\x00URL(\d+)\x00', ln)
                    if m:
                        url = urls[int(m.group(1))]
                    j += 1
                    break
                # Si es texto descriptivo (no solo URLs), capturarlo como descripción
                clean_ln = re.sub(r'\x00URL\d+\x00', '', ln).strip()
                if (clean_ln and len(clean_ln) > 30
                    and 'PUBLICIDAD' not in clean_ln
                    and 'mailto:' not in clean_ln):
                    if description is None:
                        description = clean_ln
                    else:
                        description += ' ' + clean_ln
                j += 1
            
            # Si no encontramos URL "leer más", buscar la primera URL después del titular
            if not url:
                for k in range(i + 1, min(i + 5, len(lines))):
                    m = re.search(r'\x00URL(\d+)\x00', lines[k])
                    if m:
                        candidate = urls[int(m.group(1))]
                        if 'mailpoet_router' in candidate or 'financialfood.es' in candidate:
                            url = candidate
                            break
            
            # Validar: tiene que tener URL para ser noticia válida
            if url and line not in seen_titles:
                seen_titles.add(line)
                items.append({
                    'title': line,
                    'summary': description or '',
                    'url': url,
                })
            i = j
        else:
            i += 1
    
    return items


# ============================================================
# Extractor: Alimarket FoodTech
# ============================================================
# Estructura: cada noticia tiene URL, titular, descripción, "Sigue leyendo" o URL
def extract_alimarket_foodtech(text: str) -> list:
    """Extrae noticias de Newsletter FoodTech de Alimarket."""
    urls = []
    def replace_url(m):
        urls.append(unwrap_safelink(m.group(1)))
        return f'\x00URL{len(urls)-1}\x00'
    
    text2 = SAFELINK_RE.sub(replace_url, text)
    text2 = text2.replace('\t', ' ')
    text2 = re.sub(r' +', ' ', text2)
    lines = [l.strip() for l in text2.split('\n')]
    
    items = []
    seen_titles = set()
    in_news = False  # Empezamos a extraer tras "ESTA SEMANA DESTACAMOS"
    
    stop_markers = [
        'gestiona las newsletter',
        'has recibido este mail',
        'dejar de recibir',
        'cuestión de confianza',
        'alimarket en las redes',
        'quienes somos',
        'cliente@alimarket',
        'publicaciones alimarket',
    ]
    
    i = 0
    while i < len(lines):
        line = lines[i]
        lower = line.lower()
        
        # Empezar a procesar tras la sección destacada
        if 'esta semana destacamos' in lower or 'destacamos' in lower or 'noticias' in lower:
            in_news = True
            i += 1
            continue
        
        if any(m in lower for m in stop_markers):
            break
        
        if not in_news:
            i += 1
            continue
        
        # Quitar URLs embebidas para evaluar el texto
        clean = re.sub(r'\x00URL\d+\x00', '', line).strip()
        # También quitar barras "________________________________"
        clean = re.sub(r'_{5,}', '', clean).strip()
        
        if len(clean) < 25:
            i += 1
            continue
        
        # Saltar líneas conocidas que no son titulares
        if any(skip in lower for skip in [
            'sigue leyendo', 'leer más', 'ver en el navegador',
            'añadir', 'libreta de direcciones', 'mailto:',
            'foodtech', 'newsletter',
        ]) and len(clean) < 60:
            i += 1
            continue
        
        # Buscar URL antes (típico) o después
        url = None
        # Primera prioridad: URL en línea inmediatamente anterior (que aparece antes del titular)
        for k in range(max(0, i-2), i):
            m = re.search(r'\x00URL(\d+)\x00', lines[k])
            if m:
                cand = urls[int(m.group(1))]
                if 'alimarket' in cand or 'acemlnc' in cand:
                    url = cand
                    break
        
        # Capturar descripción: la línea siguiente no vacía con > 30 chars que no sea solo URL
        description = None
        for k in range(i+1, min(i+5, len(lines))):
            ln = lines[k].strip()
            ln_clean = re.sub(r'\x00URL\d+\x00', '', ln).strip()
            ln_clean = re.sub(r'_{5,}', '', ln_clean).strip()
            ll = ln_clean.lower()
            if (ln_clean and len(ln_clean) > 30
                and not ll.startswith('sigue leyendo')
                and not ll.startswith('leer más')):
                description = ln_clean
                break
            if 'sigue leyendo' in ll or 'leer más' in ll:
                break
        
        if url and clean not in seen_titles:
            seen_titles.add(clean)
            items.append({
                'title': clean,
                'summary': description or '',
                'url': url,
            })
        i += 1
    
    return items


# ============================================================
# Extractor: Alimarket (general)
# ============================================================
# Estructura más simple: titular + URL inmediata. No hay descripciones en plain text.
def extract_alimarket(text: str) -> list:
    """Extrae noticias de Alimarket."""
    urls = []
    def replace_url(m):
        urls.append(unwrap_safelink(m.group(1)))
        return f'\x00URL{len(urls)-1}\x00'
    
    text2 = SAFELINK_RE.sub(replace_url, text)
    text2 = text2.replace('\t', ' ')
    text2 = re.sub(r' +', ' ', text2)
    lines = [l.strip() for l in text2.split('\n')]
    
    items = []
    seen_titles = set()
    in_news_section = False  # Solo extraer cuando estamos en sección de Noticias
    
    # Stop markers: secciones que NO son noticias
    stop_markers = [
        'informes y reportajes',
        'encuentra los establecimientos',
        'encuentra marcas',
        'mdd alimarket',
        'alimarket en las redes',
        'quienes somos',
        'cuestión de confianza',
        'gestiona las newsletter',
        'dejar de recibir',
        'has recibido este mail',
    ]
    
    for i, line in enumerate(lines):
        lower = line.lower()
        
        # Detectar inicio de sección de noticias
        if 'noticias de' in lower and len(line) < 80:
            in_news_section = True
            continue
        if 'ver más noticias' in lower:
            in_news_section = False
            continue
        if any(m in lower for m in stop_markers):
            in_news_section = False
            continue
        
        if not in_news_section:
            continue
        
        # Quitar URL del titular si está embebida
        clean = re.sub(r'\x00URL\d+\x00', '', line).strip()
        if len(clean) < 25:
            continue
        
        # Extraer URL embebida en la misma línea
        m = re.search(r'\x00URL(\d+)\x00', line)
        url = None
        if m:
            url = urls[int(m.group(1))]
        else:
            # Buscar en la línea anterior (suele tener URL inmediata antes)
            if i > 0:
                m2 = re.search(r'\x00URL(\d+)\x00', lines[i-1])
                if m2:
                    url = urls[int(m2.group(1))]
        
        # Validar que la URL es del sistema de tracking de Alimarket
        if url and ('alimarket' in url or 'acemlnc' in url):
            if clean not in seen_titles:
                seen_titles.add(clean)
                items.append({
                    'title': clean,
                    'summary': '',  # No disponible en plain text de Alimarket
                    'url': url,
                })
    
    return items


# ============================================================
# Extractor principal
# ============================================================
def extract_from_msg(path: str) -> dict:
    """Extrae todas las noticias de un único .msg."""
    msg = parse_msg(path)
    sender = (msg['sender_smtp'] or msg['sender_email'] or '').lower()
    
    # Determinar fecha del email
    date = parse_date_from_headers(msg['headers'])
    if not date:
        # Intentar extraer del nombre del archivo o del subject
        subj = msg['subject'] or ''
        m = re.search(r'(\d{1,2})[/_](\d{1,2})[/_](\d{2,4})', subj)
        if m:
            try:
                d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
                if y < 100:
                    y += 2000
                date = datetime(y, mo, d)
            except Exception:
                date = None
    
    text = msg['body_plain'] or ''
    
    if 'alimarket' in sender:
        # Distinguir FoodTech (estructura distinta) de Alimentación general
        subj = (msg['subject'] or '').lower()
        if 'foodtech' in subj:
            source = 'Alimarket FoodTech'
            items = extract_alimarket_foodtech(text)
        else:
            source = 'Alimarket'
            items = extract_alimarket(text)
    elif 'financialfood' in sender:
        source = 'Financial Food'
        items = extract_financialfood(text)
    else:
        # Email reenviado u otro: intentar adivinar
        if 'alimarket' in text.lower():
            source = 'Alimarket (reenviado)'
            items = extract_alimarket(text)
        elif 'financialfood' in text.lower():
            source = 'Financial Food (reenviado)'
            items = extract_financialfood(text)
        else:
            source = 'Desconocida'
            items = []
    
    return {
        'file': os.path.basename(path),
        'source': source,
        'date': date,
        'subject': msg['subject'],
        'items': items,
    }


# ============================================================
# Main: procesar todo y devolver estadísticas
# ============================================================
if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--dir', default='mails', help='Directorio con subcarpetas zip*')
    parser.add_argument('--limit', type=int, default=None)
    parser.add_argument('--show', action='store_true', help='Mostrar primeros resultados')
    args = parser.parse_args()
    
    all_items = []
    file_stats = []
    count = 0
    for sub in sorted(os.listdir(args.dir)):
        subpath = os.path.join(args.dir, sub)
        if not os.path.isdir(subpath):
            continue
        for fname in sorted(os.listdir(subpath)):
            if not fname.endswith('.msg'):
                continue
            path = os.path.join(subpath, fname)
            try:
                result = extract_from_msg(path)
                file_stats.append({
                    'file': fname,
                    'source': result['source'],
                    'date': result['date'].isoformat() if result['date'] else None,
                    'item_count': len(result['items']),
                })
                for item in result['items']:
                    item['source'] = result['source']
                    item['date'] = result['date'].isoformat() if result['date'] else None
                    item['source_file'] = fname
                    all_items.append(item)
            except Exception as e:
                print(f'ERROR en {fname}: {e}', file=sys.stderr)
            count += 1
            if args.limit and count >= args.limit:
                break
        if args.limit and count >= args.limit:
            break
    
    # Stats
    from collections import Counter
    by_source = Counter(it['source'] for it in all_items)
    print(f'Procesados {count} emails, {len(all_items)} noticias extraídas')
    print('Por fuente:')
    for s, c in by_source.most_common():
        print(f'  {c:5d}  {s}')
    
    # Emails con 0 noticias
    zero = [f for f in file_stats if f['item_count'] == 0]
    print(f'\nEmails sin noticias extraídas: {len(zero)}')
    if zero[:5]:
        for f in zero[:5]:
            print(f'  {f["file"]} ({f["source"]})')
    
    # Distribución items por email
    counts = [f['item_count'] for f in file_stats if f['item_count'] > 0]
    if counts:
        print(f'\nNoticias por email: media={sum(counts)/len(counts):.1f}, '
              f'min={min(counts)}, max={max(counts)}')
    
    if args.show:
        print('\n--- Primeras 5 noticias ---')
        for it in all_items[:5]:
            print(f'\n[{it["source"]}] {it["date"]}')
            print(f'TITULO: {it["title"]}')
            if it['summary']:
                print(f'RESUMEN: {it["summary"][:200]}')
            print(f'URL: {it["url"][:100]}')
