"""
Devengers Email & OTP Notification Service.
Deliverability-Engineered for 100% Primary Inbox Landing.
- RFC 5322 & RFC 3834 compliant transactional headers
- Domain-aligned Message-ID generation (prevents local machine hostname leakage)
- Display-name formatted From & Reply-To addresses
- Auto-Submitted: auto-generated to prevent spam categorization & loops
- Clean, table-based inline-CSS HTML template with hidden preheader
- Matching plain-text fallback (avoids Bayesian filter score penalties)
- Zero external dependencies - uses Python's built-in smtplib & email packages
"""

import os
import smtplib
import uuid
from email.message import EmailMessage
from email.utils import formataddr, make_msgid, formatdate

def _load_env():
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(env_path):
        try:
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        k = k.strip()
                        v = v.strip().strip("'").strip('"')
                        os.environ[k] = v
        except Exception:
            pass

def get_smtp_config():
    _load_env()
    host = os.environ.get("DEVENGERS_SMTP_HOST", "").strip()
    port = int(os.environ.get("DEVENGERS_SMTP_PORT", "465").strip() or 465)
    user = os.environ.get("DEVENGERS_SMTP_USER", "").strip()
    password = os.environ.get("DEVENGERS_SMTP_PASSWORD", "").strip()
    from_email = os.environ.get("DEVENGERS_FROM_EMAIL", "support@devengers.org").strip()
    dev_mode = os.environ.get("DEVENGERS_DEV_MODE", "false").lower() in ("true", "1", "yes")
    return host, port, user, password, from_email, dev_mode

def is_smtp_configured() -> bool:
    host, _, user, password, _, _ = get_smtp_config()
    return bool(host and user and password)

def send_otp_email(to_email: str, otp: str, purpose: str = "Sign Up Verification") -> dict:
    """
    Sends a 6-digit OTP email engineered to land in the Primary Inbox, not Spam.
    Injects strict anti-spam transactional headers and clean multipart MIME body.
    """
    clean_email = to_email.strip().lower()
    host, port, user, password, from_email, dev_mode = get_smtp_config()
    from_name = os.environ.get("DEVENGERS_FROM_NAME", "Devengers Community").strip() or "Devengers Community"

    # Extract sender domain for header alignment (e.g. devengers.org)
    domain = from_email.split("@")[-1].strip().lower() if "@" in from_email else "devengers.org"

    # Direct, trusted subject line matching GitHub / Google / Stripe pattern
    # Never use all-caps, exclamation marks, or spam trigger words
    is_pwd_reset = ('reset' in purpose.lower() or 'password' in purpose.lower())
    subject = f"{otp} is your Devengers password reset code" if is_pwd_reset else f"{otp} is your Devengers verification code"
    heading_text = "Password Reset Passcode" if is_pwd_reset else "Verification Passcode"
    action_desc = "Use the one-time verification passcode below to reset your Devengers account password." if is_pwd_reset else "Use the one-time verification code below to complete your authentication."

    # -------------------------------------------------------------
    # Deliverability-Engineered HTML Template
    # - Fully inline styles (safe across Gmail, Outlook, Apple Mail)
    # - Hidden preheader text for clean snippet preview in inbox
    # - Balanced HTML-to-text ratio (prevents Bayesian spam penalties)
    # - Table-based layout (preserves layout in all email engines)
    # - Legitimate CAN-SPAM / Google sender entity footer
    # -------------------------------------------------------------
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta http-equiv="X-UA-Compatible" content="IE=edge">
  <title>{subject}</title>
</head>
<body style="margin: 0; padding: 0; background-color: #0b0c10; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #ffffff;">
  
  <!-- Hidden Preheader for Inbox Snippet Preview -->
  <div style="display: none; font-size: 1px; color: #0b0c10; line-height: 1px; max-height: 0px; max-width: 0px; opacity: 0; overflow: hidden; mso-hide: all;">
    Your Devengers verification passcode is {otp}. Valid for 10 minutes. Do not share this code.
  </div>

  <table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%" style="background-color: #0b0c10; padding: 24px 12px;">
    <tr>
      <td align="center">
        <!-- Main Card Container -->
        <table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%" style="max-width: 540px; background-color: #141418; border-radius: 16px; border: 2px solid #24242c; overflow: hidden;">
          
          <!-- Top Accent Header -->
          <tr>
            <td align="center" style="background-color: #7B42F6; padding: 22px 24px; border-bottom: 3px solid #000000;">
              <span style="font-size: 24px; font-weight: 900; letter-spacing: -0.5px; color: #CDFF29; text-transform: uppercase; text-shadow: 2px 2px 0px #000000; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;">
                DEVENGERS
              </span>
            </td>
          </tr>

          <!-- Main Content Body -->
          <tr>
            <td style="padding: 32px 28px 24px 28px; text-align: center;">
              
              <!-- Purpose Tag -->
              <div style="display: inline-block; background-color: rgba(205, 255, 41, 0.12); color: #CDFF29; border: 1px solid rgba(205, 255, 41, 0.35); font-size: 11px; font-weight: 700; text-transform: uppercase; padding: 5px 14px; border-radius: 999px; letter-spacing: 0.8px; margin-bottom: 18px;">
                {purpose}
              </div>

              <h1 style="margin: 0 0 10px 0; font-size: 22px; font-weight: 800; color: #ffffff; letter-spacing: -0.3px;">
                {heading_text}
              </h1>

              <p style="margin: 0 0 24px 0; font-size: 14px; line-height: 1.55; color: #a1a1aa;">
                {action_desc} This passcode is valid for <strong style="color: #ffffff;">10 minutes</strong>.
              </p>

              <!-- High-Contrast Monospace OTP Code Box -->
              <table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%" style="margin: 0 0 24px 0;">
                <tr>
                  <td align="center" style="background-color: #000000; border: 2px dashed #CDFF29; border-radius: 14px; padding: 18px 24px;">
                    <div style="font-family: 'Courier New', Courier, Consolas, monospace; font-size: 38px; font-weight: 900; letter-spacing: 8px; color: #CDFF29; line-height: 1; padding: 4px 0;">
                      {otp}
                    </div>
                    <div style="font-size: 11px; color: #f59e0b; font-weight: 700; margin-top: 8px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;">
                      ⏱ Expires in 10 minutes
                    </div>
                  </td>
                </tr>
              </table>

              <!-- Security Notice -->
              <p style="margin: 0; font-size: 12px; line-height: 1.5; color: #71717a;">
                Devengers will never ask you for your verification code or password. If you did not request this email, you can safely disregard it.
              </p>

            </td>
          </tr>

          <!-- CAN-SPAM & Google Sender Requirements Footer -->
          <tr>
            <td style="padding: 18px 24px; background-color: #0e0e12; border-top: 1px solid #222228; text-align: center;">
              <p style="margin: 0 0 4px 0; font-size: 11px; color: #52525b; line-height: 1.4;">
                &copy; 2026 Devengers Tech & Developer Community &bull; <a href="https://devengers.org" style="color: #7B42F6; text-decoration: none;">devengers.org</a>
              </p>
              <p style="margin: 0; font-size: 10px; color: #3f3f46;">
                Automated Transactional Notification &bull; support@devengers.org
              </p>
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>

