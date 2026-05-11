"""
Extractor de noticias de las dos newsletters: Alimarket y Financial Food.
Soporta archivos .msg (Outlook) y .eml (Gmail/estándar) de forma transparente.

Detecta URLs en dos formatos:
- Outlook plain text: <https://url.com>
- Gmail Markdown: [Texto](https://url.com)
"""
import os
import re
import sys
import email
from email import policy
from datetime import datetime
from urllib.parse import unquote, parse_qs, urlparse
from email.utils import parsedate_to_datetime

try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from msg_parser import parse_msg


# Regex para URLs en formato Outlook: <https://url>
URL_OUTLOOK_RE = re.compile(r'<(https?://[^>]+)>')
# Regex para URLs en formato Gmail Markdown: [texto](https://url)
URL_MARKDOWN_RE = re.compile(r'\[([^\]]*?)\]\((https?://[^)]+)\)')


def unwrap_safelink(url: str) -> str:
    if 'safelinks.protection.outlook.com' in url:
        try:
            qs = parse_qs(urlparse(url).query)
            if 'url' in qs:
                return unquote(qs['url'][0])
        except Exception:
            pass
    return url


def normalize_urls_to_outlook_format(text: str) -> str:
    """
    Convierte URLs en formato Markdown a formato Outlook simple,
    para que ambos extractores funcionen con un único formato interno.
    
    Markdown: [Texto](https://url)  →  Texto <https://url>
    Outlook:  <https://url>          →  se mantiene
    """
    def replace_md(m):
        link_text = m.group(1).strip()
        url = m.group(2)
        if link_text:
            return f'{link_text} <{url}>'
        return f'<{url}>'
    
    return URL_MARKDOWN_RE.sub(replace_md, text)


def parse_eml_file(path: str) -> dict:
    """Parsea un archivo .eml (formato estándar)."""
    with open(path, 'rb') as f:
        msg = email.message_from_binary_file(f, policy=policy.default)
    
    subject = msg.get('subject', '')
    from_field = msg.get('from', '')
    
    sender_email = ''
    sender_name = ''
    m = re.match(r'(.*?)<(.+?)>', from_field)
    if m:
        sender_name = m.group(1).strip().strip('"')
        sender_email = m.group(2).strip()
    else:
        sender_email = from_field.strip()
    
    body_plain = ''
    body_html = ''
    for part in msg.walk():
        ctype = part.get_content_type()
        if ctype == 'text/plain' and not body_plain:
            try:
                body_plain = part.get_content()
            except Exception:
                payload = part.get_payload(decode=True) or b''
                body_plain = payload.decode('utf-8', errors='replace')
        elif ctype == 'text/html' and not body_html:
            try:
                body_html = part.get_content()
            except Exception:
                payload = part.get_payload(decode=True) or b''
                body_html = payload.decode('utf-8', errors='replace')
    
    # Si no hay texto plano, derivarlo del HTML
    if not body_plain and body_html:
        text = re.sub(r'<style[^>]*>.*?</style>', '', body_html, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<a [^>]*href="([^"]+)"[^>]*>(.*?)</a>',
                      lambda m: f'{re.sub(r"<[^>]+>", "", m.group(2))} <{m.group(1)}>',
                      text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<br[^>]*>', '\n', text, flags=re.IGNORECASE)
        text = re.sub(r'</p>', '\n\n', text, flags=re.IGNORECASE)
        text = re.sub(r'<[^>]+>', '', text)
        import html as html_mod
        text = html_mod.unescape(text)
        body_plain = text
    
    # ⚠️ CLAVE: convertir URLs Markdown a formato Outlook para unificar
    body_plain = normalize_urls_to_outlook_format(body_plain)
    
    headers_raw = ''
    for k, v in msg.items():
        headers_raw += f'{k}: {v}\n'
    
    return {
        'subject': subject,
        'sender_name': sender_name,
        'sender_email': sender_email,
        'sender_smtp': sender_email,
        'body_plain': body_plain,
        'body_html': body_html,
        'headers': headers_raw,
        'submit_time': msg.get('date'),
        'delivery_time': msg.get('date'),
    }


