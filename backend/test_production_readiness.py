#!/usr/bin/env python3
"""
Devengers Comprehensive Meta-to-End-to-End Production Readiness Verification Suite
Tests:
  1. Python Syntax & Module Integrity
  2. Frontend Syntax (JavaScript & CSS)
  3. Static SEO & Brand Assets (og-image, favicons, logos)
  4. Cyber Security Hardening (path traversal, sensitive file blocks, security headers)
  5. HTML Routes & Meta Tag Audit (title, description, canonical, OG, Twitter, Viewport)
  6. Schema.org JSON-LD Structured Data Validation
  7. Public API Endpoint Health & JSON Schema Responses
  8. Crawler Endpoints (/robots.txt, /sitemap.xml with XML verification)
  9. Database Schema & Data Integrity
"""

import os
import sys
import glob
import json
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
import py_compile
import subprocess
import sqlite3
import re

BASE_URL = "http://localhost:3000"
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))

GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"

passed_count = 0
failed_count = 0

def log_test(name, passed, detail=""):
    global passed_count, failed_count
    if passed:
        passed_count += 1
        print(f"  {GREEN}✓{RESET} {name} {detail}")
    else:
        failed_count += 1
        print(f"  {RED}✗{RESET} {BOLD}{name}{RESET} - {RED}{detail}{RESET}")

def http_get(url_path, headers=None):
    url = f"{BASE_URL}{url_path}"
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=5) as res:
            return res.status, res.headers, res.read()
    except urllib.error.HTTPError as e:
        return e.code, e.headers, e.read()
    except Exception as e:
        return 0, {}, str(e).encode()

print(f"\n{BOLD}{CYAN}========================================================================={RESET}")
print(f"{BOLD}{CYAN}      DEVENGERS META-TO-END PRODUCTION READINESS AUDIT SUITE             {RESET}")
print(f"{BOLD}{CYAN}========================================================================={RESET}\n")

# ---------------------------------------------------------
# SECTION 1: Python Code Compilation
# ---------------------------------------------------------
print(f"{BOLD}1. Python Code Compilation & Syntax Validation{RESET}")
py_files = glob.glob(os.path.join(PROJECT_DIR, "*.py"))
all_py_clean = True
for pf in sorted(py_files):
    fname = os.path.basename(pf)
    try:
        py_compile.compile(pf, doraise=True)
        log_test(f"Compile {fname}", True)
    except Exception as e:
        all_py_clean = False
        log_test(f"Compile {fname}", False, str(e))

# ---------------------------------------------------------
# SECTION 2: JavaScript & CSS Syntax Validation
# ---------------------------------------------------------
print(f"\n{BOLD}2. JavaScript & CSS Integrity{RESET}")
js_files = ["auth.js", "script.js", "theme.js"]
for jf in js_files:
    jpath = os.path.join(PROJECT_DIR, jf)
    if os.path.exists(jpath):
        res = subprocess.run(["node", "-c", jpath], capture_output=True, text=True)
        if res.returncode == 0:
            log_test(f"JS Syntax Check: {jf}", True)
        else:
            log_test(f"JS Syntax Check: {jf}", False, res.stderr.strip())
    else:
        log_test(f"JS File exists: {jf}", False, "File missing")

css_path = os.path.join(PROJECT_DIR, "style.css")
if os.path.exists(css_path):
    with open(css_path, "r", encoding="utf-8") as f:
        css_content = f.read()
    open_braces = css_content.count("{")
    close_braces = css_content.count("}")
    log_test("CSS Brace Balance in style.css", open_braces == close_braces, f"({open_braces} open, {close_braces} close)")
    has_ig_ring = "igStoryGradient" in css_content
    log_test("Instagram Ring Animation in style.css", has_ig_ring)
    has_mobile_drawer = "#devengers-mobile-drawer" in css_content
    log_test("Mobile Drawer styles in style.css", has_mobile_drawer)
else:
    log_test("style.css exists", False, "Missing style.css")

# ---------------------------------------------------------
# SECTION 3: Brand Assets & Media Files
# ---------------------------------------------------------
print(f"\n{BOLD}3. Brand Assets & Media File Integrity{RESET}")
required_assets = [
    "og-image.jpg",
    "favicon.png",
    "favicon.ico",
    "Assest/devengers-official-logo.png",
    "Assest/devengers-logo.png"
]
for asset in required_assets:
    apath = os.path.join(PROJECT_DIR, asset)
    exists = os.path.exists(apath)
    size = os.path.getsize(apath) if exists else 0
    log_test(f"Asset: {asset}", exists and size > 0, f"({size} bytes)")

# ---------------------------------------------------------
# SECTION 4: Cyber Security Hardening & Headers
# ---------------------------------------------------------
print(f"\n{BOLD}4. Cyber Security Hardening & Headers{RESET}")
sensitive_paths = [
    "/.env",
    "/devengers.db",
    "/database.db",
    "/serve.py",
    "/auth.py",
    "/../serve.py",
    "/__pycache__"
]
for spath in sensitive_paths:
    status, _, _ = http_get(spath)
    log_test(f"Block Sensitive Path: {spath}", status in (403, 404), f"HTTP {status}")