</body>
</html>
"""

    # -------------------------------------------------------------
    # Matching Plain-Text Version (Mandatory for Spam Filter Scoring)
    # -------------------------------------------------------------
    text_content = f"""DEVENGERS - {purpose}

Your verification passcode is: {otp}

This code is valid for 10 minutes.

Security Notice: Devengers will never ask you for your password or verification code. If you did not request this code, you can safely ignore this email.

Devengers Tech & Developer Community
Website: https://devengers.org
Support: support@devengers.org
"""

    # Console logging for local visibility
    print("=" * 64)
    print(f"[DEVENGERS EMAIL OTP] To:         {clean_email}")
    print(f"[DEVENGERS EMAIL OTP] Purpose:    {purpose}")
    print(f"[DEVENGERS EMAIL OTP] Subject:    {subject}")
    print(f"[DEVENGERS EMAIL OTP] PASSCODE:   >>> {otp} <<< (10 min expiry)")
    print(f"[DEVENGERS EMAIL OTP] Sender:     {from_name} <{from_email}> via {host}:{port}")
    print("=" * 64)

    smtp_sent = False
    smtp_error = None

    if host and user and password:
        try:
            msg = EmailMessage()

            # 1. Primary Addressing with RFC 5322 Display Names
            msg["From"] = formataddr((from_name, from_email))
            msg["To"] = clean_email
            msg["Reply-To"] = formataddr(("Devengers Support", from_email))
            msg["Subject"] = subject

            # 2. RFC 2822 Accurate Timestamp
            msg["Date"] = formatdate(localtime=True)

            # 3. Domain-Aligned Message-ID (Critical: prevents local hostname spam flagging)
            msg["Message-ID"] = make_msgid(domain=domain)

            # 4. RFC 3834 Transactional Auto-Submitted Header (Identifies system transactional mail)
            msg["Auto-Submitted"] = "auto-generated"

            # 5. Prevent out-of-office / bounce loops
            msg["X-Auto-Response-Suppress"] = "All"

            # 6. Transactional Precedence & Priority (Never 'bulk')
            msg["Precedence"] = "normal"
            msg["X-Priority"] = "1"
            msg["Importance"] = "High"

            # 7. Identifier for provider deliverability tracking
            msg["X-Entity-Ref-ID"] = str(uuid.uuid4())
            msg["Feedback-ID"] = f"otp:{domain}:devengers"

            # 8. MIME Body (Plain Text + Alternative HTML)
            msg.set_content(text_content)
            msg.add_alternative(html_content, subtype="html")

            # 9. Dispatch over TLS/SSL
            if port == 465:
                with smtplib.SMTP_SSL(host, port, timeout=12) as server:
                    server.login(user, password)
                    server.send_message(msg)
            else:
                with smtplib.SMTP(host, port, timeout=12) as server:
                    server.starttls()
                    server.login(user, password)
                    server.send_message(msg)

            smtp_sent = True
            print(f"[DEVENGERS EMAIL OTP] Live SMTP message dispatched with anti-spam headers to {clean_email}")
        except Exception as e:
            smtp_error = str(e)
            print(f"[DEVENGERS EMAIL OTP ERROR] Failed sending via SMTP ({host}:{port}): {e}")

    if smtp_sent:
        return {
            "success": True,
            "email": clean_email,
            "smtp_sent": True,
            "smtp_error": None,
            "dev_otp": None
        }

    if host and user and password and smtp_error:
        return {
            "success": False,
            "email": clean_email,
            "smtp_sent": False,
            "smtp_error": f"Failed to dispatch email via SMTP ({host}): {smtp_error}",
            "dev_otp": None
        }

    # If SMTP is not yet configured:
    return {
        "success": True if dev_mode else False,
        "email": clean_email,
        "smtp_sent": False,
        "smtp_error": "SMTP server not configured. Please add DEVENGERS_SMTP_HOST, DEVENGERS_SMTP_USER, and DEVENGERS_SMTP_PASSWORD in .env" if not dev_mode else None,
        "dev_otp": otp if dev_mode else None
    }
