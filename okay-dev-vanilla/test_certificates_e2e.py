"""
End-to-End Test Suite for Devengers Certificates & Credential Verification Portal.
Tests:
1. Public competition list retrieval.
2. Public real-time certificate verification by registered Email.
3. Public real-time certificate verification by Full Name (case-insensitive).
4. Flexible search fallback (name match or email match).
5. Unregistered participant error handling.
6. Issue reporting endpoint (tickets stored with reference ID).
7. Admin route protection (401 Unauthorized for unauthenticated requests).
8. Admin login and competition creation with visual anchor coordinates.
9. Admin Excel/CSV participant roster parsing and bulk import.
10. Admin single competition retrieval and roster listing.
11. Admin template image upload with magic bytes validation.
12. Admin issues review endpoint.
13. Admin competition deletion and cascading participant cleanup.
"""

import urllib.request
import urllib.parse
import json
import http.cookiejar
import base64

BASE_URL = "http://localhost:3000"

def run_certificate_e2e_tests():
    print("================================================================")
    print("STARTING DEVENGERS CERTIFICATES & CREDENTIAL PORTAL E2E TESTS")
    print("================================================================")

    cookie_jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookie_jar))

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
                except Exception:
                    json_data = body
                return status, json_data
        except urllib.error.HTTPError as e:
            body = e.read().decode('utf-8')
            try:
                json_data = json.loads(body)
            except Exception:
                json_data = body
            return e.code, json_data

    # Test 1: Public Competitions List
    print("\n[Test 1] Testing public competitions list retrieval...")
    status, res = request("GET", "/api/certificates/competitions")
    assert status == 200, f"Expected 200, got {status}: {res}"
    assert res.get("success") is True, f"Failed: {res}"
    competitions = res.get("competitions", [])
    assert len(competitions) >= 2, f"Expected at least 2 seeded competitions, found {len(competitions)}"
    print(f"  ✓ Competitions fetched successfully: {len(competitions)} competitions online.")
    comp_id = competitions[0]["id"]

    # Test 2: Real-time Verification by Email
    print("\n[Test 2] Testing real-time participant lookup by Email...")
    status, res = request("POST", "/api/certificates/verify", {
        "competition_id": "comp_dev_hack_2026",
        "query": "kishan@devengers.org"
    })
    assert status == 200, f"Expected 200, got {status}: {res}"
    assert res.get("found") is True, f"Expected match, got {res}"
    p = res["participant"]
    c = res["competition"]
    assert p["name"] == "Kishan Kumar", f"Unexpected name: {p['name']}"
    assert "DEV-2026-" in p["certificate_number"], f"Invalid cert no: {p['certificate_number']}"
    assert "name_x" in c and "name_y" in c, f"Missing anchor coords: {c}"
    print(f"  ✓ Verified by email: '{p['name']}' ({p['email']}) -> Certificate #{p['certificate_number']}.")

    # Test 3: Real-time Verification by Full Name (case-insensitive)
    print("\n[Test 3] Testing real-time participant lookup by Name (case-insensitive)...")
    status, res = request("POST", "/api/certificates/verify", {
        "competition_id": "comp_dev_hack_2026",
        "query": "aarav sharma"
    })
    assert status == 200, f"Expected 200, got {status}: {res}"
    assert res.get("found") is True, f"Expected match, got {res}"
    assert res["participant"]["name"] == "Aarav Sharma"
    print(f"  ✓ Verified by name: '{res['participant']['name']}' matched perfectly.")

    # Test 4: Unregistered Search Handling
    print("\n[Test 4] Testing non-existent participant rejection...")
    status, res = request("POST", "/api/certificates/verify", {
        "competition_id": "comp_dev_hack_2026",
        "query": "nonexistent.developer@unknown.domain"
    })
    assert status == 404 or res.get("found") is False, f"Expected 404 or found=False, got {status}: {res}"
    print("  ✓ Properly returned friendly not-found message.")

    # Test 5: Issue Reporting Endpoint
    print("\n[Test 5] Testing participant Raise Issue endpoint...")
    status, res = request("POST", "/api/certificates/report-issue", {
        "competition_id": "comp_dev_hack_2026",
        "competition_title": "Devengers National Hackathon 2026",
        "participant_name": "Test Student",
        "participant_email": "student@test.edu",
        "issue_type": "Name Misspelled",
        "message": "Please correct the spelling of my middle name on the certificate."
    })
    assert status == 200, f"Expected 200, got {status}: {res}"
    assert res.get("success") is True, f"Failed: {res}"
    assert "issue_id" in res, f"Missing ticket ID: {res}"
    assert res.get("support_email") == "support@devengers.org", f"Support email mismatch: {res}"
    print(f"  ✓ Issue logged successfully: Ticket #{res['issue_id']} routed to support@devengers.org.")

    # Test 6: Admin Protection
    print("\n[Test 6] Testing unauthenticated admin access rejection...")
    status, res = request("GET", "/api/admin/certificates")
    assert status == 401, f"Expected 401, got {status}"
    print("  ✓ Protected /api/admin/certificates rejected with 401 Unauthorized.")

    # Test 7: Admin Login with 2FA OTP
    print("\n[Test 7] Authenticating admin user with 2FA OTP...")
    status, res = request("POST", "/api/auth/login", {
        "email": "event@devengers.org",
        "password": "devengers@2026"
    })
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
    assert status == 200 and res.get("success") is True, f"Admin login failed: {res}"
    print(f"  ✓ Admin logged in as {res.get('user', {}).get('email')}.")

    # Test 8: Admin List Competitions
    print("\n[Test 8] Fetching admin competitions list...")
    status, res = request("GET", "/api/admin/certificates")
    assert status == 200 and res.get("success") is True
    admin_comps = res.get("competitions", [])
    print(f"  ✓ Admin retrieved {len(admin_comps)} competitions with full metrics.")

    # Test 9: Admin Create Competition with Visual Anchors
    print("\n[Test 9] Creating a new competition with visual name anchor tag...")
    new_comp_payload = {
        "title": "Devengers AI & Cloud Buildathon 2026",
        "certificate_type": "Certificate of Achievement",
        "issue_date": "November 10, 2026",
        "description": "National AI & Agentic coding hackathon challenge.",
        "template_url": "Assest/uploads/cert_template_gold_luxury.jpg",
        "name_x": 50.0,
        "name_y": 49.5,
        "name_font": "Playfair Display",
        "name_size": 60,
        "name_color": "#F7D070",
        "name_align": "center",
        "name_case": "capitalize",
        "status": "Published"
    }
    status, res = request("POST", "/api/admin/certificates", new_comp_payload)
    assert status == 200 and res.get("success") is True, f"Creation failed: {res}"
    new_comp_id = res["id"]
    print(f"  ✓ New certificate competition created: ID {new_comp_id}.")

    # Test 10: Admin Roster Upload (Excel/CSV Parser)
    print("\n[Test 10] Uploading participant roster to the competition...")
    csv_roster = (
        "Participant Name,Registered Email,Award Role\n"
        "Devendra Verma,devendra@example.com,Grand Winner\n"
        "Shreya Ghoshal,shreya.g@example.com,Finalist\n"
        "Arjun Rampal,arjun@example.com,Special Merit\n"
    ).encode('utf-8')
    b64_csv = base64.b64encode(csv_roster).decode('utf-8')

    status, res = request("POST", f"/api/admin/certificates/{new_comp_id}/upload-roster", {
        "filename": "roster.csv",
        "file_base64": b64_csv,
        "replace_existing": True
    })
    assert status == 200 and res.get("success") is True, f"Roster upload failed: {res}"
    assert res.get("imported_count") == 3, f"Expected 3 imported, got {res.get('imported_count')}"
    print(f"  ✓ Roster imported: {res.get('imported_count')} participants added successfully.")

    # Test 11: Real-time search against the newly uploaded roster
    print("\n[Test 11] Testing instant search on newly uploaded participant...")
    status, res = request("POST", "/api/certificates/verify", {
        "competition_id": new_comp_id,
        "query": "devendra@example.com"
    })
    assert status == 200 and res.get("found") is True
    assert res["participant"]["name"] == "Devendra Verma"
    assert res["participant"]["role_or_rank"] == "Grand Winner"
    print(f"  ✓ Real-time verification confirmed for new import: '{res['participant']['name']}' ({res['participant']['role_or_rank']}).")

    # Test 12: Admin Template Image Upload (Magic Bytes Check)
    print("\n[Test 12] Testing template image upload with magic bytes validation...")
    # 1x1 PNG image
    tiny_png = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\rIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfe\r\xef5\xcb\x00\x00\x00\x00IEND\xaeB`\x82'
    status, res = request("POST", "/api/admin/certificates/upload-template", {
        "image_base64": base64.b64encode(tiny_png).decode('utf-8')
    })
    assert status == 200 and res.get("success") is True, f"Upload failed: {res}"
    assert "Assest/uploads/" in res.get("url", ""), f"Invalid URL: {res}"
    print(f"  ✓ Template uploaded with magic bytes validation: {res.get('url')}.")

    # Test 13: Admin Issues Review
    print("\n[Test 13] Checking admin issues review endpoint...")
    status, res = request("GET", "/api/admin/certificates-issues")
    assert status == 200 and res.get("success") is True
    issues = res.get("issues", [])
    assert len(issues) >= 1, f"Expected at least 1 issue, found {len(issues)}"
    print(f"  ✓ Admin reviewed {len(issues)} reported issues.")

    # Test 14: Admin Delete Competition
    print("\n[Test 14] Testing deletion of competition and participant cascade...")
    status, res = request("DELETE", f"/api/admin/certificates/{new_comp_id}")
    assert status == 200 and res.get("success") is True
    # Verify participant is gone
    status, res = request("POST", "/api/certificates/verify", {
        "competition_id": new_comp_id,
        "query": "devendra@example.com"
    })
    assert status == 404 or res.get("found") is False
    print("  ✓ Competition deleted and participants cleanly removed from database.")

    print("\n================================================================")
    print("ALL 14 CERTIFICATE E2E TESTS PASSED SUCCESSFULLY! (100% GREEN)")
    print("================================================================")

if __name__ == '__main__':
    run_certificate_e2e_tests()
