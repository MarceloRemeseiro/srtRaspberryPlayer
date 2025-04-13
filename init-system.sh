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

echo -e "${GREEN}=== Instalando dependencias para SRT Player ===${NC}"

# Actualizar repositorios
echo -e "${YELLOW}Actualizando repositorios...${NC}"
apt-get update

# Instalar dependencias esenciales
echo -e "${YELLOW}Instalando dependencias esenciales...${NC}"
apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    python3-requests \
    vlc \
    alsa-utils

# Configurar framebuffer para vc4-fkms-v3d
echo -e "${YELLOW}Verificando y configurando framebuffer...${NC}"
if [ -e /dev/fb0 ]; then
    echo -e "${GREEN}Framebuffer detectado en /dev/fb0${NC}"
else
    echo -e "${RED}Framebuffer no encontrado. Verificando configuración...${NC}"
    
    # Configurar dtoverlay
    if grep -q "dtoverlay=vc4-kms-v3d" /boot/config.txt; then
        # Si está en modo KMS, cambiarlo a FKMS
        sed -i 's/dtoverlay=vc4-kms-v3d/dtoverlay=vc4-fkms-v3d/' /boot/config.txt
        echo -e "${YELLOW}Cambiado de KMS a FKMS en config.txt. Se requiere reiniciar.${NC}"
    elif ! grep -q "dtoverlay=vc4-fkms-v3d" /boot/config.txt; then
        # Si no está configurado, añadir FKMS
        echo "dtoverlay=vc4-fkms-v3d,cma-256" >> /boot/config.txt
        echo -e "${YELLOW}Añadido dtoverlay=vc4-fkms-v3d,cma-256 a config.txt. Se requiere reiniciar.${NC}"
    fi
fi

# Configurar audio HDMI
echo -e "${YELLOW}Configurando audio HDMI...${NC}"
amixer cset numid=3 2 2>/dev/null || echo -e "${YELLOW}No se pudo configurar HDMI directamente, continuando...${NC}"

# Verificar que audio esté habilitado en config.txt
echo -e "${YELLOW}Verificando configuración de audio en /boot/config.txt...${NC}"
if ! grep -q "^dtparam=audio=on" /boot/config.txt; then
    echo "dtparam=audio=on" >> /boot/config.txt
    echo -e "${GREEN}Audio habilitado en /boot/config.txt${NC}"
fi

# Cargar módulo de sonido
echo -e "${YELLOW}Cargando módulo de sonido...${NC}"
modprobe snd-bcm2835 2>/dev/null || echo -e "${YELLOW}No se pudo cargar módulo de sonido, continuando...${NC}"

# Instalar requests de Python
echo -e "${YELLOW}Instalando dependencias de Python...${NC}"
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

# Configurar audio por defecto
echo "🔊 Configurando audio por defecto..."
cat > /etc/modprobe.d/alsa-base.conf << EOF
options snd-bcm2835 index=0
EOF

# Configuración para usar VLC con usuario pi

# 1. Crear directorio de debug
mkdir -p /home/pi/srt-player-debug
chown pi:pi /home/pi/srt-player-debug

# 2. Asegurar que VLC está instalado
apt-get update && apt-get install -y vlc

# 3. Configurar servicio systemd para usuario pi
cat > /etc/systemd/system/srt-player-user.service << 'EOF'
[Unit]
Description=SRT Player Service (User Mode)
After=network.target

[Service]
Type=simple
User=pi
Group=pi
WorkingDirectory=/home/pi/srtRaspberryPlayer
ExecStart=/usr/bin/python3 -u src/main.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

# 4. Recargar systemd y configurar servicios
systemctl daemon-reload
systemctl stop srt-player
systemctl disable srt-player
systemctl enable srt-player-user
systemctl start srt-player-user

# 5. Verificar estado
systemctl status srt-player-user

echo -e "${GREEN}=== Instalación completada ===${NC}"
echo -e "${GREEN}MPV configurado correctamente para reproducción de streams SRT${NC}"
echo -e "${GREEN}Reinicia el sistema para aplicar todos los cambios${NC}"
echo -e "${YELLOW}Comando para ver logs: journalctl -u srt-player -f${NC}"