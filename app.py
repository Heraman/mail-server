from flask import Flask, render_template, request, redirect, url_for, session as flask_session, flash, jsonify
from functools import wraps
import threading, time, sys, os
from datetime import datetime

from models import *
from smtp_server import SMTPServer

app = Flask(__name__)
app.secret_key = 'change-this-to-a-random-secret-key'

# --- Decorators ---

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in flask_session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

def active_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        user = get_user_by_id(flask_session.get('user_id'))
        if not user or not is_user_active(user):
            flask_session['is_active'] = False
            flash('Account inactive. Contact admin to activate.')
            return redirect(url_for('inactive'))
        flask_session['is_active'] = True
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not flask_session.get('is_admin'):
            flash('Admin only.')
            return redirect(url_for('inboxes'))
        return f(*args, **kwargs)
    return decorated

def full_email(inbox):
    return f"{inbox['address']}@{inbox['domain']}"

# --- Auth ---

@app.route('/')
def index():
    if 'user_id' in flask_session:
        return redirect(url_for('inboxes'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = verify_user(username, password)
        if user:
            flask_session['user_id'] = user['id']
            flask_session['username'] = user['username']
            flask_session['is_admin'] = bool(user.get('is_admin', 0))
            flask_session['is_active'] = is_user_active(user)
            return redirect(url_for('domains'))
        flash('Invalid username or password')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if create_user(username, password):
            flash('Registration successful. Admin will activate your account.')
            return redirect(url_for('login'))
        flash('Username already taken')
    return render_template('register.html')

@app.route('/logout')
def logout():
    flask_session.clear()
    return redirect(url_for('login'))

@app.route('/inactive')
def inactive():
    return render_template('inactive.html')

# --- Admin ---

@app.route('/admin/users')
@login_required
@admin_required
def admin_users():
    users = get_all_users()
    return render_template('admin_users.html', users=users)

@app.route('/admin/users/<int:user_id>/activate', methods=['POST'])
@login_required
@admin_required
def admin_activate(user_id):
    days = int(request.form.get('days', 30))
    activate_user(user_id, days)
    flash(f'User activated for {days} days.')
    return redirect(url_for('admin_users'))

@app.route('/admin/users/<int:user_id>/deactivate', methods=['POST'])
@login_required
@admin_required
def admin_deactivate(user_id):
    deactivate_user(user_id)
    flash('User deactivated.')
    return redirect(url_for('admin_users'))

# --- Domains ---

@app.route('/domains')
@login_required
def domains():
    user_domains = get_domains(flask_session['user_id'])
    return render_template('domains.html', domains=user_domains,
                           is_active=flask_session.get('is_active'))

@app.route('/domains/add', methods=['POST'])
@login_required
@active_required
def add_domain_route():
    domain = request.form.get('domain', '').strip().lower()
    if not domain:
        flash('Domain cannot be empty')
        return redirect(url_for('domains'))
    if add_domain(domain, flask_session['user_id']):
        flash(f'Domain {domain} added')
    else:
        flash('Domain already exists or invalid')
    return redirect(url_for('domains'))

@app.route('/domains/delete/<int:domain_id>', methods=['POST'])
@login_required
@active_required
def delete_domain_route(domain_id):
    delete_domain(domain_id, flask_session['user_id'])
    flash('Domain deleted')
    return redirect(url_for('domains'))

# --- Inboxes ---

@app.route('/inboxes')
@login_required
def inboxes():
    user_inboxes = get_inboxes(flask_session['user_id'])
    user_domains = get_domains(flask_session['user_id'])
    return render_template('inboxes.html', inboxes=user_inboxes, domains=user_domains,
                           full_email=full_email, is_active=flask_session.get('is_active'))

@app.route('/inboxes/create', methods=['POST'])
@login_required
@active_required
def create_inbox_route():
    domain_id = request.form.get('domain_id')
    custom_address = request.form.get('address', '').strip().lower()
    days = int(request.form.get('days', 30))
    if not domain_id:
        flash('Select a domain')
        return redirect(url_for('inboxes'))
    address = custom_address or gen_random_address()
    inbox = create_inbox(address, domain_id, flask_session['user_id'], days)
    if inbox:
        public_url = url_for('public_inbox', token=inbox['public_token'], _external=True)
        flash(f'Inbox created: {address}@{inbox["domain"]} | Public: {public_url}')
    else:
        flash('Inbox address already exists for this domain')
    return redirect(url_for('inboxes'))

@app.route('/inboxes/delete/<int:inbox_id>', methods=['POST'])
@login_required
@active_required
def delete_inbox_route(inbox_id):
    delete_inbox(inbox_id, flask_session['user_id'])
    flash('Inbox deleted')
    return redirect(url_for('inboxes'))

# --- Public Routes ---

@app.route('/p/<token>')
def public_inbox(token):
    inbox = get_inbox_by_token(token)
    if not inbox:
        return render_template('public_error.html', msg='Inbox not found or expired.'), 404
    page = request.args.get('page', 1, type=int)
    emails, total = get_emails_for_inbox_public(inbox['id'], page)
    return render_template('public_emails.html', inbox=inbox, emails=emails,
                           page=page, total=total)

@app.route('/p/<token>/email/<int:email_id>')
def public_view_email(token, email_id):
    inbox = get_inbox_by_token(token)
    if not inbox:
        return render_template('public_error.html', msg='Inbox not found or expired.'), 404
    email = get_email_public(email_id, inbox['id'])
    if not email:
        return render_template('public_error.html', msg='Email not found.'), 404
    return render_template('public_view_email.html', inbox=inbox, email=email)

# --- Emails ---

@app.route('/inbox/<int:inbox_id>')
@login_required
def inbox_emails(inbox_id):
    inbox = get_inbox_by_id(inbox_id, flask_session['user_id'])
    if not inbox:
        flash('Inbox not found')
        return redirect(url_for('inboxes'))
    page = request.args.get('page', 1, type=int)
    emails, total = get_emails_for_inbox(inbox_id, flask_session['user_id'], page)
    return render_template('emails.html', inbox=inbox, emails=emails,
                           page=page, total=total, full_email=full_email)

@app.route('/email/<int:email_id>')
@login_required
def view_email(email_id):
    email = get_email(email_id, flask_session['user_id'])
    if not email:
        flash('Email not found')
        return redirect(url_for('inboxes'))
    return render_template('view_email.html', email=email)

@app.route('/email/<int:email_id>/delete', methods=['POST'])
@login_required
def delete_email_route(email_id):
    inbox_id = request.form.get('inbox_id')
    delete_email(email_id, flask_session['user_id'])
    flash('Email deleted')
    return redirect(url_for('inbox_emails', inbox_id=inbox_id) if inbox_id else url_for('inboxes'))

# --- Cleanup ---

def cleanup_loop():
    while True:
        time.sleep(3600)
        try:
            cleanup_expired()
        except Exception as e:
            print(f'Cleanup error: {e}', flush=True)

# --- Startup (always runs) ---

init_db()
cleanup_expired()

# --- Main ---

if __name__ == '__main__':

    cleanup_thread = threading.Thread(target=cleanup_loop, daemon=True)
    cleanup_thread.start()

    smtp_host = os.environ.get('SMTP_HOST', '127.0.0.1')
    smtp_port = int(os.environ.get('SMTP_PORT', '1025'))
    web_host = os.environ.get('WEB_HOST', '127.0.0.1')
    web_port = int(os.environ.get('WEB_PORT', '5000'))

    smtp = SMTPServer(host=smtp_host, port=smtp_port)
    smtp.start()

    app.run(host=web_host, port=web_port, debug=True, use_reloader=False)
