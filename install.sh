#!/bin/bash

# Verificar si se ejecuta como root
if [ "$EUID" -ne 0 ]; then 
    echo "Por favor, ejecuta el script como root (usando sudo)"
    exit 1
fi

echo "🚀 Iniciando configuración del SRT Player con VLC..."

# Colores para mensajes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}=== Instalando dependencias para SRT Player con VLC ===${NC}"

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
    alsa-utils \
    git

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

# Ejecutar script de configuración X11
echo -e "${YELLOW}Configurando entorno X11...${NC}"
if [ -f "/home/pi/srtRaspberryPlayer/setup-x11.sh" ]; then
    bash /home/pi/srtRaspberryPlayer/setup-x11.sh
else
    echo -e "${RED}No se encontró el script setup-x11.sh, asegúrate de clonar el repositorio primero${NC}"
    exit 1
fi

# Copiar servicio systemd
echo -e "${YELLOW}Configurando servicio systemd...${NC}"
if [ -f "/home/pi/srtRaspberryPlayer/srt-player-user.service" ]; then
    cp /home/pi/srtRaspberryPlayer/srt-player-user.service /etc/systemd/system/
    systemctl daemon-reload
    systemctl enable srt-player-user
    systemctl restart srt-player-user
else
    echo -e "${RED}No se encontró el archivo srt-player-user.service, asegúrate de tenerlo en el repositorio${NC}"
    exit 1
fi

# Verificar estado del servicio
echo -e "${YELLOW}Verificando estado del servicio...${NC}"
systemctl status srt-player-user --no-pager

echo -e "${GREEN}=== Instalación completada ===${NC}"
echo -e "${GREEN}VLC configurado correctamente para reproducción de streams SRT como usuario pi${NC}"
echo -e "${YELLOW}Comando para ver logs: journalctl -u srt-player-user -f${NC}"
echo -e "${YELLOW}Puede que sea necesario reiniciar el sistema para que todos los cambios surtan efecto${NC}" 