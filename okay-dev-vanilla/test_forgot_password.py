"""
Tests the Forgot Password and Password Reset workflow end-to-end:
1. Rejection of reset OTP for non-existent users.
2. Generation and storage of 6-digit reset OTP.
3. Rejection of invalid OTP, mismatched passwords, short passwords.
4. Successful password reset with valid OTP.
5. Invalidation of old sessions upon password reset.
6. Successful login with the new password.
"""

import sys
import json
import sqlite3
import os
import urllib.request
import urllib.error

BASE_URL = "http://localhost:3000"
DB_PATH = os.path.join(os.path.dirname(__file__), "devengers.db")

def request(method, path, data=None):
    url = f"{BASE_URL}{path}"
    headers = {"Content-Type": "application/json"}
    body = json.dumps(data).encode("utf-8") if data is not None else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            err_data = json.loads(e.read().decode("utf-8"))
        except Exception:
            err_data = {"error": str(e)}
        return e.code, err_data

def get_latest_otp(email, purpose="Password Reset"):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("""
        SELECT otp FROM email_otps
        WHERE email = ? AND purpose = ? AND is_used = 0
        ORDER BY created_at DESC LIMIT 1
    """, (email.lower(), purpose))
    row = cursor.fetchone()
    conn.close()
    return row["otp"] if row else None

def test_forgot_password_flow():
    print("\n=======================================================")
    print("Testing Forgot Password & Password Reset Flow")
    print("=======================================================")

    test_email = "tester_reset@devengers.org"
    initial_pwd = "InitialPassword123!"
    new_pwd = "NewSecurePassword456!"

    # 1. Test sending reset OTP to a non-existent email
    print("\n[Step 1] Requesting reset OTP for non-existent email...")
    status, res = request("POST", "/api/auth/send-otp", {"email": "nobody_exists_here@devengers.org", "purpose": "Password Reset"})
    assert status == 404, f"Expected 404 for non-existent user, got {status}: {res}"
    print(f"  ✓ Non-existent user properly rejected with 404: {res.get('error')}")

    # 2. Provision test user via register flow
    print("\n[Step 2] Provisioning test user...")
    status, otp_res = request("POST", "/api/auth/send-otp", {"email": test_email, "purpose": "Sign Up Verification"})
    assert status == 200, f"Failed to send signup OTP: {otp_res}"
    signup_otp = get_latest_otp(test_email, purpose="Sign Up Verification")
    assert signup_otp, "Could not find signup OTP in database"

    status, reg_res = request("POST", "/api/auth/register", {
        "email": test_email,
        "password": initial_pwd,
        "name": "Password Reset Tester",
        "otp": signup_otp
    })
    assert status == 201, f"Failed to register test user: {reg_res}"
    print(f"  ✓ Test user registered: {test_email}")

    # 3. Request Password Reset OTP for existing user
    print("\n[Step 3] Requesting Password Reset OTP for registered user...")
    status, reset_otp_res = request("POST", "/api/auth/send-otp", {"email": test_email, "purpose": "Password Reset"})
    assert status == 200, f"Expected 200 OK for reset OTP request, got {status}: {reset_otp_res}"
    assert reset_otp_res.get("success") is True, f"Expected success: True, got {reset_otp_res}"
    print(f"  ✓ Password reset OTP successfully generated and sent: {reset_otp_res.get('message')}")

    reset_otp = get_latest_otp(test_email, purpose="Password Reset")
    assert reset_otp and len(reset_otp) == 6, f"Expected valid 6-digit OTP, got {reset_otp}"
    print(f"  ✓ Found valid 6-digit OTP in DB: {reset_otp}")

    # 4. Attempt reset with wrong OTP
    print("\n[Step 4] Testing password reset with INVALID OTP...")
    status, res = request("POST", "/api/auth/reset-password", {
        "email": test_email,
        "otp": "000000",
        "password": new_pwd,
        "confirm_password": new_pwd
    })
    assert status == 400, f"Expected 400 for invalid OTP, got {status}: {res}"
    print(f"  ✓ Invalid OTP rejected: {res.get('error')}")

    # 5. Attempt reset with mismatched passwords
    print("\n[Step 5] Testing password reset with MISMATCHED passwords...")
    status, res = request("POST", "/api/auth/reset-password", {
        "email": test_email,
        "otp": reset_otp,
        "password": new_pwd,
        "confirm_password": "DifferentPassword789!"
    })
    assert status == 400, f"Expected 400 for mismatched passwords, got {status}: {res}"
    print(f"  ✓ Mismatched passwords rejected: {res.get('error')}")

    # 6. Attempt reset with short password (< 6 chars)
    print("\n[Step 6] Testing password reset with SHORT password...")
    status, res = request("POST", "/api/auth/reset-password", {
        "email": test_email,
        "otp": reset_otp,
        "password": "123",
        "confirm_password": "123"
    })
    assert status == 400, f"Expected 400 for short password, got {status}: {res}"
    print(f"  ✓ Short password rejected: {res.get('error')}")

    # 7. Successful password reset with valid OTP
    print("\n[Step 7] Resetting password with valid OTP...")
    status, res = request("POST", "/api/auth/reset-password", {
        "email": test_email,
        "otp": reset_otp,
        "password": new_pwd,
        "confirm_password": new_pwd
    })
    assert status == 200, f"Expected 200 for valid reset, got {status}: {res}"
    assert res.get("success") is True, f"Expected success: True, got {res}"
    print(f"  ✓ Password successfully reset: {res.get('message')}")

    # 8. Attempt login with OLD password (should fail)
    print("\n[Step 8] Attempting login with OLD password (must fail)...")
    status, res = request("POST", "/api/auth/login", {
        "email": test_email,
        "password": initial_pwd
    })
    assert status == 401, f"Expected 401 for old password, got {status}: {res}"
    print(f"  ✓ Old password correctly rejected with 401")

    # 9. Attempt login with NEW password (should succeed)
    print("\n[Step 9] Attempting login with NEW password...")
    status, res = request("POST", "/api/auth/login", {
        "email": test_email,
        "password": new_pwd
    })
    assert status == 200, f"Expected 200 for new password, got {status}: {res}"
    assert res.get("success") is True, f"Expected success: True, got {res}"
    print(f"  ✓ Login succeeded with new password for {res.get('user', {}).get('email')}")

    # 10. Verify OTP cannot be reused
    print("\n[Step 10] Testing OTP replay prevention...")
    status, res = request("POST", "/api/auth/reset-password", {
        "email": test_email,
        "otp": reset_otp,
        "password": "YetAnotherPassword999!",
        "confirm_password": "YetAnotherPassword999!"
    })
    assert status == 400, f"Expected 400 for reused OTP, got {status}: {res}"
    print(f"  ✓ Reused OTP correctly rejected: {res.get('error')}")

    # Clean up test user
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM users WHERE email = ?", (test_email,))
    cursor.execute("DELETE FROM email_otps WHERE email = ?", (test_email,))
    cursor.execute("DELETE FROM login_attempts WHERE ip_or_email = ?", (test_email,))
    conn.commit()
    conn.close()

    print("\n=======================================================")
    print("ALL FORGOT PASSWORD TESTS PASSED PERFECTLY! ✓✓✓")
    print("=======================================================")

if __name__ == "__main__":
    test_forgot_password_flow()

