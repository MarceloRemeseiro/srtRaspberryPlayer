import os
from pathlib import Path
import uuid

# Rutas base
BASE_DIR = Path(__file__).resolve().parent.parent.parent
ASSETS_DIR = BASE_DIR / 'assets'

# Configuración
def generate_device_id():
    # Genera un UUID y toma los primeros 3 caracteres
    random_id = str(uuid.uuid4())[:3]
    return f'PLAYER_{random_id}'

DEVICE_ID = generate_device_id()  # Ejemplo: PLAYER_a1b
SERVER_URL = 'https://central.streamingpro.es'
CONFIG_CHECK_INTERVAL = 5   # Segundos entre consultas al servidor 