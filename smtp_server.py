import socket
import email as email_parser
from email import policy
from aiosmtpd.controller import Controller
from models import get_inbox_by_email, save_email

def decode_payload(part):
    payload = part.get_payload(decode=True)
    if payload is None:
        return ''
    charset = part.get_content_charset() or 'utf-8'
    try:
        return payload.decode(charset, errors='replace')
    except (LookupError, UnicodeDecodeError):
        return payload.decode('utf-8', errors='replace')

class MailHandler:
    async def handle_DATA(self, server, session, envelope):
        mail_from = envelope.mail_from

        raw_bytes = envelope.content
        msg = email_parser.message_from_bytes(raw_bytes, policy=policy.compat32)
        subject = msg.get('Subject', '(No Subject)')

        body_text = ''
        body_html = ''

        if msg.is_multipart():
            for part in msg.walk():
                ctype = part.get_content_type()
                if ctype == 'text/plain' and not body_text:
                    body_text = decode_payload(part)
                elif ctype == 'text/html' and not body_html:
                    body_html = decode_payload(part)
        else:
            ctype = msg.get_content_type()
            if ctype == 'text/html':
                body_html = decode_payload(msg)
            else:
                body_text = decode_payload(msg)

        delivered = 0
        for rcpt in envelope.rcpt_tos:
            inbox = get_inbox_by_email(rcpt.lower())
            if inbox:
                save_email(inbox['id'], mail_from, subject, body_text, body_html)
                delivered += 1

        if delivered:
            return '250 OK'
        return '550 No such mailbox here'

class SMTPServer:
    def __init__(self, host='0.0.0.0', port=25):
        self.host = host
        self.port = port
        self.controller = None

    def start(self):
        handler = MailHandler()
        self.controller = Controller(handler, hostname=self.host, port=self.port,
                                     server_hostname=socket.getfqdn())
        self.controller.start()
        print(f'SMTP receive-only server running on {self.host}:{self.port}', flush=True)

    def stop(self):
        if self.controller:
            self.controller.stop()
