"""
Clasifica noticias añadiendo sectores y empresas detectadas.
Usa listas curadas + reglas de coincidencia (insensible a mayúsculas, palabra completa).
"""
import json
import re
from collections import Counter


# ============================================================
# EMPRESAS (con variantes/aliases)
# La clave es el nombre canónico que se mostrará. Los valores
# son las variantes que hay que buscar en el texto.
# ============================================================
EMPRESAS = {
    # Distribución / retail
    'Mercadona': ['Mercadona'],
    'Carrefour': ['Carrefour'],
    'Lidl': ['Lidl'],
    'Aldi': ['Aldi'],
    'Eroski': ['Eroski', 'Caprabo'],
    'Día': ['Dia ', 'Día ', ' Dia.', ' Día.', 'DIA '],  # ojo "dia" minúscula
    'Alcampo': ['Alcampo', 'Auchan'],
    'Consum': ['Consum'],
    'Costco': ['Costco'],
    'El Corte Inglés': ['El Corte Inglés', 'Corte Inglés', 'Hipercor', 'Supercor'],
    'Hiperdino': ['HiperDino', 'Hiperdino'],
    'Alimerka': ['Alimerka'],
    'Covirán': ['Covirán', 'Coviran'],
    'Ahorramas': ['Ahorramas', 'Ahorra Más'],
    'BM Supermercados': ['BM Supermercados', 'Uvesco'],
    'Spar': ['Spar '],
    'Bonpreu': ['Bon Preu', 'Bonpreu', 'Esclat'],
    'Gadisa': ['Gadisa', 'Gadis'],
    'Froiz': ['Froiz'],
    'Masymas': ['Masymas', 'Mas y Mas'],
    'Vegalsa': ['Vegalsa'],
    'Grupo MAS': ['Grupo MAS', 'Cash Fresh'],
    'Transgourmet': ['Transgourmet'],
    'Makro': ['Makro'],
    'Cash & Carry': ['Cash & Carry', 'Cash and Carry'],

    # Multinacionales CPG/F&B
    'Nestlé': ['Nestlé', 'Nestle'],
    'Danone': ['Danone'],
    'Unilever': ['Unilever'],
    'Coca-Cola': ['Coca-Cola', 'Coca Cola', 'CocaCola'],
    'PepsiCo': ['PepsiCo', 'Pepsi'],
    'Mondelez': ['Mondelez', 'Mondelēz'],
    'Heineken': ['Heineken'],
    'AB InBev': ['AB InBev', 'Anheuser', 'Budweiser'],
    'Diageo': ['Diageo'],
    'Pernod Ricard': ['Pernod Ricard', 'Pernod-Ricard'],
    'Kraft Heinz': ['Kraft Heinz'],
    'Mars': ['Mars '],
    'Ferrero': ['Ferrero'],
    'Kellogg': ['Kellogg', "Kellogg's", 'Kellanova'],
    'General Mills': ['General Mills'],
    'P&G': ['P&G', 'Procter & Gamble', 'Procter and Gamble'],
    'Henkel': ['Henkel'],
    'Reckitt': ['Reckitt'],
    'Colgate': ['Colgate-Palmolive', 'Colgate'],
    'L\'Oréal': ["L'Oréal", 'L´Oréal', 'LOreal'],

    # Españolas grandes F&B
    'Mahou San Miguel': ['Mahou San Miguel', 'Mahou', 'San Miguel'],
    'Damm': ['Damm', 'Estrella Damm'],
    'Hijos de Rivera': ['Hijos de Rivera', 'Estrella Galicia'],
    'Capsa Food': ['Capsa Food', 'Capsa', 'Central Lechera'],
    'Pascual': ['Pascual'],
    'García Carrión': ['García Carrión', 'Don Simón'],
    'Calidad Pascual': ['Calidad Pascual'],
    'Lactalis': ['Lactalis', 'Puleva'],
    'Reny Picot': ['Reny Picot'],
    'El Pozo': ['El Pozo', 'ElPozo'],
    'Campofrío': ['Campofrío', 'Sigma'],
    'Argal': ['Argal'],
    'Noel': ['Noel '],
    'Espuña': ['Espuña'],
    'Casademont': ['Casademont'],
    'Grupo Vall Companys': ['Vall Companys'],
    'Grupo Costa': ['Grupo Costa'],
    'Coren': ['Coren'],
    'Incarlopsa': ['Incarlopsa'],
    'Cárnicas Serrano': ['Cárnicas Serrano'],
    'Pescanova': ['Pescanova'],
    'Calvo': ['Grupo Calvo', 'Conservas Calvo'],
    'Jealsa': ['Jealsa'],
    'Conservas Garavilla': ['Garavilla', 'Isabel'],
    'Frinsa': ['Frinsa'],
    'Bimbo': ['Bimbo'],
    'Panrico': ['Panrico'],
    'Adam Foods': ['Adam Foods', 'Cuétara'],
    'Gullón': ['Gullón'],
    'Bicentury': ['Bicentury'],
    'Borges': ['Borges'],
    'Deoleo': ['Deoleo', 'Carbonell', 'Koipe'],
    'Grupo Dcoop': ['Dcoop'],
    'Acesur': ['Acesur'],
    'Migasa': ['Migasa'],
    'Ebro Foods': ['Ebro Foods', 'SOS', 'Brillante'],
    'Helados Estiu': ['Estiu'],
    'Frigo': ['Frigo'],
    'Helados Alacant': ['Helados Alacant'],
    'Florette': ['Florette'],
    'Vega Mayor': ['Vega Mayor'],
    'Verdifresh': ['Verdifresh'],
    'Primaflor': ['Primaflor'],
    'Bonduelle': ['Bonduelle'],
    'Bollo Natural Fruit': ['Bollo Natural Fruit'],
    'Ametller Origen': ['Ametller Origen'],
    'Le Duff': ['Le Duff', 'Bridor', 'Panamar'],
    'Granini': ['Granini', 'Don Simón'],
    'AMC Innova': ['AMC Innova', 'AMC Group'],
    'Hero': ['Hero España', 'Hero '],
    'Schweppes': ['Schweppes'],
    'Red Bull': ['Red Bull'],
    'Monster': ['Monster Energy', 'Monster Beverage'],
    'Codorníu': ['Codorníu', 'Codorniu'],
    'Freixenet': ['Freixenet'],
    'González Byass': ['González Byass', 'Tío Pepe'],
    'Bodegas Torres': ['Bodegas Torres', 'Familia Torres'],
    'Vicente Gandía': ['Vicente Gandía'],
    'Pernod Ricard España': ['Pernod Ricard'],
    'Osborne': ['Osborne'],

    # Foodtech / startups
    'Heura': ['Heura'],
    'Foods for Tomorrow': ['Foods for Tomorrow'],
    'Beyond Meat': ['Beyond Meat'],
    'Impossible Foods': ['Impossible Foods'],
    'Pink Albatross': ['Pink Albatross'],
    'Cocuus': ['Cocuus'],
    'Imperia': ['Imperia '],
    'IKOS': ['IKOS'],
    'Grodi': ['Grodi'],

    # Otras
    'Ecoembes': ['Ecoembes'],
    'Gerblé': ['Gerblé'],
    'Schär': ['Schär', 'Schar'],
    'Idilia Foods': ['Idilia Foods', 'ColaCao', 'Cola Cao'],
    'Schweppes Suntory': ['Suntory'],
    'KFC': ['KFC'],
    'McDonald\'s': ["McDonald's", 'McDonalds'],
    'Burger King': ['Burger King'],
    'Telepizza': ['Telepizza'],
    'Domino\'s': ["Domino's"],
    'Starbucks': ['Starbucks'],
    'Glovo': ['Glovo'],
    'Just Eat': ['Just Eat'],
    'Uber Eats': ['Uber Eats'],
    'FIAB': ['FIAB'],
    'AECOC': ['AECOC'],
    'ASEDAS': ['ASEDAS'],
    'ANGED': ['ANGED'],
    'ACES': ['ACES '],
    'Promarca': ['Promarca'],
    'Mercasa': ['Mercasa'],
    'Mercabarna': ['Mercabarna'],
    'Mercamadrid': ['Mercamadrid'],
}


