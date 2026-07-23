import sqlite3, os, random, string, uuid
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash

DB_PATH = os.path.join(os.path.dirname(__file__), 'mail.db')

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn

def init_db():
    conn = get_db()
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            is_admin INTEGER DEFAULT 0,
            is_active INTEGER DEFAULT 0,
            expires_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS domains (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            domain TEXT UNIQUE NOT NULL,
            user_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS inboxes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            address TEXT NOT NULL,
            domain_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP NOT NULL,
            is_active INTEGER DEFAULT 1,
            public_token TEXT,
            FOREIGN KEY (domain_id) REFERENCES domains(id),
            FOREIGN KEY (user_id) REFERENCES users(id),
            UNIQUE(address, domain_id)
        );
        CREATE TABLE IF NOT EXISTS emails (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            inbox_id INTEGER NOT NULL,
            sender TEXT NOT NULL,
            subject TEXT DEFAULT '',
            body_text TEXT DEFAULT '',
            body_html TEXT DEFAULT '',
            is_read INTEGER DEFAULT 0,
            received_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (inbox_id) REFERENCES inboxes(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_emails_inbox ON emails(inbox_id);
        CREATE INDEX IF NOT EXISTS idx_inboxes_expires ON inboxes(expires_at);
    ''')
    for col in ['is_admin', 'is_active', 'expires_at']:
        try:
            conn.execute(f'ALTER TABLE users ADD COLUMN {col} INTEGER' if col != 'expires_at' else f'ALTER TABLE users ADD COLUMN {col} TEXT')
        except sqlite3.OperationalError:
            pass
    try:
        conn.execute('ALTER TABLE inboxes ADD COLUMN public_token TEXT')
    except sqlite3.OperationalError:
        pass
    conn.commit()
    conn.close()

def gen_random_address(length=10):
    chars = string.ascii_lowercase + string.digits
    return ''.join(random.choice(chars) for _ in range(length))

# --- Users ---

def create_user(username, password):
    conn = get_db()
    try:
        first_user = conn.execute('SELECT COUNT(*) as c FROM users').fetchone()['c'] == 0
        is_admin = 1 if first_user else 0
        conn.execute('INSERT INTO users (username, password, is_admin, is_active) VALUES (?, ?, ?, ?)',
                     (username, generate_password_hash(password), is_admin, is_admin))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def verify_user(username, password):
    conn = get_db()
    user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
    conn.close()
    if user and check_password_hash(user['password'], password):
        return dict(user)
    return None

def get_user_by_id(user_id):
    if not user_id:
        return None
    conn = get_db()
    user = conn.execute('SELECT * FROM users WHERE id=?', (user_id,)).fetchone()
    conn.close()
    return dict(user) if user else None

def get_all_users():
    conn = get_db()
    rows = conn.execute('SELECT * FROM users ORDER BY created_at DESC').fetchall()
    conn.close()
    return [dict(r) for r in rows]

def activate_user(user_id, days=30):
    conn = get_db()
    expires_at = (datetime.utcnow() + timedelta(days=days)).isoformat()
    conn.execute('UPDATE users SET is_active=1, expires_at=? WHERE id=?', (expires_at, user_id))
    conn.commit()
    conn.close()

def deactivate_user(user_id):
    conn = get_db()
    conn.execute('UPDATE users SET is_active=0, expires_at=NULL WHERE id=?', (user_id,))
    conn.commit()
    conn.close()

def is_user_active(user):
    if not user:
        return False
    u = dict(user)
    if u.get('is_admin'):
        return True
    if not u.get('is_active'):
        return False
    expires_at = u.get('expires_at')
    if expires_at:
        try:
            if datetime.fromisoformat(expires_at) < datetime.utcnow():
                return False
        except (ValueError, TypeError):
            return False
    return True

# --- Domains ---

def add_domain(domain, user_id):
    conn = get_db()
    try:
        conn.execute('INSERT INTO domains (domain, user_id) VALUES (?, ?)', (domain, user_id))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def get_domains(user_id):
    conn = get_db()
    domains = conn.execute('SELECT * FROM domains WHERE user_id = ? ORDER BY domain', (user_id,)).fetchall()
    conn.close()
    return domains

def get_all_domains():
    conn = get_db()
    domains = conn.execute('SELECT d.*, u.username FROM domains d JOIN users u ON d.user_id = u.id').fetchall()
    conn.close()
    return domains

def delete_domain(domain_id, user_id):
    conn = get_db()
    conn.execute('DELETE FROM inboxes WHERE domain_id IN (SELECT id FROM domains WHERE id=? AND user_id=?)',
                 (domain_id, user_id))
    conn.execute('DELETE FROM domains WHERE id=? AND user_id=?', (domain_id, user_id))
    conn.commit()
    conn.close()

def get_domain_by_name(domain_name):
    conn = get_db()
    domain = conn.execute('SELECT * FROM domains WHERE domain = ?', (domain_name,)).fetchone()
    conn.close()
    return domain

# --- Inboxes ---

def create_inbox(address, domain_id, user_id, days=30):
    conn = get_db()
    expires_at = (datetime.utcnow() + timedelta(days=days)).isoformat()
    public_token = uuid.uuid4().hex[:16]
    try:
        conn.execute(
            'INSERT INTO inboxes (address, domain_id, user_id, expires_at, public_token) VALUES (?, ?, ?, ?, ?)',
            (address, domain_id, user_id, expires_at, public_token)
        )
        conn.commit()
        inbox = conn.execute('''
            SELECT i.*, d.domain FROM inboxes i
            JOIN domains d ON i.domain_id = d.id
            WHERE i.address=? AND i.domain_id=?
        ''', (address, domain_id)).fetchone()
        return inbox
    except sqlite3.IntegrityError:
        return None
    finally:
        conn.close()

def get_inboxes(user_id):
    conn = get_db()
    inboxes = conn.execute('''
        SELECT i.*, d.domain FROM inboxes i
        JOIN domains d ON i.domain_id = d.id
        WHERE i.user_id = ? AND i.is_active = 1
        ORDER BY i.created_at DESC
    ''', (user_id,)).fetchall()
    conn.close()
    return inboxes

def get_inbox_by_email(email_addr):
    if '@' not in email_addr:
        return None
    local, domain = email_addr.lower().split('@', 1)
    conn = get_db()
    inbox = conn.execute('''
        SELECT i.*, d.domain FROM inboxes i
        JOIN domains d ON i.domain_id = d.id
        WHERE i.address = ? AND d.domain = ? AND i.is_active = 1
    ''', (local, domain)).fetchone()
    if inbox and datetime.fromisoformat(inbox['expires_at']) < datetime.utcnow():
        conn.execute('UPDATE inboxes SET is_active=0 WHERE id=?', (inbox['id'],))
        conn.commit()
        inbox = None
    conn.close()
    return inbox

def get_inbox_by_id(inbox_id, user_id):
    conn = get_db()
    inbox = conn.execute('''
        SELECT i.*, d.domain FROM inboxes i
        JOIN domains d ON i.domain_id = d.id
        WHERE i.id = ? AND i.user_id = ? AND i.is_active = 1
    ''', (inbox_id, user_id)).fetchone()
    conn.close()
    return inbox

def get_inbox_by_token(token):
    conn = get_db()
    inbox = conn.execute('''
        SELECT i.*, d.domain FROM inboxes i
        JOIN domains d ON i.domain_id = d.id
        WHERE i.public_token = ? AND i.is_active = 1
    ''', (token,)).fetchone()
    if inbox and datetime.fromisoformat(inbox['expires_at']) < datetime.utcnow():
        conn.execute('UPDATE inboxes SET is_active=0 WHERE id=?', (inbox['id'],))
        conn.commit()
        inbox = None
    conn.close()
    return inbox

def get_emails_for_inbox_public(inbox_id, page=1, per_page=50):
    conn = get_db()
    offset = (page - 1) * per_page
    emails = conn.execute('''
        SELECT e.* FROM emails e
        WHERE e.inbox_id = ?
        ORDER BY e.received_at DESC LIMIT ? OFFSET ?
    ''', (inbox_id, per_page, offset)).fetchall()
    total = conn.execute('SELECT COUNT(*) as c FROM emails WHERE inbox_id=?', (inbox_id,)).fetchone()['c']
    conn.close()
    return emails, total

def get_email_public(email_id, inbox_id):
    conn = get_db()
    email = conn.execute('SELECT * FROM emails WHERE id=? AND inbox_id=?', (email_id, inbox_id)).fetchone()
    if email and not email['is_read']:
        conn.execute('UPDATE emails SET is_read=1 WHERE id=?', (email_id,))
        conn.commit()
    conn.close()
    return email

def delete_inbox(inbox_id, user_id):
    conn = get_db()
    conn.execute('DELETE FROM emails WHERE inbox_id=?', (inbox_id,))
    conn.execute('DELETE FROM inboxes WHERE id=? AND user_id=?', (inbox_id, user_id))
    conn.commit()
    conn.close()

# --- Emails ---

def save_email(inbox_id, sender, subject, body_text, body_html=''):
    conn = get_db()
    conn.execute(
        'INSERT INTO emails (inbox_id, sender, subject, body_text, body_html) VALUES (?, ?, ?, ?, ?)',
        (inbox_id, sender, subject, body_text, body_html)
    )
    conn.commit()
    conn.close()

def get_emails_for_inbox(inbox_id, user_id, page=1, per_page=50):
    conn = get_db()
    offset = (page - 1) * per_page
    emails = conn.execute('''
        SELECT e.* FROM emails e
        JOIN inboxes i ON e.inbox_id = i.id
        WHERE e.inbox_id = ? AND i.user_id = ?
        ORDER BY e.received_at DESC LIMIT ? OFFSET ?
    ''', (inbox_id, user_id, per_page, offset)).fetchall()
    total = conn.execute('''
        SELECT COUNT(*) as c FROM emails e
        JOIN inboxes i ON e.inbox_id = i.id
        WHERE e.inbox_id = ? AND i.user_id = ?
    ''', (inbox_id, user_id)).fetchone()['c']
    conn.close()
    return emails, total

def get_email(email_id, user_id):
    conn = get_db()
    email = conn.execute('''
        SELECT e.* FROM emails e
        JOIN inboxes i ON e.inbox_id = i.id
        WHERE e.id = ? AND i.user_id = ?
    ''', (email_id, user_id)).fetchone()
    if email and not email['is_read']:
        conn.execute('UPDATE emails SET is_read=1 WHERE id=?', (email_id,))
        conn.commit()
    conn.close()
    return email

def delete_email(email_id, user_id):
    conn = get_db()
    conn.execute('''
        DELETE FROM emails WHERE id=? AND inbox_id IN
        (SELECT id FROM inboxes WHERE user_id=?)
    ''', (email_id, user_id))
    conn.commit()
    conn.close()

def cleanup_expired():
    conn = get_db()
    conn.execute('UPDATE inboxes SET is_active=0 WHERE expires_at < datetime("now")')
    conn.execute('''
        DELETE FROM emails WHERE inbox_id IN
        (SELECT id FROM inboxes WHERE is_active=0)
    ''')
    conn.execute('DELETE FROM inboxes WHERE is_active=0')
    conn.commit()
    conn.close()
