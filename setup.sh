#!/usr/bin/env bash
set -euo pipefail

echo "=== TempMail Server Setup ==="
echo ""

# --- Check root ---
if [ "$(id -u)" -ne 0 ]; then
    echo "ERROR: Must run as root (for port 25 & firewall)."
    echo "  sudo bash setup.sh"
    exit 1
fi

# --- Config ---
DOMAIN="${DOMAIN:-}"
SMTP_PORT="${SMTP_PORT:-25}"
WEB_PORT="${WEB_PORT:-5000}"
WEB_HOST="${WEB_HOST:-0.0.0.0}"
SMTP_HOST="${SMTP_HOST:-0.0.0.0}"
APP_DIR="$(cd "$(dirname "$0")" && pwd)"

# --- Parse domain ---
if [ -z "$DOMAIN" ]; then
    read -rp "Enter your domain (e.g. tempmail.example.com): " DOMAIN
fi
DOMAIN="${DOMAIN#https://}"
DOMAIN="${DOMAIN#http://}"
DOMAIN="${DOMAIN%%/*}"

if [ -z "$DOMAIN" ]; then
    echo "ERROR: Domain is required."
    exit 1
fi

echo ""
echo "Domain:   $DOMAIN"
echo "SMTP:     $SMTP_HOST:$SMTP_PORT"
echo "Web UI:   http://$WEB_HOST:$WEB_PORT"
echo ""

# --- Install deps ---
echo ">>> Installing Python dependencies..."
pip3 install --break-system-packages -r "$APP_DIR/requirements.txt" 2>&1 | tail -2 || \
pip install -r "$APP_DIR/requirements.txt" 2>&1 | tail -2

# --- Firewall ---
echo ">>> Opening firewall ports..."
for port in "$SMTP_PORT" "$WEB_PORT"; do
    if command -v ufw &>/dev/null; then
        ufw allow "$port/tcp" 2>/dev/null && echo "  ufw: $port/tcp opened"
    elif command -v firewall-cmd &>/dev/null; then
        firewall-cmd --add-port="$port/tcp" --permanent 2>/dev/null && \
        firewall-cmd --reload 2>/dev/null && echo "  firewalld: $port/tcp opened"
    elif command -v iptables &>/dev/null; then
        iptables -A INPUT -p tcp --dport "$port" -j ACCEPT 2>/dev/null && echo "  iptables: $port/tcp opened"
    else
        echo "  WARNING: No firewall tool found. Open port $port manually."
    fi
done

# --- Systemd service ---
SERVICE_FILE="/etc/systemd/system/tempmail.service"
echo ">>> Creating systemd service..."

cat > "$SERVICE_FILE" <<SERVICEEOF
[Unit]
Description=TempMail Server
After=network.target

[Service]
Type=simple
User=$(who am i | awk '{print $1}')
WorkingDirectory=$APP_DIR
Environment="SMTP_HOST=$SMTP_HOST"
Environment="SMTP_PORT=$SMTP_PORT"
Environment="WEB_HOST=$WEB_HOST"
Environment="WEB_PORT=$WEB_PORT"
ExecStart=$(which python3) $APP_DIR/app.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
SERVICEEOF

systemctl daemon-reload
systemctl enable tempmail.service
systemctl restart tempmail.service

echo ">>> Service started."

# --- DNS instructions ---
IP=""
if command -v curl &>/dev/null; then
    IP=$(curl -s https://api.ipify.org 2>/dev/null || echo "")
fi
if [ -z "$IP" ] && command -v dig &>/dev/null; then
    IP=$(dig +short myip.opendns.com @resolver1.opendns.com 2>/dev/null || echo "")
fi
if [ -z "$IP" ]; then
    IP="<YOUR_SERVER_PUBLIC_IP>"
fi

echo ""
echo "================================================"
echo "  SETUP COMPLETE"
echo "================================================"
echo ""
echo "  Web UI:   http://$IP:$WEB_PORT"
echo "  SMTP:     $IP:$SMTP_PORT"
echo ""
echo "  1. Log in to your domain registrar / DNS panel."
echo ""
echo "  2. Add these DNS records for $DOMAIN:"
echo ""
echo "     Record    Name              Value"
echo "     ------    ----              -----"
echo "     MX        @                  $IP"
echo "     A         @                  $IP"
echo "     (optional) AAAA              <IPv6 if available>"
echo ""
echo "  3. Add $DOMAIN in the TempMail Web UI."
echo ""
echo "  4. Create an inbox like hello@$DOMAIN."
echo ""
echo "  5. Send a test email from any external account."
echo ""
echo "  TIP: For Gmail/Outlook deliverability, also add:"
echo "       TXT    @    v=spf1 mx ~all"
echo "       TXT    @    v=DMARC1; p=none;"
echo "================================================"
