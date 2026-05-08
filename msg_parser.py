"""
Parser minimalista de archivos .msg (formato CFB/OLE2 de Microsoft Outlook).
Implementa solo lo necesario para extraer cuerpo HTML, texto plano,
asunto, remitente y fecha.
"""
import struct
from typing import Optional


class CFBParser:
    """Parser de Compound File Binary Format (CFB / OLE2)."""

    SECTOR_SIZE = 512
    DIFAT_HEADER_COUNT = 109
    FREESECT = 0xFFFFFFFF
    ENDOFCHAIN = 0xFFFFFFFE
    FATSECT = 0xFFFFFFFD
    DIFSECT = 0xFFFFFFFC

    def __init__(self, path: str):
        with open(path, 'rb') as f:
            self.data = f.read()
        self._parse_header()
        self._build_fat()
        self._build_minifat()
        self._read_directory()

    def _parse_header(self):
        # Header structure
        sig = self.data[0:8]
        if sig != b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1':
            raise ValueError("No es un archivo CFB válido")
        self.sector_shift = struct.unpack('<H', self.data[30:32])[0]
        self.mini_sector_shift = struct.unpack('<H', self.data[32:34])[0]
        self.num_dir_sectors = struct.unpack('<I', self.data[40:44])[0]
        self.num_fat_sectors = struct.unpack('<I', self.data[44:48])[0]
        self.first_dir_sector = struct.unpack('<I', self.data[48:52])[0]
        self.mini_stream_cutoff = struct.unpack('<I', self.data[56:60])[0]
        self.first_minifat_sector = struct.unpack('<I', self.data[60:64])[0]
        self.num_minifat_sectors = struct.unpack('<I', self.data[64:68])[0]
        self.first_difat_sector = struct.unpack('<I', self.data[68:72])[0]
        self.num_difat_sectors = struct.unpack('<I', self.data[72:76])[0]

        self.sector_size = 1 << self.sector_shift  # 512 typically
        self.mini_sector_size = 1 << self.mini_sector_shift  # 64

        # First 109 DIFAT entries are in header
        self.difat = list(struct.unpack('<109I', self.data[76:512]))

        # Read additional DIFAT sectors if present
        next_sec = self.first_difat_sector
        while next_sec != self.ENDOFCHAIN and next_sec != self.FREESECT:
            offset = (next_sec + 1) * self.sector_size
            entries = struct.unpack('<127I', self.data[offset:offset + 508])
            self.difat.extend(entries)
            next_sec = struct.unpack('<I', self.data[offset + 508:offset + 512])[0]

    def _sector_offset(self, sector_id: int) -> int:
        return (sector_id + 1) * self.sector_size

    def _build_fat(self):
        self.fat = []
        for fat_sec in self.difat:
            if fat_sec == self.FREESECT:
                continue
            offset = self._sector_offset(fat_sec)
            entries_per_sector = self.sector_size // 4
            entries = struct.unpack(f'<{entries_per_sector}I',
                                    self.data[offset:offset + self.sector_size])
            self.fat.extend(entries)

    def _build_minifat(self):
        self.minifat = []
        sec = self.first_minifat_sector
        while sec != self.ENDOFCHAIN and sec != self.FREESECT:
            offset = self._sector_offset(sec)
            entries_per_sector = self.sector_size // 4
            entries = struct.unpack(f'<{entries_per_sector}I',
                                    self.data[offset:offset + self.sector_size])
            self.minifat.extend(entries)
            if sec >= len(self.fat):
                break
            sec = self.fat[sec]

    def _read_chain(self, start: int, fat: list) -> bytes:
        """Lee una cadena de sectores del FAT."""
        result = bytearray()
        sec = start
        visited = set()
        while sec != self.ENDOFCHAIN and sec != self.FREESECT:
            if sec in visited:  # Protección contra ciclos
                break
            visited.add(sec)
            offset = self._sector_offset(sec)
            result.extend(self.data[offset:offset + self.sector_size])
            if sec >= len(fat):
                break
            sec = fat[sec]
        return bytes(result)

    def _read_mini_chain(self, start: int, mini_stream: bytes) -> bytes:
        result = bytearray()
        sec = start
        visited = set()
        while sec != self.ENDOFCHAIN and sec != self.FREESECT:
            if sec in visited:
                break
            visited.add(sec)
            offset = sec * self.mini_sector_size
            result.extend(mini_stream[offset:offset + self.mini_sector_size])
            if sec >= len(self.minifat):
                break
            sec = self.minifat[sec]
        return bytes(result)

    def _read_directory(self):
        dir_data = self._read_chain(self.first_dir_sector, self.fat)
        self.entries = []
        for i in range(0, len(dir_data), 128):
            entry_data = dir_data[i:i + 128]
            if len(entry_data) < 128:
                break
            name_len = struct.unpack('<H', entry_data[64:66])[0]
            if name_len == 0:
                self.entries.append(None)
                continue
            name = entry_data[0:name_len - 2].decode('utf-16-le', errors='replace')
            obj_type = entry_data[66]
            start_sector = struct.unpack('<I', entry_data[116:120])[0]
            stream_size = struct.unpack('<Q', entry_data[120:128])[0]
            self.entries.append({
                'name': name,
                'type': obj_type,  # 1=storage, 2=stream, 5=root
                'start': start_sector,
                'size': stream_size,
            })

        # Mini stream is the data of the root entry
        root = self.entries[0]
        if root and root['size'] > 0:
            self.mini_stream = self._read_chain(root['start'], self.fat)[:root['size']]
        else:
            self.mini_stream = b''

    def read_stream(self, name: str) -> Optional[bytes]:
        for entry in self.entries:
            if entry and entry['name'] == name and entry['type'] == 2:
                if entry['size'] < self.mini_stream_cutoff:
                    data = self._read_mini_chain(entry['start'], self.mini_stream)
                else:
                    data = self._read_chain(entry['start'], self.fat)
                return data[:entry['size']]
        return None

    def list_streams(self) -> list:
        return [e['name'] for e in self.entries if e and e['type'] == 2]