# ============================================================
# SECTORES (palabras clave que indican el sector de la noticia)
# ============================================================
SECTORES = {
    'Bebidas alcohólicas': [
        'cerveza', 'cervecera', 'cervezas', 'vino ', 'vinos', 'bodega', 'bodegas',
        'destilería', 'whisky', 'ginebra', 'vodka', 'ron', 'licor', 'licores',
        'cava', 'champán', 'champagne', 'spirits', 'sidra',
    ],
    'Bebidas no alcohólicas': [
        'refresco', 'refrescos', 'agua mineral', 'aguas envasadas', 'zumo', 'zumos',
        'energy drink', 'bebida energética', 'bebida funcional',
    ],
    'Café y té': ['café ', 'cafés', 'cafetería', 'cafeterías', 'té ', 'infusión', 'infusiones'],
    'Lácteos': [
        'lácteo', 'lácteos', 'leche', 'yogur', 'yogures', 'queso', 'quesos',
        'mantequilla', 'nata', 'kéfir', 'mascarpone',
    ],
    'Cárnicos': [
        'cárnico', 'cárnicos', 'cárnica', 'embutido', 'embutidos', 'jamón', 'chorizo',
        'salchichón', 'matadero', 'mataderos', 'carne ', 'carnes', 'porcino', 'avícola',
        'pollo', 'pavo', 'vacuno', 'ternera', 'cordero',
    ],
    'Pescado y marisco': [
        'pescado', 'pescados', 'marisco', 'mariscos', 'atún', 'merluza', 'salmón',
        'pesquera', 'pesquero', 'conservas de pescado', 'acuicultura',
    ],
    'Snacks y aperitivos': [
        'snack', 'snacks', 'aperitivo', 'aperitivos', 'patatas fritas', 'frutos secos',
        'chips', 'galleta', 'galletas',
    ],
    'Confitería y chocolate': [
        'chocolate', 'chocolates', 'cacao', 'caramelo', 'caramelos', 'chuchería',
        'chucherías', 'bombón', 'bombones', 'turrón', 'turrones',
    ],
    'Panadería y bollería': [
        'panadería', 'panaderías', 'bollería', 'pan ', 'pastel', 'pasteles',
        'pastelería', 'bollo ', 'bollos', 'masa ',
    ],
    'Congelados': ['congelado', 'congelados', 'congelación', 'ultracongelado'],
    'Frutas y verduras': [
        'fruta', 'frutas', 'hortaliza', 'hortalizas', 'verdura', 'verduras',
        'fresh-cut', 'cuarta gama', 'iv gama', 'ensalada', 'ensaladas',
        'tomate', 'aguacate', 'naranja',
    ],
    'Aceites y grasas': [
        'aceite de oliva', 'aceite ', 'aceites', 'oliva', 'olivar', 'aov', 'aove',
        'grasa', 'grasas',
    ],
    'Plant-based': [
        'plant-based', 'plant based', 'vegano', 'vegana', 'veganos', 'veganas',
        'vegetariano', 'vegetariana', 'sustituto cárnico', 'proteína vegetal',
        'proteínas vegetales', 'carne vegetal',
    ],
    'Salud y bienestar': [
        'salud', 'saludable', 'saludables', 'bienestar', 'nutrición', 'nutricional',
        'funcional', 'sin gluten', 'sin azúcar', 'sin lactosa', 'bio ', 'orgánico',
        'orgánica', 'eco ', 'ecológico', 'ecológica', 'ecológicos', 'ecológicas',
        'reducido en', 'bajo en', 'alto en proteína',
    ],
    'Distribución / Retail': [
        'supermercado', 'supermercados', 'hipermercado', 'hipermercados',
        'cadena de supermercados', 'distribución alimentaria',
        'gran consumo', 'cash&carry', 'cash & carry', 'discount',
        'marca de distribuidor', 'marca blanca', 'marca propia', 'mdd',
    ],
    'Foodservice / Horeca': [
        'horeca', 'restauración', 'restaurante', 'restaurantes', 'cafetería',
        'cafeterías', 'foodservice', 'food service', 'hostelería', 'colectividades',
        'catering',
    ],
    'M&A / Inversión': [
        ' compra ', ' compran ', 'adquisición', 'adquisiciones', 'adquiere',
        'fusión', 'opa ', ' fondo ', 'capital riesgo', 'private equity', 'ronda de',
        'capital privado', 'inversores', 'levantar capital', 'capta ', 'captación',
        'desinversión', 'venta de',
    ],
    'Resultados financieros': [
        'facturación', 'facturó', 'facturará', 'beneficios', 'ebitda', 'ingresos',
        'ventas crecieron', 'ventas alcanzan', 'cifra de negocio', 'resultados',
        'cuentas anuales', 'plan estratégico', 'previsión', 'previsiones',
    ],
    'Marketing y campañas': [
        'campaña', 'campañas', 'lanza una campaña', 'publicidad', 'patrocin',
        'embajador', 'embajadora', 'comunicación', 'spot ',
    ],
    'Lanzamiento de producto': [
        'lanza ', 'lanzamiento', 'nueva gama', 'nueva línea', 'nuevo producto',
        'estrena ', 'presenta ', 'presentación de',
    ],
    'Innovación / I+D': [
        'innovación', 'innovador', 'innovadora', 'i+d', 'i+d+i', 'investigación',
        'desarrollo de producto', 'foodtech', 'agtech',
    ],
    'Sostenibilidad': [
        'sostenibilidad', 'sostenible', 'sostenibles', 'circular', 'reciclaje',
        'reciclado', 'reciclables', 'huella de carbono', 'emisiones', 'co2',
        'envase sostenible', 'packaging sostenible', 'ods ',
    ],
    'Internacionalización': [
        'exportación', 'exportaciones', 'exporta', 'mercados internacionales',
        'expansión internacional', 'desembarca en', 'aterriza en',
    ],
    'Regulación / Política': [
        'ministerio', 'normativa', 'regulación', 'regulaciones', 'ley ', 'decreto',
        'reglamento', 'sanción', 'sanciones', 'arancel', 'aranceles', 'pac ',
        'subvención', 'subvenciones', 'comisión europea', 'parlamento',
    ],
    'Logística': [
        'logística', 'logístico', 'almacén', 'almacenes', 'centro de distribución',
        'cadena de suministro', 'última milla', 'flota ',
    ],
    'Tecnología / Digital': [
        'inteligencia artificial', ' ia ', 'big data', 'digitalización', 'digital',
        'software', 'plataforma digital', 'app ', 'aplicación móvil', 'ecommerce',
        'e-commerce', 'comercio electrónico',
    ],
    'Recursos humanos': [
        'fichaje', 'nombramiento', 'consejero delegado', 'plantilla',
        'nuevos empleos', 'contrataciones', 'despidos', 'expediente de regulación',
        'nombrado director', 'nombrada directora', 'nombrada nueva',
        'asume el cargo', 'releva en', 'sustituye en el cargo',
    ],
    'Apertura / Inauguración': [
        'inaugur', 'nueva tienda', 'abre sus puertas', 'pone en marcha',
        'abre nuevo', 'estrena tienda', 'estrena nuevo', 'estrena local',
    ],
    'Cierre / Crisis': [
        'concurso de acreedores', 'preconcurso', 'liquidación', 'cierre de la fábrica',
        'cierre de planta', 'cierra su fábrica', 'cierra su planta', 'quiebra',
        'suspensión de pagos', 'expediente de regulación de empleo',
    ],
}


