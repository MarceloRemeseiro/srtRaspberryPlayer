#!/bin/bash

# Verificar si se ejecuta como root
if [ "$EUID" -ne 0 ]; then 
    echo "Por favor, ejecuta el script como root (usando sudo)"
    exit 1
fi

echo "🚀 Iniciando configuración del sistema..."

# Detener el servicio si existe
if systemctl is-active --quiet srt-player; then
    echo "🛑 Deteniendo servicio existente..."
    systemctl stop srt-player
fi

# Colores para mensajes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}=== Instalando dependencias mínimas para SRT Player ===${NC}"

# Actualizar repositorios
echo -e "${YELLOW}Actualizando repositorios...${NC}"
apt-get update

# Instalar solo dependencias esenciales
echo -e "${YELLOW}Instalando dependencias esenciales...${NC}"
apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    python3-requests \
    omxplayer \
    alsa-utils

# Configurar audio HDMI
echo -e "${YELLOW}Configurando audio HDMI...${NC}"
amixer cset numid=3 2

# Verificar que audio esté habilitado en config.txt
echo -e "${YELLOW}Verificando configuración de audio en /boot/config.txt...${NC}"
if ! grep -q "^dtparam=audio=on" /boot/config.txt; then
    echo "dtparam=audio=on" >> /boot/config.txt
    echo -e "${GREEN}Audio habilitado en /boot/config.txt${NC}"
fi

# Cargar módulo de sonido
echo -e "${YELLOW}Cargando módulo de sonido...${NC}"
modprobe snd-bcm2835

# Verificar si OMXPlayer está instalado correctamente
if command -v omxplayer >/dev/null 2>&1; then
    echo -e "${GREEN}OMXPlayer instalado correctamente${NC}"
else
    echo -e "${RED}Error: OMXPlayer no se pudo instalar${NC}"
    exit 1
fi

# Instalar solo requests de Python
echo -e "${YELLOW}Instalando requests para Python...${NC}"
pip3 install requests

# 1. Servicio del player
echo "🔧 Configurando servicio del player..."
cat > /etc/systemd/system/srt-player.service << EOF
[Unit]
Description=SRT Player Service
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/srtRaspberryPlayer
Environment=PYTHONPATH=/root/srtRaspberryPlayer/src
ExecStart=/usr/bin/python3 -u src/main.py
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

# 2. Servicio para deshabilitar cursor
echo "🖥️ Configurando servicio del cursor..."
cat > /etc/systemd/system/disable-cursor.service << EOF
[Unit]
Description=Disable cursor on framebuffer
After=getty.target

[Service]
Type=oneshot
ExecStart=/bin/sh -c 'echo 0 > /sys/class/graphics/fbcon/cursor_blink'
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOF

# 3. Configurar cmdline.txt si no está ya configurado
echo "⚙️ Configurando cmdline.txt..."
if ! grep -q "vt.global_cursor_default=0" /boot/cmdline.txt; then
    sed -i 's/$/ vt.global_cursor_default=0 logo.nologo consoleblank=0/' /boot/cmdline.txt
fi

# 4. Recargar systemd
echo "🔄 Recargando systemd..."
systemctl daemon-reload

# 5. Habilitar servicios
echo "✅ Habilitando servicios..."
systemctl enable srt-player
systemctl enable disable-cursor

# 6. Iniciar servicios
echo "▶️ Iniciando servicios..."
systemctl start disable-cursor
systemctl start srt-player

# Configurar ALSA
echo "🔊 Configurando ALSA..."
cat > /etc/asound.conf << EOF
pcm.!default {
    type hw
    card 0
    device 1
}

ctl.!default {
    type hw
    card 0
}
EOF

# Añadir soporte gráfico y audio
if ! grep -q "vc4-kms-v3d" /boot/config.txt; then
    echo "dtoverlay=vc4-kms-v3d" >> /boot/config.txt
fi

# Configurar audio por defecto
echo "🔊 Configurando audio por defecto..."
cat > /etc/modprobe.d/alsa-base.conf << EOF
options snd-bcm2835 index=0
EOF

echo -e "${GREEN}=== Instalación completada ===${NC}"
echo -e "${GREEN}Reinicia el sistema para aplicar todos los cambios${NC}"
echo -e "${YELLOW}Comando para ver logs: journalctl -u srt-player -f${NC}"