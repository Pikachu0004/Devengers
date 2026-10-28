#!/usr/bin/env python3
import sys
import email_service

recipient = sys.argv[1] if len(sys.argv) > 1 else "knishad0004@gmail.com"
print(f"Testing live SMTP dispatch to {recipient}...")

host, port, user, pwd, from_email, _ = email_service.get_smtp_config()
print(f"Host: {host}:{port}")
print(f"User: {user}")
print(f"From: {from_email}")
print(f"Password Set: {'YES' if pwd else 'NO (EMPTY)'}")

if not pwd:
    print("\n[!] Please set DEVENGERS_SMTP_PASSWORD in .env before testing.")
    sys.exit(1)

res = email_service.send_otp_email(recipient, "123456", "Live SMTP Test")
print("\nResult:", res)
