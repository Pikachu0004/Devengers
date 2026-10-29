"""
Devengers Email & OTP Notification Service.
Deliverability-Engineered for 100% Primary Inbox Landing.

Supported Dispatch Channels (Automatic Priority Cascade over HTTPS Port 443):
1. Zoho ZeptoMail REST API (Dedicated transactional API by Zoho - perfect for devengers.org, 10k free trial, no daily cap)
2. Resend HTTP REST API (HTTPS port 443 - zero block on Render / Vercel cloud)
3. Brevo HTTP REST API (HTTPS port 443 - 300 free emails/day)
4. Standard SMTP over TLS/SSL (Fallback for localhost or unblocked hosts)
5. Dev Mode bypass (Instant OTP generation for local/staging testing)

Zero external dependencies - uses Python standard library.
"""

import os
import smtplib
import uuid
import json
import urllib.request
import urllib.error
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
    _load_env()
    zepto_token = os.environ.get("ZEPTOMAIL_TOKEN", "").strip() or os.environ.get("DEVENGERS_ZEPTOMAIL_TOKEN", "").strip()
    resend_key = os.environ.get("RESEND_API_KEY", "").strip() or os.environ.get("DEVENGERS_RESEND_API_KEY", "").strip()
    brevo_key = os.environ.get("BREVO_API_KEY", "").strip() or os.environ.get("DEVENGERS_BREVO_API_KEY", "").strip()
    if zepto_token or resend_key or brevo_key:
        return True
    host, _, user, password, _, _ = get_smtp_config()
    return bool(host and user and password)

def _send_via_zeptomail(token: str, from_name: str, from_email: str, to_addr: str, subject: str, html_body: str, text_body: str, region: str = "in") -> dict:
    """Dispatches transactional email via Zoho ZeptoMail HTTPS REST API (Port 443 - zero cloud blocks)."""
    region = (region or "in").strip().lower()
    if region in ("com", "us"):
        url = "https://api.zeptomail.com/v1.1/email"
    elif region in ("eu", "europe"):
        url = "https://api.zeptomail.eu/v1.1/email"
    else:
        url = "https://api.zeptomail.in/v1.1/email"

    auth_header = token if token.startswith("Zoho-enczapikey ") else f"Zoho-enczapikey {token}"

    payload = {
        "from": {
            "address": from_email,
            "name": from_name
        },
        "to": [
            {
                "email_address": {
                    "address": to_addr,
                    "name": to_addr.split("@")[0]
                }
            }
        ],
        "subject": subject,
        "htmlbody": html_body,
        "textbody": text_body
    }

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Authorization": auth_header,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "DevengersPlatform/1.0"
        },
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=12) as resp:
        body = resp.read().decode("utf-8")
        return json.loads(body) if body else {"success": True}

def _send_via_resend(api_key: str, from_addr: str, to_addr: str, subject: str, html_body: str, text_body: str) -> dict:
    """Dispatches email via Resend HTTPS REST API (Port 443 - bypasses Render SMTP block)."""
    url = "https://api.resend.com/emails"
    payload = {
        "from": from_addr,
        "to": [to_addr],
        "subject": subject,
        "html": html_body,
        "text": text_body
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "DevengersPlatform/1.0"
        },
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=12) as resp:
        body = resp.read().decode("utf-8")
        return json.loads(body) if body else {"success": True}

def _send_via_brevo(api_key: str, from_name: str, from_email: str, to_addr: str, subject: str, html_body: str, text_body: str) -> dict:
    """Dispatches email via Brevo HTTPS REST API (Port 443 - bypasses Render SMTP block)."""
    url = "https://api.brevo.com/v3/smtp/email"
    payload = {
        "sender": {"name": from_name, "email": from_email},
        "to": [{"email": to_addr}],
        "subject": subject,
        "htmlContent": html_body,
        "textContent": text_body
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "api-key": api_key,
            "Content-Type": "application/json",
            "User-Agent": "DevengersPlatform/1.0"
        },
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=12) as resp:
        body = resp.read().decode("utf-8")
        return json.loads(body) if body else {"success": True}

