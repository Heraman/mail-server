# TempMail Server

Receive-only disposable email server with web UI.

## Quick Start (Production)

```bash
# On a VPS with public IP:
sudo bash setup.sh
# Enter your domain when prompted
```

## Manual Setup

```bash
pip install -r requirements.txt

# Production (port 25 + 0.0.0.0):
sudo env SMTP_HOST=0.0.0.0 SMTP_PORT=25 WEB_HOST=0.0.0.0 python app.py

# Testing local (port 1025):
python app.py
```

## DNS Configuration

For `tempmail.example.com`:

| Record | Name  | Value              |
|--------|-------|--------------------|
| MX     | @     | <your-server-ip>   |
| A      | @     | <your-server-ip>   |
| TXT    | @     | v=spf1 mx ~all     |

## Usage

1. Open web UI → Register
2. Add your domain (e.g. `tempmail.example.com`)
3. Create inbox (e.g. `hello@tempmail.example.com`)
4. Send email to that address from anywhere
5. Read it in the web UI

## Env Variables

| Variable    | Default      | Description       |
|-------------|--------------|-------------------|
| SMTP_HOST   | 127.0.0.1    | SMTP bind address |
| SMTP_PORT   | 1025         | SMTP port         |
| WEB_HOST    | 127.0.0.1    | Web bind address  |
| WEB_PORT    | 5000         | Web port          |
