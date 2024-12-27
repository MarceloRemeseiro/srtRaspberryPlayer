import os
from pathlib import Path

# Rutas base
BASE_DIR = Path(__file__).resolve().parent.parent.parent
ASSETS_DIR = BASE_DIR / 'assets'

# Configuración
DEVICE_ID = 'PLAYER_02'
SERVER_URL = 'https://central.streamingpro.es'
CONFIG_CHECK_INTERVAL = 5   # Segundos entre consultas al servidor 