def parse_date_from_headers(headers: str):
    if not headers:
        return None
    for line in headers.split('\n'):
        if line.lower().startswith('date:'):
            try:
                return parsedate_to_datetime(line[5:].strip())
            except Exception:
                pass
    return None


# ============================================================
# Extractor: Financial Food
# Estructura habitual (tanto en .msg como en .eml normalizado):
#   PUBLICIDAD  (opcional)
#   Titular
#   Caption-de-imagen <URL>  (opcional, < ~100 chars con URL embebida)
#   Descripción larga
#   Leer más <URL>            ← este URL es el del artículo
#   ...siguiente noticia...
#
# Estrategia: buscar líneas "Leer más <URL>" como marcadores y mirar
# hacia atrás hasta el anterior "Leer más" o "PUBLICIDAD".
# ============================================================
URL_BARE_RE = re.compile(r'^https?://\S+$')
READMORE_RE = re.compile(r'^Leer m[áa]s\s*\x00URL(\d+)\x00\s*$', re.IGNORECASE)
HEADER_PHRASES = [
    'boletín para los profesionales',
    'si no visualiza correctamente',
    'haga click aquí',
    'es un mail automático',
    'darse de baja',
    'mailpoet',
    'política de privacidad',
    'has recibido este mail',
    'gestiona las newsletter',
    'newsletter',
    'noticias destacadas',
    'todas las noticias',
]


def _is_junk_line(line: str) -> bool:
    """Líneas que se ignoran completamente al buscar contenido."""
    stripped = line.strip()
    if not stripped:
        return True
    if URL_BARE_RE.match(stripped):
        return True
    if re.fullmatch(r'(\x00URL\d+\x00\s*)+', stripped):
        return True
    clean = re.sub(r'\x00URL\d+\x00', '', stripped).strip()
    if len(clean) < 5:
        return True
    # Cabeceras/footers conocidos
    lower = clean.lower()
    if any(h in lower for h in HEADER_PHRASES) and len(clean) < 120:
        return True
    # Solo iconos de redes
    if re.fullmatch(r'(facebook|twitter|youtube|linkedin|instagram)(\s+(facebook|twitter|youtube|linkedin|instagram))*', lower):
        return True
    return False


def extract_financialfood(text: str) -> list:
    """Extrae noticias de Financial Food."""
    urls = []
    def replace_url(m):
        urls.append(unwrap_safelink(m.group(1)))
        return f'\x00URL{len(urls)-1}\x00'
    
    text2 = URL_OUTLOOK_RE.sub(replace_url, text)
    text2 = text2.replace('\t', ' ')
    text2 = re.sub(r' +', ' ', text2)
    lines = [l.strip() for l in text2.split('\n')]
    
    items = []
    seen_titles = set()
    
    for i, line in enumerate(lines):
        m = READMORE_RE.match(line)
        if not m:
            continue
        
        url = urls[int(m.group(1))]
        
        # Mirar hacia atrás, parando en PUBLICIDAD o "Leer más" anterior
        candidates = []
        j = i - 1
        while j >= 0:
            prev = lines[j]
            if not prev.strip():
                j -= 1
                continue
            if READMORE_RE.match(prev) or prev.strip() == 'PUBLICIDAD':
                break
            if _is_junk_line(prev):
                j -= 1
                continue
            candidates.append(prev)
            j -= 1
        
        candidates.reverse()
        if not candidates:
            continue
        
        # Separar título de descripción
        # Captions de imagen: tienen URL embebida AL FINAL (después del texto, "...título. Fuente: X. <URL>")
        # Los captions suelen ser título o resumen + URL del thumbnail
        title = None
        description_parts = []
        
        for content in candidates:
            clean = re.sub(r'\x00URL\d+\x00', '', content).strip()
            clean = re.sub(r' +', ' ', clean)
            
            if len(clean) < 15:
                continue
            
            has_url = '\x00URL' in content
            # Captions terminan con URL embebida (formato "texto <URL>" o "texto. Fuente: X. <URL>")
            # Es decir: la línea termina con el marcador de URL (o casi)
            ends_with_url = bool(re.search(r'\x00URL\d+\x00\s*$', content.strip()))
            
            # Si tiene URL embebida Y es corta → caption corto (skip)
            if has_url and len(clean) < 100:
                continue
            # Si la línea ACABA con URL → es caption de imagen (skip)
            if ends_with_url:
                continue
            
            if title is None:
                title = clean
            else:
                description_parts.append(clean)
        
        if title and title not in seen_titles:
            seen_titles.add(title)
            items.append({
                'title': title,
                'summary': ' '.join(description_parts),
                'url': url,
            })
    
    return items