# ============================================================
# Función de detección
# ============================================================
def find_companies(text: str) -> list:
    """Devuelve lista de empresas detectadas en el texto."""
    found = []
    for canonical, variants in EMPRESAS.items():
        for variant in variants:
            # Búsqueda case-insensitive con palabra completa cuando aplica
            # Si la variante tiene espacio al inicio/final lo respetamos
            if variant.startswith(' ') or variant.endswith(' '):
                # Buscar con espacios literales
                if variant.lower() in text.lower():
                    found.append(canonical)
                    break
            else:
                # Búsqueda con límites de palabra (más estricta)
                pattern = r'(?<![A-Za-zÁÉÍÓÚÑáéíóúñ])' + re.escape(variant) + r'(?![A-Za-zÁÉÍÓÚÑáéíóúñ])'
                if re.search(pattern, text, re.IGNORECASE):
                    found.append(canonical)
                    break
    return sorted(set(found))


def find_sectors(text: str) -> list:
    """Devuelve lista de sectores detectados en el texto."""
    text_lower = text.lower()
    found = []
    for sector, keywords in SECTORES.items():
        for kw in keywords:
            if kw.lower() in text_lower:
                found.append(sector)
                break
    return sorted(set(found))


def classify_news(items: list) -> list:
    """Añade campos 'sectors' y 'companies' a cada noticia."""
    for n in items:
        text = (n.get('title') or '') + ' ' + (n.get('summary') or '')
        n['companies'] = find_companies(text)
        n['sectors'] = find_sectors(text)
    return items


if __name__ == '__main__':
    with open('noticias.json', 'r', encoding='utf-8') as f:
        items = json.load(f)
    
    items = classify_news(items)
    
    # Estadísticas
    company_counts = Counter()
    sector_counts = Counter()
    no_company = 0
    no_sector = 0
    for n in items:
        if not n['companies']:
            no_company += 1
        if not n['sectors']:
            no_sector += 1
        for c in n['companies']:
            company_counts[c] += 1
        for s in n['sectors']:
            sector_counts[s] += 1
    
    print(f'Total noticias: {len(items)}')
    print(f'Sin empresa detectada: {no_company} ({100*no_company//len(items)}%)')
    print(f'Sin sector detectado: {no_sector} ({100*no_sector//len(items)}%)')
    print()
    print('Top 25 empresas:')
    for c, n in company_counts.most_common(25):
        print(f'  {n:5d}  {c}')
    print()
    print('Sectores:')
    for s, n in sector_counts.most_common():
        print(f'  {n:5d}  {s}')
    
    # Guardar
    with open('noticias-clasificadas.json', 'w', encoding='utf-8') as f:
        json.dump(items, f, ensure_ascii=False, separators=(',', ':'))
