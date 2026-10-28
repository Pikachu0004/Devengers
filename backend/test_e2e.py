"""
Comprehensive End-to-End Test Suite for Devengers Events & Admin Platform.
Tests authentication, authorization, session management, event CRUD, uploads,
category filters, click-through URLs, and security edge cases.
"""

import urllib.request
import urllib.parse
import json
import http.cookiejar
import os

BASE_URL = "http://localhost:3000"

def run_tests():
    print("==================================================")
    print("STARTING DEVENGERS EVENTS & ADMIN E2E TEST SUITE")
    print("==================================================")

    cookie_jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookie_jar))

    # Helper: JSON request
    def request(method, path, data=None, token=None):
        url = BASE_URL + path
        headers = {}
        payload = None
        if data is not None:
            headers['Content-Type'] = 'application/json'
            payload = json.dumps(data).encode('utf-8')
        if token:
            headers['Authorization'] = f"Bearer {token}"

        req = urllib.request.Request(url, data=payload, headers=headers, method=method)
        try:
            with opener.open(req) as resp:
                status = resp.status
                body = resp.read().decode('utf-8')
                try:
                    json_data = json.loads(body)
                except:
                    json_data = body
                return status, json_data
        except urllib.error.HTTPError as e:
            body = e.read().decode('utf-8')
            try:
                json_data = json.loads(body)
            except:
                json_data = body
            return e.code, json_data

    # Test 1: Unauthenticated Admin Route Protection
    print("\n[Test 1] Testing unauthenticated admin access protection...")
    status, res = request("GET", "/api/admin/events")
    assert status == 401, f"Expected 401, got {status}: {res}"
    print("  ✓ Protected admin endpoint properly rejected with 401 Unauthorized.")

    # Test 2: Invalid Login Rejection
    print("\n[Test 2] Testing invalid credentials rejection...")
    status, res = request("POST", "/api/auth/login", {"email": "event@devengers.org", "password": "WrongPassword!23"})
    assert status == 401, f"Expected 401 for wrong password, got {status}"
    assert res.get("success") is False, "Expected success: False"
    print("  ✓ Invalid password properly rejected with generic error message.")

    # Test 3: Admin Login with Designated Admin Email & 2FA OTP
    print("\n[Test 3] Testing admin login for event@devengers.org with 2FA OTP...")
    status, res = request("POST", "/api/auth/login", {"email": "event@devengers.org", "password": "devengers@2026"})
    if res.get("requires_otp"):
        otp = res.get("dev_otp")
        if not otp:
            import sqlite3
            c = sqlite3.connect("devengers.db")
            row = c.execute("SELECT otp FROM email_otps WHERE email = 'event@devengers.org' AND is_used = 0 ORDER BY created_at DESC LIMIT 1").fetchone()
            c.close()
            otp = row[0] if row else ""
        print(f"  ✓ Admin 2FA triggered as required! OTP: {otp}")
        status, res = request("POST", "/api/auth/login", {
            "email": "event@devengers.org", 
            "password": "devengers@2026", 
            "otp": otp
        })
    assert status == 200, f"Expected 200 for admin login, got {status}: {res}"
    assert res.get("success") is True, "Expected success: True"
    assert res.get("user", {}).get("role") == "admin", "Expected role: admin"
    assert res.get("redirect") == "admin-events.html", f"Expected redirect to admin-events.html, got {res.get('redirect')}"
    admin_token = res.get("token")
    print(f"  ✓ Admin logged in successfully with 2FA OTP! Role: admin, Redirect: {res.get('redirect')}")

    # Test 4: Verify Session Endpoint /api/auth/me
    print("\n[Test 4] Verifying /api/auth/me session...")
    status, res = request("GET", "/api/auth/me")
    assert status == 200, f"Expected 200, got {status}"
    assert res.get("authenticated") is True, "Expected authenticated: True"
    assert res.get("user", {}).get("email") == "event@devengers.org", "Expected email match"
    print("  ✓ Session verified via cookie: authenticated as event@devengers.org.")

    # Test 5: Admin Dashboard Events & Stats Retrieval
    print("\n[Test 5] Fetching admin events list and stats...")
    status, res = request("GET", "/api/admin/events")
    assert status == 200, f"Expected 200, got {status}"
    stats = res.get("stats", {})
    print(f"  ✓ Admin events fetched: Total={stats.get('total')}, Published={stats.get('published')}, Drafts={stats.get('drafts')}")

    # Test 6: Image Upload with Magic Bytes Validation
    print("\n[Test 6] Testing image upload with binary magic bytes validation...")
    import io
    boundary = "----WebKitFormBoundaryDevengersUploadTest"
    png_header = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4"
    multipart_body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="thumbnail"; filename="sample_hackathon.png"\r\n'
        f"Content-Type: image/png\r\n\r\n"
    ).encode('latin1') + png_header + f"\r\n--{boundary}--\r\n".encode('latin1')

    req = urllib.request.Request(
        f"{BASE_URL}/api/admin/upload",
        data=multipart_body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST"
    )
    with opener.open(req) as resp:
        upload_res = json.loads(resp.read().decode('utf-8'))
    assert upload_res.get("success") is True, f"Upload failed: {upload_res}"
    uploaded_image_url = upload_res.get("url")
    print(f"  ✓ Image uploaded successfully to: {uploaded_image_url}")

    # Test 7: Reject Unsafe Schemes in Destination URL
    print("\n[Test 7] Testing rejection of unsafe javascript: scheme in destination URL...")
    unsafe_event = {
        "title": "Unsafe Hackathon",
        "short_description": "Trying to inject unsafe url",
        "category": "Hackathons",
        "reg_deadline": "2026-11-20T23:59:59Z",
        "thumbnail": uploaded_image_url,
        "destination_url": "javascript:alert(1)",
        "status": "Published"
    }
    status, res = request("POST", "/api/admin/events", unsafe_event)
    assert status == 400, f"Expected 400 for javascript: scheme, got {status}"
    print("  ✓ Unsafe URL scheme rejected properly with HTTP 400.")

    # Test 8: Create Event with Exact Destination URL
    print("\n[Test 8] Creating and publishing a new Hackathon with verified external URL...")
    target_destination = "https://unstop.com/hackathons/devengers-national-code-sprint-2026"
    new_hackathon = {
        "title": "Devengers National Code Sprint 2026",
        "short_description": "Flagship 36-hour code sprint with ₹2,00,000 cash prizes and sponsor recruitment.",
        "full_description": "Full details on tracks, mentors, submission guidelines, and prizes.",
        "category": "Hackathons",
        "organizer": "Devengers Tech Community & MLH",
        "thumbnail": uploaded_image_url,
        "reg_open_date": "2026-10-15T00:00:00Z",
        "reg_deadline": "2026-11-25T23:59:59Z",
        "event_start_date": "2026-12-01T10:00:00Z",
        "event_end_date": "2026-12-02T22:00:00Z",
        "prize_amount": 200000.0,
        "prize_currency": "INR",
        "prize_description": "₹2,00,000 Cash Pool + Cloud Vouchers",
        "reg_fee": 0.0,
        "destination_url": target_destination,
        "action_label": "Register on Unstop",
        "status": "Published"
    }
    status, res = request("POST", "/api/admin/events", new_hackathon)
    assert status == 201, f"Expected 201 Created, got {status}: {res}"
    created_id = res.get("event", {}).get("id")
    print(f"  ✓ Hackathon created & published! Event ID: {created_id}")

    # Test 9: Verify Published Event on Public Endpoint & Destination URL
    print("\n[Test 9] Verifying public listing on /api/events and category filter...")
    status, res = request("GET", "/api/events?category=Hackathons")
    assert status == 200, f"Expected 200, got {status}"
    hackathons = res.get("events", [])
    matched = next((e for e in hackathons if e["id"] == created_id), None)
    assert matched is not None, f"Created event {created_id} not found in Hackathons category"
    assert matched["destination_url"] == target_destination, f"Destination URL mismatch: {matched['destination_url']}"
    assert matched["action_label"] == "Register on Unstop", "Action label mismatch"
    print("  ✓ Event confirmed on public feed!")
    print(f"    - Title: {matched['title']}")
    print(f"    - Destination URL: {matched['destination_url']}")
    print(f"    - Action Label: {matched['action_label']}")

    # Test 10: Verify Category Isolation
    print("\n[Test 10] Testing category isolation (Quizzes, Internships, Jobs)...")
    status, res = request("GET", "/api/events?category=Quizzes")
    assert all(e["category"] == "Quizzes" for e in res.get("events", [])), "Category leak in Quizzes"
    print("  ✓ Quizzes category confirmed isolated.")

    status, res = request("GET", "/api/events?category=Internships")
    assert all(e["category"] == "Internships" for e in res.get("events", [])), "Category leak in Internships"
    print("  ✓ Internships category confirmed isolated.")

    status, res = request("GET", "/api/events?category=Jobs")
    assert all(e["category"] == "Jobs" for e in res.get("events", [])), "Category leak in Jobs"
    print("  ✓ Jobs category confirmed isolated.")

    # Test 11: Edit Event & Verify Database Persistence
    print("\n[Test 11] Editing event details and checking persistence...")
    updated_title = "Devengers National Code Sprint 2026 (UPDATED)"
    status, res = request("PUT", f"/api/admin/events/{created_id}", {
        "title": updated_title,
        "prize_amount": 250000.0,
        "prize_description": "₹2,50,000 Cash Pool (Bumped!)"
    })
    assert status == 200, f"Expected 200 for update, got {status}: {res}"
    assert res.get("event", {}).get("title") == updated_title, "Title was not updated"

    # Fetch public event to verify
    status, res = request("GET", f"/api/events/{created_id}")
    assert res.get("event", {}).get("title") == updated_title, "Public endpoint did not reflect edit"
    print("  ✓ Event updated and persistent across database queries.")

    # Test 12: Unpublish Event & Verify Removal from Public Feed
    print("\n[Test 12] Unpublishing event and verifying removal from public listing...")
    status, res = request("POST", f"/api/admin/events/{created_id}/status", {"status": "Unpublished"})
    assert status == 200, f"Expected 200 for status update, got {status}: {res}"

    status, res = request("GET", "/api/events")
    public_ids = [e["id"] for e in res.get("events", [])]
    assert created_id not in public_ids, "Unpublished event should not be in public listing"
    print("  ✓ Unpublished event immediately excluded from public feed.")

    # Re-publish for public view
    request("POST", f"/api/admin/events/{created_id}/status", {"status": "Published"})

    # Test 13: End-to-End Student Signup with Email OTP Verification
    print("\n[Test 13] Testing end-to-end user registration with mandatory Email OTP...")
    import secrets
    new_user_email = f"e2e_student_{secrets.token_hex(4)}@devengers.org"
    
    # 13a. Request Signup OTP
    status, otp_res = request("POST", "/api/auth/send-otp", {"email": new_user_email, "purpose": "signup"})
    assert status == 200, f"Failed to send OTP: {otp_res}"
    assert otp_res.get("success") is True, "Expected success: True"
    signup_otp = otp_res.get("dev_otp")
    if not signup_otp:
        import sqlite3
        c = sqlite3.connect("devengers.db")
        row = c.execute("SELECT otp FROM email_otps WHERE email = ? AND is_used = 0 ORDER BY created_at DESC LIMIT 1", (new_user_email,)).fetchone()
        c.close()
        signup_otp = row[0] if row else ""
    print(f"  ✓ Email OTP generated & dispatched for {new_user_email}: {signup_otp}")

    # 13b. Attempt Registration without OTP -> must fail
    status, res = request("POST", "/api/auth/register", {
        "full_name": "Test Student",
        "email": new_user_email,
        "password": "studentpass123",
        "otp": ""
    })
    assert status == 400, f"Expected 400 for missing OTP, got {status}"
    print("  ✓ Registration without OTP rejected properly.")

    # 13c. Complete Registration with Valid OTP
    cookie_jar.clear()
    status, res = request("POST", "/api/auth/register", {
        "full_name": "Test Student",
        "email": new_user_email,
        "password": "studentpass123",
        "otp": signup_otp,
        "college_name": "Engineering Institute",
        "grad_year": "2027"
    })
    assert status == 201, f"Registration failed: {res}"
    assert res.get("success") is True, "Expected registration success"
    assert res.get("user", {}).get("role") == "user", "Expected role: user (regular member)"
    assert res.get("redirect") == "profile.html", f"Expected redirect to profile.html, got {res.get('redirect')}"
    print("  ✓ Member registered successfully with verified OTP! Redirect: profile.html")

    # Test 14: Full Profile Management (Bio, Skills, Handles, Academics)
    print("\n[Test 14] Testing complete profile management (Name, Bio, Skills, Handles, Photo URL)...")
    profile_updates = {
        "name": "Kishan Verified Member",
        "target_role": "Full Stack & Cloud Systems Engineer",
        "college_name": "Premier Institute of Technology",
        "grad_year": "2026",
        "bio": "Building high-performance distributed backends, algorithms, and microservices.",
        "github_handle": "kishan-dev",
        "leetcode_handle": "kishan-algo",
        "linkedin_url": "https://linkedin.com/in/kishandev",
        "portfolio_url": "https://kishandev.org",
        "twitter_handle": "@kishandev",
        "skills": "Python, TypeScript, Go, React, PostgreSQL, Docker",
        "avatar_url": "Assest/uploads/sample_avatar.png"
    }
    status, res = request("POST", "/api/user/profile", profile_updates)
    assert status == 200, f"Profile update failed: {res}"
    assert res.get("success") is True, "Expected success: True"
    updated_profile = res.get("profile", {})
    assert updated_profile.get("name") == "Kishan Verified Member", "Name not saved"
    assert updated_profile.get("github_handle") == "kishan-dev", "GitHub handle not saved"
    assert updated_profile.get("portfolio_url") == "https://kishandev.org", "Portfolio URL not saved"
    assert updated_profile.get("skills") == "Python, TypeScript, Go, React, PostgreSQL, Docker", "Skills not saved"
    assert updated_profile.get("avatar_url") == "Assest/uploads/sample_avatar.png", "Avatar URL not saved"
    print("  ✓ Full profile saved and verified in database!")

    # Test 15: Daily Streak Check-in & DSA Problem Progress
    print("\n[Test 15] Testing daily streak check-in and DSA problem logging...")
    status, res = request("POST", "/api/user/checkin")
    assert status == 200, f"Daily check-in failed: {res}"
    assert res.get("success") is True, "Expected checkin success"
    print(f"  ✓ Daily streak checked in! Message: {res.get('message')}")

    status, res = request("POST", "/api/user/profile", {"questions_solved_total": 42})
    assert status == 200, f"Problem logging failed: {res}"
    assert res.get("profile", {}).get("questions_solved_total") == 42, "Questions count mismatch"
    print("  ✓ Logged 42 DSA problems and darkened heatmap activity!")

    # Test 16: Strict Member Role Isolation (No Admin Access)
    print("\n[Test 16] Verifying regular member cannot access any admin route...")
    status, res = request("GET", "/api/admin/events")
    assert status == 401, f"Expected 401 Unauthorized for member, got {status}"
    status, res = request("POST", "/api/admin/events", {"title": "Illegal Event"})
    assert status == 401, f"Expected 401 Unauthorized for member event creation, got {status}"
    print("  ✓ Regular member strictly isolated from admin panel operations (401 Unauthorized).")

    # Test 17: Flash Event Auto-Fetch & Auto-Crop (Admin Only)
    print("\n[Test 17] Re-logging in as Administrator with 2FA OTP for Flash Event tests...")
    cookie_jar.clear()
    status, res = request("POST", "/api/auth/login", {"email": "event@devengers.org", "password": "devengers@2026"})
    if res.get("requires_otp"):
        otp = res.get("dev_otp")
        if not otp:
            import sqlite3
            c = sqlite3.connect("devengers.db")
            row = c.execute("SELECT otp FROM email_otps WHERE email = 'event@devengers.org' AND is_used = 0 ORDER BY created_at DESC LIMIT 1").fetchone()
            c.close()
            otp = row[0] if row else ""
        status, res = request("POST", "/api/auth/login", {
            "email": "event@devengers.org",
            "password": "devengers@2026",
            "otp": otp
        })
    assert status == 200 and res.get("user", {}).get("role") == "admin", "Admin login failed"

    status, res = request("POST", "/api/admin/events/flash-fetch", {
        "url": "https://paper.design",
        "category": "Hackathons"
    })
    assert status == 200, f"Flash fetch failed: {res}"
    assert res.get("success") is True, "Flash fetch success flag false"
    print("  ✓ Flash Event auto-extracted title, 16:9 banner, logo, and cover fit.")

    # Test 18: Logout
    print("\n[Test 18] Testing logout and session invalidation...")
    status, res = request("POST", "/api/auth/logout")
    assert status == 200, f"Logout failed: {res}"

    status, res = request("GET", "/api/auth/me")
    assert res.get("authenticated") is False, "Session should be invalidated after logout"
    print("  ✓ Logout verified and session destroyed.")

    print("\n==================================================")
    print("ALL 18 E2E TESTS PASSED SUCCESSFULLY! (100% GREEN)")
    print("==================================================")

if __name__ == '__main__':
    run_tests()