def send_otp_email(to_email: str, otp: str, purpose: str = "Sign Up Verification") -> dict:
    """
    Sends a 6-digit OTP email engineered to land in the Primary Inbox, not Spam.
    Tries HTTP REST APIs first (ZeptoMail, Resend, Brevo) to bypass cloud SMTP blocks,
    then falls back to SMTP, and finally to Dev Mode if enabled.
    """
    _load_env()
    clean_email = to_email.strip().lower()
    host, port, user, password, from_email, dev_mode = get_smtp_config()
    from_name = os.environ.get("DEVENGERS_FROM_NAME", "Devengers Community").strip() or "Devengers Community"

    zepto_token = os.environ.get("ZEPTOMAIL_TOKEN", "").strip() or os.environ.get("DEVENGERS_ZEPTOMAIL_TOKEN", "").strip()
    zepto_region = os.environ.get("ZEPTOMAIL_REGION", "").strip() or os.environ.get("DEVENGERS_ZEPTOMAIL_REGION", "in").strip()

    resend_key = os.environ.get("RESEND_API_KEY", "").strip() or os.environ.get("DEVENGERS_RESEND_API_KEY", "").strip()
    brevo_key = os.environ.get("BREVO_API_KEY", "").strip() or os.environ.get("DEVENGERS_BREVO_API_KEY", "").strip()

    domain = from_email.split("@")[-1].strip().lower() if "@" in from_email else "devengers.org"

    is_pwd_reset = ('reset' in purpose.lower() or 'password' in purpose.lower())
    subject = f"{otp} is your Devengers password reset code" if is_pwd_reset else f"{otp} is your Devengers verification code"
    heading_text = "Password Reset Passcode" if is_pwd_reset else "Verification Passcode"
    action_desc = "Use the one-time verification passcode below to reset your Devengers account password." if is_pwd_reset else "Use the one-time verification code below to complete your authentication."

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta http-equiv="X-UA-Compatible" content="IE=edge">
  <title>{subject}</title>