# ============================================================
# Extractor: Alimarket FoodTech
# ============================================================
def extract_alimarket_foodtech(text: str) -> list:
    urls = []
    def replace_url(m):
        urls.append(unwrap_safelink(m.group(1)))
        return f'\x00URL{len(urls)-1}\x00'
    
    text2 = URL_OUTLOOK_RE.sub(replace_url, text)
    text2 = text2.replace('\t', ' ')
    text2 = re.sub(r' +', ' ', text2)
    lines = [l.strip() for l in text2.split('\n')]
    
    items = []
    seen_titles = set()
    in_news = False
    
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
        
        if 'esta semana destacamos' in lower or 'destacamos' in lower or 'noticias' in lower:
            in_news = True
            i += 1
            continue
        
        if any(m in lower for m in stop_markers):
            break
        
        if not in_news:
            i += 1
            continue
        
        clean = re.sub(r'\x00URL\d+\x00', '', line).strip()
        clean = re.sub(r'_{5,}', '', clean).strip()
        
        if len(clean) < 25:
            i += 1
            continue
        
        if any(skip in lower for skip in [
            'sigue leyendo', 'leer más', 'ver en el navegador',
            'añadir', 'libreta de direcciones', 'mailto:',
            'foodtech', 'newsletter',
        ]) and len(clean) < 60:
            i += 1
            continue
        
        url = None
        for k in range(max(0, i-2), i):
            m = re.search(r'\x00URL(\d+)\x00', lines[k])
            if m:
                cand = urls[int(m.group(1))]
                if 'alimarket' in cand or 'acemlnc' in cand:
                    url = cand
                    break
        
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
# Extractor: Alimarket general
# ============================================================
def extract_alimarket(text: str) -> list:
    urls = []
    def replace_url(m):
        urls.append(unwrap_safelink(m.group(1)))
        return f'\x00URL{len(urls)-1}\x00'
    
    text2 = URL_OUTLOOK_RE.sub(replace_url, text)
    text2 = text2.replace('\t', ' ')
    text2 = re.sub(r' +', ' ', text2)
    lines = [l.strip() for l in text2.split('\n')]
    
    items = []
    seen_titles = set()
    in_news_section = False
    
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
        
        clean = re.sub(r'\x00URL\d+\x00', '', line).strip()
        if len(clean) < 25:
            continue
        
        m = re.search(r'\x00URL(\d+)\x00', line)
        url = None
        if m:
            url = urls[int(m.group(1))]
        else:
            if i > 0:
                m2 = re.search(r'\x00URL(\d+)\x00', lines[i-1])
                if m2:
                    url = urls[int(m2.group(1))]
        
        if url and ('alimarket' in url or 'acemlnc' in url):
            if clean not in seen_titles:
                seen_titles.add(clean)
                items.append({
                    'title': clean,
                    'summary': '',
                    'url': url,
                })
    
    return items


# ============================================================
# Extractor HTML: Alimarket .eml (Gmail)
# ============================================================
# Alimarket envía emails SOLO en HTML (sin text/plain).
# Los titulares son enlaces <a> con texto descriptivo apuntando a alimarket.acemlnc.com
# o alimarket.com. Es muy fiable extraer directamente del HTML.

