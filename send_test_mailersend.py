import argparse
import sys
from typing import Optional

from api_gateway.config import get_settings
from api_gateway.services.email.mailersend_provider import MailerSendProvider


def main():
    parser = argparse.ArgumentParser(description="Send a test email via MailerSend")
    parser.add_argument("--to", required=True, help="Recipient email address")
    parser.add_argument("--subject", default="Noyco test email", help="Email subject")
    parser.add_argument("--text", default="This is a test email from Noyco via MailerSend.", help="Plain text content")
    parser.add_argument("--html", default="<p>This is a <strong>test</strong> email from Noyco via MailerSend.</p>", help="HTML content")
    parser.add_argument("--from-email", dest="from_email", default=None, help="Override From email (optional)")
    parser.add_argument("--from-name", dest="from_name", default=None, help="Override From name (optional)")
    args = parser.parse_args()

    settings = get_settings()

    api_key = getattr(settings, "MAILERSEND_API_KEY", None)
    default_from = args.from_email or getattr(settings, "MAILERSEND_FROM", None) or getattr(settings, "EMAIL_FROM", None)
    default_from_name = args.from_name or getattr(settings, "MAILERSEND_FROM_NAME", None) or getattr(settings, "EMAIL_FROM_NAME", None)

    provider = MailerSendProvider(
        api_key=api_key,
        default_from=default_from,
        default_from_name=default_from_name,
    )

    print("Using From:", default_from, f"({default_from_name})")
    result = provider.send_email(
        to=args.to,
        subject=args.subject,
        html=args.html,
        text=args.text,
    )

    if result.ok:
        print("Email sent via MailerSend ✅")
        if result.message_id:
            print("Message-ID:", result.message_id)
        sys.exit(0)
    else:
        print("Failed to send email via MailerSend ❌")
        print("Error:", result.error)
        sys.exit(1)


if __name__ == "__main__":
    main()