</head>
<body style="margin: 0; padding: 0; background-color: #0b0c10; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #ffffff;">
  
  <div style="display: none; font-size: 1px; color: #0b0c10; line-height: 1px; max-height: 0px; max-width: 0px; opacity: 0; overflow: hidden; mso-hide: all;">
    Your Devengers verification passcode is {otp}. Valid for 10 minutes. Do not share this code.
  </div>

  <table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%" style="background-color: #0b0c10; padding: 24px 12px;">
    <tr>
      <td align="center">
        <table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%" style="max-width: 540px; background-color: #141418; border-radius: 16px; border: 2px solid #24242c; overflow: hidden;">
          
          <tr>
            <td align="center" style="background-color: #7B42F6; padding: 22px 24px; border-bottom: 3px solid #000000;">
              <span style="font-size: 24px; font-weight: 900; letter-spacing: -0.5px; color: #CDFF29; text-transform: uppercase; text-shadow: 2px 2px 0px #000000; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;">
                DEVENGERS
              </span>
            </td>
          </tr>

          <tr>
            <td style="padding: 32px 28px 24px 28px; text-align: center;">
              
              <div style="display: inline-block; background-color: rgba(205, 255, 41, 0.12); color: #CDFF29; border: 1px solid rgba(205, 255, 41, 0.35); font-size: 11px; font-weight: 700; text-transform: uppercase; padding: 5px 14px; border-radius: 999px; letter-spacing: 0.8px; margin-bottom: 18px;">
                {purpose}
              </div>

              <h1 style="margin: 0 0 10px 0; font-size: 22px; font-weight: 800; color: #ffffff; letter-spacing: -0.3px;">
                {heading_text}
              </h1>

              <p style="margin: 0 0 24px 0; font-size: 14px; line-height: 1.55; color: #a1a1aa;">
                {action_desc} This passcode is valid for <strong style="color: #ffffff;">10 minutes</strong>.
              </p>

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

              <p style="margin: 0; font-size: 12px; line-height: 1.5; color: #71717a;">
                Devengers will never ask you for your verification code or password. If you did not request this email, you can safely disregard it.
              </p>

            </td>
          </tr>

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

    text_content = f"""DEVENGERS - {purpose}

Your verification passcode is: {otp}

This code is valid for 10 minutes.

Security Notice: Devengers will never ask you for your password or verification code. If you did not request this code, you can safely ignore this email.

Devengers Tech & Developer Community
Website: https://devengers.org
Support: support@devengers.org
"""

    print("=" * 64)
    print(f"[DEVENGERS EMAIL OTP] To:         {clean_email}")
    print(f"[DEVENGERS EMAIL OTP] Purpose:    {purpose}")
    print(f"[DEVENGERS EMAIL OTP] Subject:    {subject}")
    print(f"[DEVENGERS EMAIL OTP] PASSCODE:   >>> {otp} <<< (10 min expiry)")
    print("=" * 64)

    # -------------------------------------------------------------
    # 1. Primary Enterprise Channel: Zoho ZeptoMail REST API (Port 443)
    # -------------------------------------------------------------
    if zepto_token:
        try:
            _send_via_zeptomail(zepto_token, from_name, from_email, clean_email, subject, html_content, text_content, region=zepto_region)
            print(f"[DEVENGERS EMAIL OTP] Successfully dispatched via Zoho ZeptoMail API to {clean_email}")
            return {
                "success": True,
                "email": clean_email,
                "provider": "zeptomail",
                "smtp_sent": True,
                "smtp_error": None,
                "dev_otp": None
            }
        except Exception as e:
            err_msg = str(e)
            print(f"[DEVENGERS EMAIL ZEPTOMAIL ERROR] Failed via ZeptoMail API: {e}")
            if hasattr(e, "read"):
                try:
                    err_detail = e.read().decode("utf-8")
                    print(f"[DEVENGERS EMAIL ZEPTOMAIL DETAIL] {err_detail}")
                except Exception:
                    pass

    # -------------------------------------------------------------
    # 2. Resend HTTPS REST API (Port 443)
    # -------------------------------------------------------------
    if resend_key:
        try:
            resend_from = os.environ.get("RESEND_FROM", "").strip() or f"{from_name} <{from_email}>"
            _send_via_resend(resend_key, resend_from, clean_email, subject, html_content, text_content)
            print(f"[DEVENGERS EMAIL OTP] Successfully dispatched via Resend API to {clean_email}")
            return {
                "success": True,
                "email": clean_email,
                "provider": "resend",
                "smtp_sent": True,
                "smtp_error": None,
                "dev_otp": None
            }
        except Exception as e:
            err_msg = str(e)
            print(f"[DEVENGERS EMAIL RESEND ERROR] Failed via Resend API: {e}")
            if hasattr(e, "read"):
                try:
                    err_detail = e.read().decode("utf-8")
                    print(f"[DEVENGERS EMAIL RESEND DETAIL] {err_detail}")
                except Exception:
                    pass

    # -------------------------------------------------------------
    # 3. Brevo HTTPS REST API (Port 443)
    # -------------------------------------------------------------
    if brevo_key:
        try:
            _send_via_brevo(brevo_key, from_name, from_email, clean_email, subject, html_content, text_content)
            print(f"[DEVENGERS EMAIL OTP] Successfully dispatched via Brevo API to {clean_email}")
            return {
                "success": True,
                "email": clean_email,
                "provider": "brevo",
                "smtp_sent": True,
                "smtp_error": None,
                "dev_otp": None
            }
        except Exception as e:
            print(f"[DEVENGERS EMAIL BREVO ERROR] Failed via Brevo API: {e}")

    # -------------------------------------------------------------
    # 4. Standard SMTP (Localhost / unblocked servers)
    # -------------------------------------------------------------
    smtp_sent = False
    smtp_error = None

    if host and user and password:
        try:
            msg = EmailMessage()
            msg["From"] = formataddr((from_name, from_email))
            msg["To"] = clean_email
            msg["Reply-To"] = formataddr(("Devengers Support", from_email))
            msg["Subject"] = subject
            msg["Date"] = formatdate(localtime=True)
            msg["Message-ID"] = make_msgid(domain=domain)
            msg["Auto-Submitted"] = "auto-generated"
            msg["X-Auto-Response-Suppress"] = "All"
            msg["Precedence"] = "normal"
            msg["X-Priority"] = "1"
            msg["Importance"] = "High"
            msg["X-Entity-Ref-ID"] = str(uuid.uuid4())
            msg["Feedback-ID"] = f"otp:{domain}:devengers"

            msg.set_content(text_content)
            msg.add_alternative(html_content, subtype="html")

            if port == 465:
                with smtplib.SMTP_SSL(host, port, timeout=6) as server:
                    server.login(user, password)
                    server.send_message(msg)
            else:
                with smtplib.SMTP(host, port, timeout=6) as server:
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
            "provider": "smtp",
            "smtp_sent": True,
            "smtp_error": None,
            "dev_otp": None
        }

    # -------------------------------------------------------------
    # 5. Dev Mode Fallback (Instant OTP generation for testing)
    # -------------------------------------------------------------
    if dev_mode:
        print(f"[DEVENGERS DEV MODE] Returning OTP directly in response for {clean_email}: {otp}")
        return {
            "success": True,
            "email": clean_email,
            "provider": "dev_mode",
            "smtp_sent": False,
            "smtp_error": None,
            "dev_otp": otp
        }

    # If all options failed:
    return {
        "success": False,
        "email": clean_email,
        "smtp_sent": False,
        "smtp_error": (
            "Transactional email delivery is not configured for high-volume production. "
            "Please configure Zoho ZeptoMail (ZEPTOMAIL_TOKEN - 10,000 free emails, perfect for devengers.org), "
            "or RESEND_API_KEY / BREVO_API_KEY in Render environment variables."
        ),
        "dev_otp": None
    }
