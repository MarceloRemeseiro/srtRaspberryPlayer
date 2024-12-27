#!/bin/bash

# Configurar systemd
echo "Configurando servicios..."

# 1. Servicio del player
cat > /etc/systemd/system/srt-player.service << EOF
[Unit]
Description=SRT Player Service
After=network.target

[Service]
Type=simple
User=pi
WorkingDirectory=/opt/srt-player-python
Environment=PYTHONPATH=/opt/srt-player-python
ExecStart=/usr/local/bin/python src/main.py
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

# 2. Servicio para deshabilitar cursor
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

# 3. Configurar cmdline.txt
echo " vt.global_cursor_default=0 logo.nologo consoleblank=0" >> /boot/cmdline.txt

# 4. Habilitar servicios
systemctl enable srt-player
systemctl enable disable-cursor

# 5. Iniciar servicios
systemctl start disable-cursor
systemctl start srt-player

# Mantener el contenedor corriendo
exec "$@"