# ============================================================
# Extracción de campos del MSG
# ============================================================
# Los campos MAPI están guardados en streams con nombres como:
#   __substg1.0_<TAG><TYPE>
# Tags útiles:
#   0x0037 = subject (asunto)
#   0x0042 = sent representing name
#   0x0C1A = sender name
#   0x0C1F = sender email address
#   0x0E1D = normalized subject
#   0x1000 = body (plain text)
#   0x1013 = body HTML
#   0x007D = transport message headers
# Tipos:
#   001E = string ANSI
#   001F = string Unicode (UTF-16 LE)
#   0102 = binary

PROP_TAGS = {
    'subject': '0037',
    'sender_name': '0C1A',
    'sender_email': '0C1F',
    'sender_smtp': '5D01',  # PR_SENDER_SMTP_ADDRESS
    'body_plain': '1000',
    'body_html': '1013',
    'body_html_bin': '1013',
    'headers': '007D',
    'sent_repr_name': '0042',
    'sent_repr_email': '0065',
    'sent_repr_smtp': '5D02',
    'submit_time': '0039',
    'delivery_time': '0E06',
    'creation_time': '3007',
    'received_by_email': '0076',
}


def get_property(parser: CFBParser, tag: str) -> Optional[bytes]:
    """Busca una propiedad MAPI por tag. Prueba string Unicode, ANSI, y binario."""
    for type_code in ['001F', '001E', '0102']:
        name = f'__substg1.0_{tag}{type_code}'
        data = parser.read_stream(name)
        if data is not None:
            if type_code == '001F':
                try:
                    return data.decode('utf-16-le', errors='replace').rstrip('\x00')
                except Exception:
                    pass
            elif type_code == '001E':
                try:
                    return data.decode('cp1252', errors='replace').rstrip('\x00')
                except Exception:
                    pass
            else:
                # Binario - probar UTF-8 luego cp1252
                try:
                    return data.decode('utf-8').rstrip('\x00')
                except Exception:
                    return data.decode('cp1252', errors='replace').rstrip('\x00')
    return None


def parse_msg(path: str) -> dict:
    """Parsea un archivo .msg y devuelve dict con los campos clave."""
    parser = CFBParser(path)
    result = {
        'subject': get_property(parser, PROP_TAGS['subject']),
        'sender_name': get_property(parser, PROP_TAGS['sender_name']),
        'sender_email': get_property(parser, PROP_TAGS['sender_email']),
        'sender_smtp': get_property(parser, PROP_TAGS['sender_smtp']),
        'body_plain': get_property(parser, PROP_TAGS['body_plain']),
        'body_html': get_property(parser, PROP_TAGS['body_html']),
        'headers': get_property(parser, PROP_TAGS['headers']),
        'submit_time': get_property(parser, PROP_TAGS['submit_time']),
        'delivery_time': get_property(parser, PROP_TAGS['delivery_time']),
    }
    # Tiempo se guarda en formato FILETIME en streams binarios; intentar leerlo de los headers
    return result


if __name__ == '__main__':
    import sys
    msg = parse_msg(sys.argv[1])
    print("Asunto:", msg['subject'])
    print("De:", msg['sender_name'], '<' + (msg['sender_smtp'] or msg['sender_email'] or '') + '>')
    print("Tamaño HTML:", len(msg['body_html'] or ''))
    print("Tamaño texto:", len(msg['body_plain'] or ''))
    print()
    print("--- HEADERS (primeras 500 chars) ---")
    print((msg['headers'] or '')[:500])
