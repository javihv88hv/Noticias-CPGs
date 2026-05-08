"""
Extractor de noticias de las dos newsletters: Alimarket y Financial Food.
Soporta archivos .msg (Outlook) y .eml (estándar email) de forma transparente.
"""
import os
import re
import sys
import email
from email import policy
from datetime import datetime
from urllib.parse import unquote, parse_qs, urlparse
from email.utils import parsedate_to_datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from msg_parser import parse_msg


SAFELINK_RE = re.compile(r'<(https?://[^>]+)>')


def unwrap_safelink(url: str) -> str:
    if 'safelinks.protection.outlook.com' in url:
        try:
            qs = parse_qs(urlparse(url).query)
            if 'url' in qs:
                return unquote(qs['url'][0])
        except Exception:
            pass
    return url


def parse_eml_file(path: str) -> dict:
    """Parsea un archivo .eml (formato estándar). Devuelve estructura compatible con parse_msg."""
    with open(path, 'rb') as f:
        msg = email.message_from_binary_file(f, policy=policy.default)
    
    subject = msg.get('subject', '')
    from_field = msg.get('from', '')
    
    # Extraer email del campo From
    sender_email = ''
    sender_name = ''
    m = re.match(r'(.*?)<(.+?)>', from_field)
    if m:
        sender_name = m.group(1).strip().strip('"')
        sender_email = m.group(2).strip()
    else:
        sender_email = from_field.strip()
    
    # Extraer cuerpo en texto plano
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
        # Convertir links a formato <url> tipo plain text
        text = re.sub(r'<a [^>]*href="([^"]+)"[^>]*>(.*?)</a>',
                      lambda m: f'{re.sub(r"<[^>]+>", "", m.group(2))} <{m.group(1)}>',
                      text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<br[^>]*>', '\n', text, flags=re.IGNORECASE)
        text = re.sub(r'</p>', '\n\n', text, flags=re.IGNORECASE)
        text = re.sub(r'<[^>]+>', '', text)
        # Decodificar entidades HTML básicas
        import html as html_mod
        text = html_mod.unescape(text)
        body_plain = text
    
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
# ============================================================
def extract_financialfood(text: str) -> list:
    urls = []
    def replace_url(m):
        urls.append(unwrap_safelink(m.group(1)))
        return f'\x00URL{len(urls)-1}\x00'
    
    text2 = SAFELINK_RE.sub(replace_url, text)
    text2 = text2.replace('\t', ' ')
    text2 = re.sub(r' +', ' ', text2)
    lines = [l.strip() for l in text2.split('\n')]
    
    items = []
    i = 0
    seen_titles = set()
    while i < len(lines):
        line = lines[i]
        if (not line
            or re.fullmatch(r'(\x00URL\d+\x00\s*)+', line)
            or 'PUBLICIDAD' in line
            or line.lower().startswith('leer más')
            or line.lower().startswith('si no visualiza')
            or line.lower().startswith('publicidad')
            or 'mailpoet_router' in line.lower()):
            i += 1
            continue
        
        if len(line) > 25 and 'mailto:' not in line and not line.startswith('Boletín'):
            if '\x00URL' in line:
                clean = re.sub(r'\x00URL\d+\x00', '', line).strip()
                if len(clean) < 25:
                    i += 1
                    continue
                line = clean
            
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
            
            url = None
            description = None
            j = i + 1
            scan_limit = min(i + 12, len(lines))
            while j < scan_limit:
                ln = lines[j].strip()
                if not ln:
                    j += 1
                    continue
                if 'leer más' in ln.lower():
                    m = re.search(r'\x00URL(\d+)\x00', ln)
                    if m:
                        url = urls[int(m.group(1))]
                    j += 1
                    break
                clean_ln = re.sub(r'\x00URL\d+\x00', '', ln).strip()
                if (clean_ln and len(clean_ln) > 30
                    and 'PUBLICIDAD' not in clean_ln
                    and 'mailto:' not in clean_ln):
                    if description is None:
                        description = clean_ln
                    else:
                        description += ' ' + clean_ln
                j += 1
            
            if not url:
                for k in range(i + 1, min(i + 5, len(lines))):
                    m = re.search(r'\x00URL(\d+)\x00', lines[k])
                    if m:
                        candidate = urls[int(m.group(1))]
                        if 'mailpoet_router' in candidate or 'financialfood.es' in candidate:
                            url = candidate
                            break
            
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
def extract_alimarket_foodtech(text: str) -> list:
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
    
    text2 = SAFELINK_RE.sub(replace_url, text)
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
# Extractor principal: detecta formato y enruta
# ============================================================
def extract_from_msg(path: str) -> dict:
    """Extrae todas las noticias de un único correo (.msg o .eml)."""
    if path.lower().endswith('.eml'):
        msg = parse_eml_file(path)
    else:
        msg = parse_msg(path)
    
    sender = (msg.get('sender_smtp') or msg.get('sender_email') or '').lower()
    
    date = parse_date_from_headers(msg.get('headers', ''))
    if not date:
        subj = msg.get('subject') or ''
        m = re.search(r'(\d{1,2})[/_](\d{1,2})[/_](\d{2,4})', subj)
        if m:
            try:
                d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
                if y < 100:
                    y += 2000
                date = datetime(y, mo, d)
            except Exception:
                date = None
    
    text = msg.get('body_plain') or ''
    
    if 'alimarket' in sender:
        subj = (msg.get('subject') or '').lower()
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
        'subject': msg.get('subject'),
        'items': items,
    }