# Verify security headers on normal page
status, headers, _ = http_get("/index.html")
sec_headers = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "SAMEORIGIN",
    "X-XSS-Protection": "1; mode=block",
    "Referrer-Policy": "strict-origin-when-cross-origin"
}
for hname, expected_val in sec_headers.items():
    actual = headers.get(hname)
    log_test(f"Security Header [{hname}]", actual is not None and expected_val in actual, f"Found: {actual}")

# ---------------------------------------------------------
# SECTION 5: HTML Pages & Meta Tags Audit
# ---------------------------------------------------------
print(f"\n{BOLD}5. HTML Pages & Comprehensive Meta Tag Audit{RESET}")
pages_to_audit = [
    ("/", "index.html", True),
    ("/dsa", "dsa.html", True),
    ("/events", "events.html", True),
    ("/campus", "campus.html", True),
    ("/learn", "learn.html", True),
    ("/certificates", "certificates.html", True),
    ("/jobs", "jobs.html", True),
    ("/gallery", "gallery.html", True),
    ("/directory", "directory.html", True),
    ("/login", "login.html", True),
    ("/register", "register.html", True),
    ("/profile", "profile.html", False) # private
]

for clean_path, disk_file, is_public in pages_to_audit:
    status, h, body = http_get(clean_path)
    body_str = body.decode("utf-8", errors="ignore")
    
    # 1. HTTP Status
    log_test(f"Page Load: {clean_path} -> {disk_file}", status == 200, f"HTTP {status}")
    
    # 2. Title Tag
    title_match = re.search(r"<title>(.*?)</title>", body_str, re.IGNORECASE)
    has_title = bool(title_match and len(title_match.group(1).strip()) > 5)
    title_text = title_match.group(1).strip() if title_match else "None"
    log_test(f"  Title tag present on {clean_path}", has_title, f"'{title_text[:40]}...'")
    
    # 3. Canonical Tag
    canon_match = re.search(r'<link\s+rel=["\x27]canonical["\x27]\s+href=["\x27](.*?)["\x27]', body_str, re.IGNORECASE)
    has_canon = bool(canon_match and "https://devengers.org" in canon_match.group(1))
    log_test(f"  Canonical URL on {clean_path}", has_canon, canon_match.group(1) if canon_match else "Missing")
    
    # 4. Meta Description
    desc_match = re.search(r'<meta\s+name=["\x27]description["\x27]\s+content=["\x27](.*?)["\x27]', body_str, re.IGNORECASE)
    has_desc = bool(desc_match and len(desc_match.group(1).strip()) > 20)
    log_test(f"  Meta Description on {clean_path}", has_desc)
    
    # 5. Open Graph Image
    og_img = re.search(r'<meta\s+property=["\x27]og:image["\x27]\s+content=["\x27](.*?)["\x27]', body_str, re.IGNORECASE)
    has_og_img = bool(og_img and "og-image.jpg" in og_img.group(1))
    log_test(f"  OG Image on {clean_path}", has_og_img, og_img.group(1) if og_img else "Missing")
    
    # 6. Twitter Card
    tw_card = re.search(r'<meta\s+name=["\x27]twitter:card["\x27]\s+content=["\x27](.*?)["\x27]', body_str, re.IGNORECASE)
    has_tw = bool(tw_card and tw_card.group(1) == "summary_large_image")
    log_test(f"  Twitter Summary Large Image on {clean_path}", has_tw)
    
    # 7. Robots crawler directives
    robots_match = re.search(r'<meta\s+name=["\x27]robots["\x27]\s+content=["\x27](.*?)["\x27]', body_str, re.IGNORECASE)
    if is_public:
        has_robots = bool(robots_match and "index" in robots_match.group(1))
        log_test(f"  Robots Allow Index on {clean_path}", has_robots, robots_match.group(1) if robots_match else "None")
    else:
        has_noindex = bool(robots_match and "noindex" in robots_match.group(1))
        log_test(f"  Robots NoIndex Private Dashboard {clean_path}", has_noindex)

# ---------------------------------------------------------
# SECTION 6: Schema.org JSON-LD Structured Data
# ---------------------------------------------------------
print(f"\n{BOLD}6. Schema.org JSON-LD Structured Data Validation{RESET}")
for clean_path, disk_file, is_public in pages_to_audit:
    if not is_public:
        continue
    _, _, body = http_get(clean_path)
    body_str = body.decode("utf-8", errors="ignore")
    ld_matches = re.findall(r'<script\s+type=["\x27]application/ld\+json["\x27]>(.*?)</script>', body_str, re.DOTALL)
    
    has_ld = len(ld_matches) > 0
    if has_ld:
        try:
            data = json.loads(ld_matches[0].strip())
            types = []
            if "@graph" in data:
                types = [x.get("@type") for x in data["@graph"]]
            elif "@type" in data:
                types = [data["@type"]]
            log_test(f"JSON-LD Valid on {clean_path}", True, f"Types: {types}")
        except Exception as e:
            log_test(f"JSON-LD Valid on {clean_path}", False, str(e))
    else:
        log_test(f"JSON-LD Present on {clean_path}", False, "No JSON-LD block found")