ALIMARKET_HTML_SKIP_PATTERNS = [
    'ver en el navegador', 'ver más noticias', 'ver más informes',
    'mailto:', 'newsletter@', 'cliente@alimarket',
    'buscar establecimientos', 'buscar marcas',
    'mdd alimarket', 'alimarket research',
    'darse de baja', 'dejar de recibir',
    'aviso legal', 'política de privacidad', 'política de cookies',
    'has recibido este mail', 'gestiona las newsletter',
    'cuestión de confianza', 'quiénes somos', 'quienes somos',
    'informe 2024', 'informe 2025', 'informe 2026',
    'informe sobre', 'análisis 2024', 'análisis 2025', 'análisis 2026',
    'termómetro gran consumo',
    'redes sociales', 'publicidad en alimarket',
    'servicios y suscripciones',
    'valentín beato', 'valentin beato',  # dirección física del footer
    'c/ valent',
    '28037 madrid',
]


def extract_alimarket_html(html: str) -> list:
    """Extrae noticias del HTML de un email de Alimarket."""
    if not html or not HAS_BS4:
        return []
    
    soup = BeautifulSoup(html, 'html.parser')
    for tag in soup(['style', 'script']):
        tag.decompose()
    
    items = []
    seen = set()
    
    for a in soup.find_all('a', href=True):
        href = a['href']
        text = a.get_text(separator=' ', strip=True)
        text = re.sub(r'\s+', ' ', text)
        
        if not text or len(text) < 20:
            continue
        
        # Solo enlaces de Alimarket
        if 'alimarket' not in href and 'acemlnc' not in href:
            continue
        
        lower = text.lower()
        if any(s in lower for s in ALIMARKET_HTML_SKIP_PATTERNS):
            continue
        
        # Skip cabeceras tipo "Newsletter Alimentación", "Boletín..."
        if text.startswith('Newsletter') or text.startswith('Boletín'):
            continue
        
        # Skip direcciones/datos de contacto
        if re.match(r'^[A-ZÁÉÍÓÚÑ/\s]+\d{4,5}', text):  # tipo "C/ XYZ 28037"
            continue
        
        if text in seen:
            continue
        seen.add(text)
        
        items.append({
            'title': text,
            'summary': '',  # Alimarket no incluye adelanto en el HTML del email
            'url': href,
        })
    
    return items


# ============================================================
# Extractor principal: detecta formato y enruta
# ============================================================
def _subject_to_source(subject: str) -> str:
    """Mapea el asunto a una fuente legible."""
    s = (subject or '').lower()
    if 'foodtech' in s:
        return 'Alimarket FoodTech'
    if 'non food' in s or 'nonfood' in s:
        return 'Alimarket Non Food'
    if 'envase' in s or 'packaging' in s:
        return 'Alimarket Envase'
    if 'horeca' in s or 'foodservice' in s:
        return 'Alimarket Horeca'
    return 'Alimarket'


def extract_from_msg(path: str) -> dict:
    """Extrae todas las noticias de un único correo (.msg o .eml)."""
    is_eml = path.lower().endswith('.eml')
    if is_eml:
        msg = parse_eml_file(path)
    else:
        msg = parse_msg(path)
    
    sender = (msg.get('sender_smtp') or msg.get('sender_email') or '').lower()
    subject = msg.get('subject') or ''
    
    date = parse_date_from_headers(msg.get('headers', ''))
    if not date:
        m = re.search(r'(\d{1,2})[/_](\d{1,2})[/_](\d{2,4})', subject)
        if m:
            try:
                d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
                if y < 100:
                    y += 2000
                date = datetime(y, mo, d)
            except Exception:
                date = None
    
    text = msg.get('body_plain') or ''
    html = msg.get('body_html') or ''
    
    if 'alimarket' in sender:
        source = _subject_to_source(subject)
        if is_eml:
            # En .eml de Gmail, Alimarket viene solo en HTML
            items = extract_alimarket_html(html)
        else:
            # En .msg, usar el extractor de texto plano
            if 'foodtech' in subject.lower():
                items = extract_alimarket_foodtech(text)
            else:
                items = extract_alimarket(text)
    elif 'financialfood' in sender:
        source = 'Financial Food'
        items = extract_financialfood(text)
    else:
        # Reenviados u origen desconocido
        if 'alimarket' in text.lower() or 'alimarket' in html.lower():
            source = 'Alimarket (reenviado)'
            items = extract_alimarket_html(html) if is_eml else extract_alimarket(text)
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
        'subject': subject,
        'items': items,
    }
