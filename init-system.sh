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
    ffmpeg \
    alsa-utils \
    libpcre3 \
    fonts-freefont-ttf \
    vlc

# Intentar instalar OMXPlayer
echo -e "${YELLOW}Intentando instalar OMXPlayer...${NC}"

# Primero verificar si ya está instalado
if command -v omxplayer >/dev/null 2>&1; then
    echo -e "${GREEN}OMXPlayer ya está instalado${NC}"
    OMXPLAYER_INSTALLED=true
else
    # Intentar instalar desde los repositorios
    echo -e "${YELLOW}Intentando instalar OMXPlayer desde los repositorios...${NC}"
    apt-get install -y omxplayer || true
    
    # Verificar si se instaló correctamente
    if command -v omxplayer >/dev/null 2>&1; then
        echo -e "${GREEN}OMXPlayer instalado correctamente desde los repositorios${NC}"
        OMXPLAYER_INSTALLED=true
    else
        # Intentar descargar el paquete .deb
        echo -e "${YELLOW}Intentando instalar OMXPlayer desde paquete .deb...${NC}"
        cd /tmp
        wget http://omxplayer.sconde.net/builds/omxplayer_0.3.6~git20150505~b1ad23e_armhf.deb
        
        # Intentar instalar el paquete
        dpkg -i omxplayer_*_armhf.deb || true
        apt-get -f install -y  # Corregir dependencias
        
        # Verificar de nuevo
        if command -v omxplayer >/dev/null 2>&1; then
            echo -e "${GREEN}OMXPlayer instalado correctamente desde el paquete .deb${NC}"
            OMXPLAYER_INSTALLED=true
        else
            echo -e "${RED}No se pudo instalar OMXPlayer. Se usará VLC como alternativa.${NC}"
            OMXPLAYER_INSTALLED=false
        fi
    fi
fi

# Configurar el directorio /opt/vc si OMXPlayer está instalado pero faltan libs
if [ "$OMXPLAYER_INSTALLED" = true ]; then
    echo -e "${YELLOW}Verificando bibliotecas para OMXPlayer...${NC}"
    
    # Crear directorios necesarios
    mkdir -p /opt/vc/lib
    
    # Verificar si existe algún archivo en /opt/vc/lib
    if [ -z "$(ls -A /opt/vc/lib 2>/dev/null)" ]; then
        echo -e "${YELLOW}Directorio /opt/vc/lib vacío, intentando copiar bibliotecas desde el sistema...${NC}"
        
        # Intentar encontrar las bibliotecas en el sistema
        if [ -d /usr/lib/arm-linux-gnueabihf ]; then
            echo -e "${YELLOW}Copiando bibliotecas necesarias para OMXPlayer...${NC}"
            cp /usr/lib/arm-linux-gnueabihf/libbcm_host.so* /opt/vc/lib/ 2>/dev/null || true
            cp /usr/lib/arm-linux-gnueabihf/libvcos.so* /opt/vc/lib/ 2>/dev/null || true
            cp /usr/lib/arm-linux-gnueabihf/libvchiq_arm.so* /opt/vc/lib/ 2>/dev/null || true
            cp /usr/lib/arm-linux-gnueabihf/libopenmaxil.so* /opt/vc/lib/ 2>/dev/null || true
            cp /usr/lib/arm-linux-gnueabihf/libEGL.so* /opt/vc/lib/ 2>/dev/null || true
            cp /usr/lib/arm-linux-gnueabihf/libGLESv2.so* /opt/vc/lib/ 2>/dev/null || true
            cp /usr/lib/arm-linux-gnueabihf/libbrcmEGL.so* /opt/vc/lib/ 2>/dev/null || true
            cp /usr/lib/arm-linux-gnueabihf/libbrcmGLESv2.so* /opt/vc/lib/ 2>/dev/null || true
            
            # Verificar si se copiaron archivos
            if [ -n "$(ls -A /opt/vc/lib 2>/dev/null)" ]; then
                echo -e "${GREEN}Bibliotecas copiadas correctamente a /opt/vc/lib${NC}"
            else
                echo -e "${YELLOW}No se pudieron copiar bibliotecas. OMXPlayer podría no funcionar correctamente.${NC}"
            fi
        else
            echo -e "${YELLOW}No se encontró el directorio de bibliotecas. OMXPlayer podría no funcionar.${NC}"
        fi
    else
        echo -e "${GREEN}Directorio /opt/vc/lib ya contiene archivos, omitiendo copia de bibliotecas${NC}"
    fi
    
    # Exportar la ruta de bibliotecas
    echo -e "${YELLOW}Configurando variables de entorno para OMXPlayer...${NC}"
    echo 'export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:/opt/vc/lib' > /etc/profile.d/omxplayer.sh
    chmod +x /etc/profile.d/omxplayer.sh
    source /etc/profile.d/omxplayer.sh
fi

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

# Instalar solo requests de Python
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
Environment=LD_LIBRARY_PATH=\$LD_LIBRARY_PATH:/opt/vc/lib
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

echo -e "${GREEN}=== Instalación completada ===${NC}"
if [ "$OMXPLAYER_INSTALLED" = true ]; then
    echo -e "${GREEN}OMXPlayer está instalado y configurado${NC}"
else
    echo -e "${YELLOW}OMXPlayer no está disponible. Se usará VLC como alternativa${NC}"
fi
echo -e "${GREEN}Reinicia el sistema para aplicar todos los cambios${NC}"
echo -e "${YELLOW}Comando para ver logs: journalctl -u srt-player -f${NC}"