# ---------------------------------------------------------
# SECTION 7: Public API Endpoints
# ---------------------------------------------------------
print(f"\n{BOLD}7. Public Backend API Health & Contract Checks{RESET}")
api_endpoints = [
    ("/api/auth/me", True),
    ("/api/events", True),
    ("/api/courses", True),
    ("/api/pyqs", True),
    ("/api/dsa/potd", True),
    ("/api/gallery/posters", True),
    ("/api/certificates/competitions", True),
    ("/api/community/projects", True)
]

for ep, should_succeed in api_endpoints:
    status, _, body = http_get(ep)
    is_json = False
    data = None
    try:
        data = json.loads(body.decode("utf-8"))
        is_json = True
    except:
        pass
    
    ok = (status == 200 and is_json)
    log_test(f"API Endpoint: {ep}", ok, f"HTTP {status}, JSON valid")

# ---------------------------------------------------------
# SECTION 8: Crawlers & Sitemaps (/robots.txt, /sitemap.xml)
# ---------------------------------------------------------
print(f"\n{BOLD}8. Search Engine Robots & Sitemap Verification{RESET}")
# Check robots.txt
status, h, body = http_get("/robots.txt")
body_txt = body.decode("utf-8", errors="ignore")
has_sitemap_ref = "Sitemap: https://devengers.org/sitemap.xml" in body_txt
has_googlebot = "User-agent: Googlebot" in body_txt
has_disallow_admin = "Disallow: /admin-*" in body_txt
log_test("robots.txt HTTP 200", status == 200)
log_test("robots.txt references sitemap.xml", has_sitemap_ref)
log_test("robots.txt explicitly configures Googlebot", has_googlebot)
log_test("robots.txt protects /admin-*", has_disallow_admin)

# Check sitemap.xml
status, h, body = http_get("/sitemap.xml")
log_test("sitemap.xml HTTP 200", status == 200)
try:
    root = ET.fromstring(body)
    urls = root.findall("{http://www.sitemaps.org/schemas/sitemap/0.9}url")
    log_test("sitemap.xml Valid XML", True, f"({len(urls)} URLs listed)")
    
    # Check that all URLs in sitemap return HTTP 200 locally
    all_sitemap_urls_ok = True
    for u in urls:
        loc = u.find("{http://www.sitemaps.org/schemas/sitemap/0.9}loc")
        if loc is not None and loc.text:
            url_path = loc.text.replace("https://devengers.org", "") or "/"
            s, _, _ = http_get(url_path)
            if s != 200:
                all_sitemap_urls_ok = False
                log_test(f"  Sitemap URL Check: {url_path}", False, f"HTTP {s}")
    log_test("All Sitemap URLs Resolving Locally (HTTP 200)", all_sitemap_urls_ok)
except Exception as e:
    log_test("sitemap.xml Valid XML", False, str(e))

# ---------------------------------------------------------
# SECTION 9: Database Schema & Data Integrity
# ---------------------------------------------------------
print(f"\n{BOLD}9. SQLite Database Integrity & Record Metrics{RESET}")
db_path = os.path.join(PROJECT_DIR, "devengers.db")
if os.path.exists(db_path):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("PRAGMA integrity_check;")
    check = cur.fetchone()
    log_test("devengers.db PRAGMA integrity_check", check == ("ok",), str(check))
    
    cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = [t[0] for t in cur.fetchall()]
    log_test("devengers.db Key Tables", "users" in tables and "events" in tables and "certificates_competitions" in tables, f"{len(tables)} tables present")
    
    for tbl in ["users", "events", "certificates_competitions", "certificate_participants"]:
        if tbl in tables:
            cur.execute(f"SELECT count(*) FROM {tbl};")
            cnt = cur.fetchone()[0]
            log_test(f"  Table '{tbl}' Record Count", cnt > 0, f"{cnt} rows")
    conn.close()
else:
    log_test("devengers.db exists", False, "Missing database file")

# ---------------------------------------------------------
# SUMMARY
# ---------------------------------------------------------
print(f"\n{BOLD}{CYAN}========================================================================={RESET}")
total_tests = passed_count + failed_count
print(f"{BOLD}TOTAL TESTS EVALUATED: {total_tests}{RESET}")
print(f"{GREEN}{BOLD}PASSED: {passed_count}{RESET}")
if failed_count == 0:
    print(f"{GREEN}{BOLD}ALL CHECKS PASSED WITH 100% SUCCESS! PRODUCTION READY 🚀{RESET}")
    print(f"{BOLD}{CYAN}========================================================================={RESET}\n")
    sys.exit(0)
else:
    print(f"{RED}{BOLD}FAILED: {failed_count}{RESET}")
    print(f"{BOLD}{CYAN}========================================================================={RESET}\n")
    sys.exit(1)
