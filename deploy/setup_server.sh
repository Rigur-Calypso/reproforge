#!/usr/bin/env bash
# ==============================================================================
# ReproForge Automated Cloud Server Setup Script
# Designed for Ubuntu 22.04 / 24.04 LTS (DigitalOcean Droplets / Cloud VMs)
# ==============================================================================

set -euo pipefail

REPO_URL="https://github.com/Rigur-Calypso/reproforge.git"
INSTALL_DIR="/opt/reproforge"

echo "=========================================================="
echo " Starting ReproForge Cloud Server Installation"
echo "=========================================================="

# 1. Update system packages
echo "[1/6] Updating system packages..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq \
    apt-transport-https \
    ca-certificates \
    curl \
    git \
    gnupg \
    lsb-release \
    python3 \
    python3-venv \
    python3-pip

# 2. Install Docker if not installed
echo "[2/6] Configuring Docker..."
if ! command -v docker &> /dev/null; then
    echo "Installing Docker Engine..."
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
    chmod a+r /etc/apt/keyrings/docker.asc
    echo \
      "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu \
      $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
      tee /etc/apt/sources.list.d/docker.list > /dev/null
    apt-get update -qq
    apt-get install -y -qq docker-ce docker-ce-cli containerd.io
fi

systemctl enable --now docker
docker info > /dev/null || { echo "Error: Docker failed to start."; exit 1; }

# 3. Clone or pull ReproForge repository
echo "[3/6] Setting up ReproForge repository at $INSTALL_DIR..."
if [ -d "$INSTALL_DIR/.git" ]; then
    echo "Updating existing repository..."
    git -C "$INSTALL_DIR" fetch origin
    git -C "$INSTALL_DIR" checkout main
    git -C "$INSTALL_DIR" pull origin main
else
    mkdir -p /opt
    git clone "$REPO_URL" "$INSTALL_DIR"
fi

cd "$INSTALL_DIR"

# 4. Build isolated worker container images
echo "[4/6] Building unprivileged Docker worker images..."
echo "  - Building reproforge-worker:py313 (Python 3.13)..."
docker build -q -t reproforge-worker:py313 -f worker/Dockerfile worker

echo "  - Building reproforge-worker:httpx (Python 3.13 + HTTPX dependencies)..."
docker build -q -t reproforge-worker:httpx -f worker/Dockerfile.httpx worker

echo "  - Building reproforge-worker:py38 (Python 3.8 + MarkupSafe 1.1.1)..."
docker build -q -t reproforge-worker:py38 -f worker/Dockerfile.py38 worker

# 5. Set up Python virtual environment
echo "[5/6] Setting up Python virtual environment and dependencies..."
python3 -m venv "$INSTALL_DIR/.venv"
"$INSTALL_DIR/.venv/bin/pip" install --upgrade pip -q
"$INSTALL_DIR/.venv/bin/pip" install -e "$INSTALL_DIR[dev]" -q

# Run self-test
echo "Running verifier integrity check..."
"$INSTALL_DIR/.venv/bin/pytest" "$INSTALL_DIR/tests/" -q

# 6. Install and enable systemd service
echo "[6/6] Registering and starting reproforge.service..."
cp "$INSTALL_DIR/deploy/reproforge.service" /etc/systemd/system/reproforge.service
systemctl daemon-reload
systemctl enable --now reproforge.service

sleep 2

# Check health endpoint
echo "Checking service health..."
curl -s http://127.0.0.1:8080/health || echo "Note: server starting up."

echo "=========================================================="
echo " ReproForge Cloud Server Installation Complete!"
echo " Server listening on: http://$(curl -s ifconfig.me || echo 'YOUR_SERVER_IP'):8080"
echo "=========================================================="
