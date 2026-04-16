#!/bin/bash
# ============================================
# Setup do OCI A1.Flex Instance Creator Bot
# Roda na VM Oracle de 1GB (Oracle Linux / Ubuntu)
# ============================================

set -e

echo "========================================"
echo "  OCI Bot - Script de Instalação"
echo "========================================"
echo ""

# Detecta o gerenciador de pacotes
if command -v dnf &> /dev/null; then
    PKG_MANAGER="dnf"
    echo "📦 Detectado: Oracle Linux / RHEL (dnf)"
elif command -v yum &> /dev/null; then
    PKG_MANAGER="yum"
    echo "📦 Detectado: Oracle Linux / RHEL (yum)"
elif command -v apt-get &> /dev/null; then
    PKG_MANAGER="apt-get"
    echo "📦 Detectado: Ubuntu / Debian (apt-get)"
else
    echo "❌ Gerenciador de pacotes não detectado!"
    exit 1
fi

echo ""

# ─── 1. Instala Python 3 e pip ───
echo "📥 [1/3] Instalando Python 3 e pip..."
if [ "$PKG_MANAGER" = "apt-get" ]; then
    sudo apt-get update -y
    sudo apt-get install -y python3 python3-pip python3-venv
else
    sudo $PKG_MANAGER install -y python3 python3-pip
fi

echo "   ✅ Python $(python3 --version | cut -d' ' -f2) instalado"
echo ""

# ─── 2. Instala dependências Python ───
echo "📥 [2/3] Instalando OCI SDK e dependências..."

# Cria um virtual environment para não poluir o sistema
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/venv"

python3 -m venv "$VENV_DIR"
source "$VENV_DIR/bin/activate"

pip install --upgrade pip
pip install oci requests

echo "   ✅ OCI SDK e requests instalados no venv"
echo ""

# ─── 3. Cria serviço systemd ───
echo "📥 [3/3] Configurando serviço systemd..."

BOT_PATH="$SCRIPT_DIR/oci_instance_bot.py"
PYTHON_PATH="$VENV_DIR/bin/python3"
WORKING_DIR="$SCRIPT_DIR"

# Cria o arquivo de serviço
sudo tee /etc/systemd/system/oci-bot.service > /dev/null << EOF
[Unit]
Description=OCI A1.Flex Instance Creator Bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$(whoami)
WorkingDirectory=$WORKING_DIR
ExecStart=$PYTHON_PATH $BOT_PATH --config $WORKING_DIR/config.json
Restart=on-failure
RestartSec=30
StandardOutput=journal
StandardError=journal

# Limites de memória (para a VM de 1GB)
MemoryMax=200M
MemoryHigh=150M

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable oci-bot.service

echo "   ✅ Serviço 'oci-bot' criado e habilitado"
echo ""

# ─── Concluído ───
echo "========================================"
echo "  ✅ Instalação concluída!"
echo "========================================"
echo ""
echo "📋 Próximos passos:"
echo ""
echo "  1. Configure o bot:"
echo "     cp config.example.json config.json"
echo "     nano config.json"
echo ""
echo "  2. Teste manualmente:"
echo "     $PYTHON_PATH $BOT_PATH"
echo ""
echo "  3. Inicie o serviço em background:"
echo "     sudo systemctl start oci-bot"
echo ""
echo "  4. Veja os logs em tempo real:"
echo "     sudo journalctl -u oci-bot -f"
echo ""
echo "  📌 Comandos úteis:"
echo "     sudo systemctl status oci-bot    # Ver status"
echo "     sudo systemctl stop oci-bot      # Parar"
echo "     sudo systemctl restart oci-bot   # Reiniciar"
echo "     tail -f oci_bot.log              # Log do bot"
echo ""
