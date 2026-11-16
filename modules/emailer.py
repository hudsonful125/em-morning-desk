"""
modules/emailer.py: emails you the morning brief, for free, through your Gmail account.

One-time setup (about 3 minutes):
  1. Your Google account needs 2-Step Verification turned on.
  2. Go to https://myaccount.google.com/apppasswords, type a name like "EM desk",
     and click Create. Google shows a 16-letter "app password". Copy it.
  3. Add these lines to your .env file:
        EMAIL_ADDRESS=you@gmail.com
        EMAIL_APP_PASSWORD=abcdefghijklmnop      (the 16 letters, no spaces)
        EMAIL_TO=you@gmail.com                   (optional: where to send it; default is yourself)

The app password only lets this program send mail. You can delete it on the same page any time.
If these lines are missing, the scheduled job simply skips the email.
"""

import os
import smtplib
from email.message import EmailMessage

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 465  # Gmail's encrypted (SSL) port


def email_settings():
    """Read the email settings from the environment (.env). Returns None if not set up."""
    address = os.getenv("EMAIL_ADDRESS")
    password = os.getenv("EMAIL_APP_PASSWORD")
    if not address or not password:
        return None
    return {"address": address, "password": password.replace(" ", ""),
            "to": os.getenv("EMAIL_TO") or address}


def build_message(subject, body, sender, to):
    """Make the email itself (pure function, easy to test)."""
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = sender
    message["To"] = to
    message.set_content(body)
    return message


def send_email(subject, body, settings=None, smtp_class=smtplib.SMTP_SSL):
    """
    Send an email. Returns an error message, or None if it worked.
    `smtp_class` can be swapped out by tests so nothing is really sent.
    """
    settings = settings or email_settings()
    if not settings:
        return "Email isn't set up (no EMAIL_ADDRESS / EMAIL_APP_PASSWORD in .env), so no email was sent."
    message = build_message(subject, body, settings["address"], settings["to"])
    try:
        with smtp_class(SMTP_HOST, SMTP_PORT, timeout=30) as server:
            server.login(settings["address"], settings["password"])
            server.send_message(message)
    except smtplib.SMTPAuthenticationError:
        return ("Gmail rejected the login. Check EMAIL_ADDRESS and EMAIL_APP_PASSWORD in .env "
                "(it must be an app password, not your normal password).")
    except (smtplib.SMTPException, OSError) as error:
        return f"Couldn't send the email: {error}"
    return None
