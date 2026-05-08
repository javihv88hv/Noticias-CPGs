"""
Descarga archivos .eml de la carpeta de Google Drive
y los deja en una carpeta local. Marca los descargados moviéndolos
a una subcarpeta "procesados" dentro de Drive (idempotencia).
"""
import os
import sys
import json
import io
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

SCOPES = ['https://www.googleapis.com/auth/drive']

def main():
    # Leer credenciales del entorno
    credentials_json = os.environ['GOOGLE_SERVICE_ACCOUNT_JSON']
    folder_id = os.environ['DRIVE_FOLDER_ID']
    
    output_dir = sys.argv[1] if len(sys.argv) > 1 else 'nuevos-eml'
    os.makedirs(output_dir, exist_ok=True)
    
    creds_info = json.loads(credentials_json)
    creds = service_account.Credentials.from_service_account_info(
        creds_info, scopes=SCOPES
    )
    service = build('drive', 'v3', credentials=creds)
    
    # Buscar (o crear) subcarpeta "procesados"
    procesados_id = get_or_create_subfolder(service, folder_id, 'procesados')
    
    # Listar archivos .eml en la carpeta principal (no recursivo)
    query = (
        f"'{folder_id}' in parents "
        f"and trashed = false "
        f"and mimeType != 'application/vnd.google-apps.folder'"
    )
    results = service.files().list(
        q=query,
        fields='files(id, name, mimeType)',
        pageSize=200
    ).execute()
    files = results.get('files', [])
    
    print(f'Archivos encontrados en Drive: {len(files)}', flush=True)
    
    if not files:
        print('No hay archivos nuevos para procesar.', flush=True)
        return
    
    downloaded = 0
    for file in files:
        file_id = file['id']
        name = file['name']
        if not name.lower().endswith('.eml'):
            print(f'  Saltando (no es .eml): {name}', flush=True)
            continue
        
        local_path = os.path.join(output_dir, name)
        try:
            # Descargar
            request = service.files().get_media(fileId=file_id)
            fh = io.FileIO(local_path, 'wb')
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while not done:
                _, done = downloader.next_chunk()
            fh.close()
            
            # Mover a "procesados" en Drive
            service.files().update(
                fileId=file_id,
                addParents=procesados_id,
                removeParents=folder_id,
                fields='id, parents'
            ).execute()
            
            downloaded += 1
            print(f'  ✓ {name}', flush=True)
        except Exception as e:
            print(f'  ✗ Error con {name}: {e}', flush=True)
    
    print(f'\nDescargados {downloaded} archivos en {output_dir}/', flush=True)


def get_or_create_subfolder(service, parent_id, name):
    """Obtiene el ID de una subcarpeta, creándola si no existe."""
    query = (
        f"'{parent_id}' in parents "
        f"and name = '{name}' "
        f"and mimeType = 'application/vnd.google-apps.folder' "
        f"and trashed = false"
    )
    results = service.files().list(q=query, fields='files(id)').execute()
    folders = results.get('files', [])
    if folders:
        return folders[0]['id']
    
    # Crear
    metadata = {
        'name': name,
        'mimeType': 'application/vnd.google-apps.folder',
        'parents': [parent_id]
    }
    created = service.files().create(body=metadata, fields='id').execute()
    return created['id']


if __name__ == '__main__':
    main()
