# TempMail Server

Receive-only disposable email server with web UI. User register → admin activate → dapat inbox sementara.

## Instalasi

```bash
# 1. Clone
git clone https://github.com/Heraman/mail-server.git /opt/tempmail
cd /opt/tempmail

# 2. Install dependencies
pip3 install --break-system-packages -r requirements.txt

# 3. Firewall (port 25 untuk SMTP, 5000 untuk web)
ufw allow ssh
ufw allow 25/tcp
ufw allow 5000/tcp
ufw --force enable

# 4. Systemd service (biar jalan 24/7)
cat > /etc/systemd/system/tempmail.service << 'EOF'
[Unit]
Description=TempMail Server
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/tempmail
Environment="SMTP_HOST=0.0.0.0"
Environment="SMTP_PORT=25"
Environment="WEB_HOST=0.0.0.0"
Environment="WEB_PORT=5000"
ExecStart=$(which python3) /opt/tempmail/app.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now tempmail

# 5. Cek status
systemctl status tempmail
```

## DNS Configuration

Biar bisa terima email dari Gmail/Yahoo, tambah record ini di panel domain:

| Record | Name  | Value                    |
|--------|-------|--------------------------|
| A      | mail  | `<IP-VPS>` (DNS only)    |
| MX     | mail  | `mail.domainkamu.com`    |
| TXT    | mail  | `v=spf1 mx ~all`         |

Priority MX: `10`. Pastikan A record **DNS only** (grey cloud), bukan proxied.

## Cara Pakai

### Admin (first user)

```
http://<IP-VPS>:5000/register      → buat akun (otomatis admin)
http://<IP-VPS>:5000/login         → login
Domains                            → tambah domain (misal mail.domainkamu.com)
Inboxes                            → buat inbox → Copy Link (public)
Manage Users                       → activate user baru + set masa berlaku
```

### User

1. Register di web → akun inactive (menunggu admin activate)
2. Hubungi admin buat aktivasi
3. Buka public link yang dikasih admin
4. Lihat email masuk (auto-refresh tiap 15 detik)

### Admin Activation

```
Manage Users → pilih user → pilih masa berlaku (1/7/30/90/365 hari) → Activate
```

## Reset Database

```bash
systemctl stop tempmail
rm -f /opt/tempmail/mail.db
systemctl start tempmail     # otomatis bikin db baru + tabel
```

## Env Variables

| Variable    | Default      | Description       |
|-------------|--------------|-------------------|
| SMTP_HOST   | 127.0.0.1    | SMTP bind address |
| SMTP_PORT   | 1025         | SMTP port         |
| WEB_HOST    | 127.0.0.1    | Web bind address  |
| WEB_PORT    | 5000         | Web port          |

## Struktur File

```
app.py           — Flask web (port 5000)
smtp_server.py   — SMTP receiver (port 25)
models.py        — SQLite database + queries
templates/       — 10 template HTML
static/          — CSS
```
