# Cómo actualizar el Boletín F&B con nuevos correos

## Antes de empezar (una sola vez)

### 1. Crea una regla en Outlook
- Inicio → Reglas → Crear regla.
- Cuando llegue un correo de:
  - `newsletter@alimarket.es`
  - `boletin@financialfood.es`
- → Mover a una nueva carpeta llamada **`pendientes-boletin`**.

A partir de ahora todos los correos relevantes se acumulan ahí solos.

### 2. Guarda este paquete
Esta carpeta contiene todo lo necesario para futuras actualizaciones:
- `template.html` — la plantilla de la web (vacía de datos)
- `noticias.json` — los datos actuales (7.223 noticias)
- `msg_parser.py`, `extract_news.py`, `classify.py`, `rebuild.py` — los scripts
- `COMO-ACTUALIZAR.md` — este archivo

**Súbelos a Google Drive, OneDrive o Dropbox** para no perderlos.

---

## Cuando quieras actualizar

### Paso 1 — Exportar correos nuevos desde Outlook
1. Abre `pendientes-boletin` en Outlook escritorio.
2. Crea una carpeta vacía en el escritorio: `nuevos-correos`.
3. Selecciona todos los correos (Ctrl+A) y arrástralos a la carpeta.
4. Comprime esa carpeta en ZIP.

### Paso 2 — Pásamelos en una conversación nueva con Claude
Abre una conversación nueva conmigo y envía:

1. **El ZIP** con los `.msg` nuevos
2. **Estos archivos del paquete**:
   - `noticias.json` (los datos actuales)
   - `template.html`
   - `msg_parser.py`, `extract_news.py`, `classify.py`, `rebuild.py`
3. **Este mensaje copiado tal cual:**

> Tengo el paquete del Boletín F&B y unos correos nuevos para añadir.
>
> Adjunto:
> - ZIP con los `.msg` nuevos
> - `noticias.json` (datos existentes)
> - `template.html`
> - Los 4 scripts Python
>
> Por favor:
> 1. Descomprime el ZIP en una carpeta
> 2. Ejecuta `rebuild.py` con `--new-emails` apuntando a esa carpeta, `--existing noticias.json`, `--template template.html`, `--out boletin-fb.html`
> 3. Devuélveme el `boletin-fb.html` resultante y el `noticias.json` actualizado

Yo (o el Claude del futuro) ejecutaré el script y te devolveré:
- El **HTML actualizado** para subir a Netlify
- El **JSON actualizado** para guardar en tu paquete (sustituye el viejo)

### Paso 3 — Subir a Netlify
1. Panel de Netlify → tu sitio → pestaña **Deploys**.
2. Arrastra `boletin-fb.html` a la zona "Drag and drop" (renómbralo a `index.html` si Netlify lo pide).
3. En segundos la web está actualizada.

### Paso 4 — Limpiar Outlook
Solo después de confirmar que la web tiene las noticias nuevas:
- Mueve los correos de `pendientes-boletin` a otra carpeta (ej. `procesados`).
- Así la próxima vez la carpeta `pendientes-boletin` solo tiene los correos NUEVOS sin procesar.

### Paso 5 — Guardar el JSON nuevo
Sustituye en tu Drive/OneDrive el `noticias.json` antiguo por el nuevo que te devuelvo. Es importante: la siguiente actualización parte de él.

---

## Notas importantes

- **Cada conversación conmigo empieza desde cero.** No recuerdo nada de las conversaciones anteriores. Por eso necesitas pasarme el JSON y los scripts cada vez.
- **Frecuencia recomendada**: semanal. Si esperas más de 3-4 semanas el ZIP puede pesar mucho.
- **Si dudas de algo**: pregúntame antes de subir el HTML a Netlify. Mejor quedarte con la versión vieja que romper la actual.
- **Nuevas empresas o sectores**: si quieres que detecte una empresa nueva (por ejemplo "Carbónica X" que no está en mi lista), dímelo y te edito `classify.py` añadiéndola.

---

## Resumen visual

```
Outlook (regla automática)
    ↓
Carpeta "pendientes-boletin" (acumula sola)
    ↓
[Cada semana, manual]
Arrastrar a carpeta + ZIP
    ↓
Conversación nueva con Claude
   (paso ZIP + paquete completo)
    ↓
Recibir HTML actualizado + JSON nuevo
    ↓
Subir HTML a Netlify · Guardar JSON nuevo · Limpiar Outlook
```

**Tiempo total cada semana: ~5 minutos.**
