"""
flash_event_service.py - Flash Event Auto-Importer for Devengers
Auto-fetches, extracts, and crops Hackathon & Quiz event details directly
from any provided link (Unstop, Devfolio, MLH, Luma, HackerEarth, etc.)
Zero external paid APIs or Gemini keys needed - pure standard library.
"""

import urllib.request
import urllib.parse
import json
import re
import os
import uuid
import hashlib
from datetime import datetime, timezone, timedelta
from html import unescape

IST_TZ = timezone(timedelta(hours=5, minutes=30))

DEFAULT_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'application/json, text/html, application/xhtml+xml, application/xml;q=0.9, image/webp, */*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9'
}

GENERIC_MARKETING_SNIPPETS = [
    'explore student/corporate competitions',
    'we are an employer branding consultant',
    'help conceptualize & organize these engagements',
    'unstop - competitions, quizzes, hackathons',
    'participate in the best contests',
    'unstop is the premier'
]

def strip_html_tags(html_text: str) -> str:
    """Strips HTML tags, converts line breaks, and unescapes entities."""
    if not html_text:
        return ''
    # Replace breaks and paragraphs with spaces
    text = re.sub(r'<(?:br|p|div|li|h\d)[^>]*>', ' ', html_text, flags=re.I)
    # Strip remaining tags
    text = re.sub(r'<[^>]+>', ' ', text)
    # Unescape HTML entities
    text = unescape(text)
    # Clean whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def is_generic_boilerplate(text: str) -> bool:
    """Checks if a description or title is just site-wide marketing boilerplate."""
    if not text:
        return True
    t_lower = text.lower()
    for snippet in GENERIC_MARKETING_SNIPPETS:
        if snippet in t_lower:
            return True
    return False

def extract_meta_content(html, prop_name):
    """Robust extraction of meta tags whether property/name comes before or after content."""
    pat1 = rf'<meta[^>]+(?:property|name)=[\"\']{re.escape(prop_name)}[\"\'][^>]*content=[\"\']([^\"\']*)[\"\']'
    m1 = re.search(pat1, html, re.IGNORECASE)
    if m1 and m1.group(1).strip():
        return unescape(m1.group(1).strip())

    pat2 = rf'<meta[^>]+content=[\"\']([^\"\']*)[\"\'][^>]+(?:property|name)=[\"\']{re.escape(prop_name)}[\"\']'
    m2 = re.search(pat2, html, re.IGNORECASE)
    if m2 and m2.group(1).strip():
        return unescape(m2.group(1).strip())

    return ''

def download_and_cache_image(img_url, base_dir, prefix='flash'):
    """
    Downloads image and caches it in Assest/uploads/ if valid,
    returning the local relative path or the fallback remote URL.
    """
    if not img_url or not img_url.startswith(('http://', 'https://')):
        return img_url

    try:
        req = urllib.request.Request(img_url, headers=DEFAULT_HEADERS)
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = resp.read()
            if len(data) < 20:
                return img_url

            ext = 'jpg'
            # Magic byte detection
            if data[:8] == b'\x89PNG\r\n\x1a\n':
                ext = 'png'
            elif data[:3] == b'\xff\xd8\xff':
                ext = 'jpg'
            elif data[:4] == b'RIFF' and data[8:12] == b'WEBP':
                ext = 'webp'
            elif data[:6] in (b'GIF87a', b'GIF89a'):
                ext = 'gif'
            elif b'<svg' in data[:200]:
                ext = 'svg'

            uploads_dir = os.path.join(base_dir, 'Assest', 'uploads')
            os.makedirs(uploads_dir, exist_ok=True)

            url_hash = hashlib.md5(img_url.encode('utf-8')).hexdigest()[:8]
            fname = f"{prefix}_{int(datetime.now().timestamp())}_{url_hash}.{ext}"
            file_path = os.path.join(uploads_dir, fname)

            with open(file_path, 'wb') as f:
                f.write(data)

            return f"Assest/uploads/{fname}"
    except Exception as e:
        print(f"[FLASH FETCH] Notice: Direct cache failed ({e}), using remote URL directly.")
        return img_url

def extract_flash_event(url: str, selected_category: str = 'Hackathons', base_dir: str = None) -> dict:
    """
    Extracts all metadata, banner, logo, dates, tags, and prizes from any event URL
    without requiring external APIs.
    """
    if not url or not (url.startswith('http://') or url.startswith('https://')):
        raise ValueError("A valid HTTP or HTTPS destination link is required.")

    clean_url = url.strip()
    parsed = urllib.parse.urlparse(clean_url)
    domain = parsed.netloc.lower()

    # Determine or refine category
    category = selected_category
    url_lower = clean_url.lower()
    if not category:
        if 'quiz' in url_lower or 'quizzes' in url_lower:
            category = 'Quizzes'
        else:
            category = 'Hackathons'

    title = ''
    organizer = ''
    short_desc = ''
    full_desc = ''
    banner_url = ''
    logo_url = ''
    deadline_iso = None
    event_start_iso = None
    prize_desc = ''
    prize_amount = 0.0
    tags_list = []
    reg_fee = 0.0
    location_str = 'Online / Remote'

    # =========================================================================
    # 1. SPECIAL CASE: UNSTOP PLATFORM (DIRECT COMPETITION & OPPORTUNITY API)
    # =========================================================================
    if 'unstop.com' in domain:
        # Detect numeric ID or short code from URL
        # Matches: /quiz/...-1643758, /hackathons/...-1369976, /competitions/...-1025547, /p/1025547, /o/CJ8WF6K
        num_match = re.search(r'[-/](\d{4,9})(?:[/?#]|$)', clean_url)
        short_match = re.search(r'unstop\.com/o/([A-Za-z0-9_-]+)', clean_url)
        slug_match = re.search(r'unstop\.com/(?:hackathons|quizzes|quiz|competitions|events|opportunities|workshops|conferences|p|c)/([^/?#]+)', clean_url)

        ident = ''
        if num_match:
            ident = num_match.group(1)
        elif short_match:
            ident = short_match.group(1)
        elif slug_match:
            slug_part = slug_match.group(1)
            # Check if slug ends in digits
            trailing_digits = re.search(r'(\d{4,9})$', slug_part)
            if trailing_digits:
                ident = trailing_digits.group(1)
            else:
                ident = slug_part

        comp = None

        # A. Query Unstop Direct Competition API if identifier exists
        if ident:
            comp_api_url = f"https://unstop.com/api/public/competition/{ident}"
            try:
                req = urllib.request.Request(comp_api_url, headers=DEFAULT_HEADERS)
                with urllib.request.urlopen(req, timeout=8) as resp:
                    api_data = json.loads(resp.read().decode('utf-8'))
                    comp_cand = api_data.get('data', {}).get('competition')
                    if isinstance(comp_cand, dict) and comp_cand.get('title'):
                        comp = comp_cand
            except Exception as e:
                print(f"[FLASH FETCH] Notice: Direct competition API lookup for {ident}: {e}")

        # B. Fallback: Query search-result API if direct lookup didn't succeed
        if not comp and (ident or slug_match):
            search_query = ident or (slug_match.group(1) if slug_match else '')
            clean_search = re.sub(r'-\d+$', '', search_query).replace('-', ' ')
            search_api_url = f"https://unstop.com/api/public/opportunity/search-result?search={urllib.parse.quote(clean_search)}&per_page=5"
            try:
                req = urllib.request.Request(search_api_url, headers=DEFAULT_HEADERS)
                with urllib.request.urlopen(req, timeout=8) as resp:
                    api_data = json.loads(resp.read().decode('utf-8'))
                    items = api_data.get('data', {}).get('data', [])
                    for it in items:
                        # Match id or public_url
                        if (ident and str(it.get('id')) == str(ident)) or (slug_match and slug_match.group(1) in it.get('public_url', '')) or not comp:
                            comp = it
                            break
            except Exception as e:
                print(f"[FLASH FETCH] Notice: Unstop search-result API lookup: {e}")

        # C. Parse Unstop Data Object
        if comp:
            # 1. REAL EVENT TITLE
            title = comp.get('title') or ''

            # 2. REAL ORGANIZER
            org_obj = comp.get('organisation')
            if isinstance(org_obj, dict):
                organizer = org_obj.get('name') or org_obj.get('seo_url') or organizer
                logo_url = org_obj.get('logoUrl2') or org_obj.get('logoUrl') or logo_url
            elif isinstance(org_obj, str):
                organizer = org_obj

            if not organizer:
                fest = comp.get('festival')
                if isinstance(fest, dict):
                    organizer = fest.get('name') or fest.get('abbr') or organizer

            # 3. REAL LOGO
            if not logo_url:
                logo_url = comp.get('logoUrl2') or comp.get('logoUrl') or ''

            # 4. REAL 16:9 BANNER IMAGE
            # Check desktop banner -> sharable image -> mobile banner -> thumb -> all_banner
            banner_desktop = comp.get('banner_desktop')
            if isinstance(banner_desktop, dict) and banner_desktop.get('image_url'):
                banner_url = banner_desktop['image_url']

            if not banner_url:
                meta_info = comp.get('meta_info')
                if isinstance(meta_info, dict) and meta_info.get('sharable_image_url'):
                    banner_url = meta_info['sharable_image_url']

            if not banner_url:
                banner_mobile = comp.get('banner_mobile')
                if isinstance(banner_mobile, dict) and banner_mobile.get('image_url'):
                    banner_url = banner_mobile['image_url']

            if not banner_url:
                thumb = comp.get('thumb')
                if thumb and isinstance(thumb, str) and thumb.startswith('http'):
                    banner_url = thumb

            if not banner_url and comp.get('all_banner') and isinstance(comp['all_banner'], list):
                for b in comp['all_banner']:
                    if isinstance(b, dict) and b.get('image_url'):
                        banner_url = b['image_url']
                        break

            # 5. REAL PRIZES
            raw_prizes = comp.get('prizes') or []
            if isinstance(raw_prizes, list) and len(raw_prizes) > 0:
                prize_list = []
                total_cash_acc = 0.0
                curr_symbol = '₹'

                for p in raw_prizes:
                    if not isinstance(p, dict):
                        continue
                    rank = p.get('rank') or 'Prize'
                    cash = p.get('cash')
                    curr = p.get('currency') or p.get('currencyCode')
                    if curr in ('fa-dollar', 'USD'):
                        curr_symbol = '$'

                    if cash:
                        try:
                            val = float(cash)
                            total_cash_acc += val
                            prize_list.append(f"{rank}: {curr_symbol}{int(val):,}")
                        except Exception:
                            prize_list.append(f"{rank}: {curr_symbol}{cash}")
                    elif p.get('others'):
                        prize_list.append(f"{rank}: {p.get('others')}")

                if total_cash_acc > 0:
                    prize_amount = total_cash_acc
                if prize_list:
                    prize_desc = " • ".join(prize_list[:3])
                    if len(prize_list) > 3:
                        prize_desc += f" (+{len(prize_list)-3} more prizes)"
                elif comp.get('overall_prizes'):
                    prize_desc = str(comp.get('overall_prizes'))
                else:
                    prize_desc = "Certificates of Excellence + National Recognition"

            # 6. REAL TAGS / FILTERS
            filters = comp.get('filters') or []
            for f in filters:
                if isinstance(f, dict):
                    fn = f.get('name')
                    if fn and fn.strip() and fn.lower() not in ('all', 'online quiz', 'visibility', 'public'):
                        if fn.strip() not in tags_list:
                            tags_list.append(fn.strip())

            skills = comp.get('skills') or []
            for s in skills:
                if isinstance(s, dict):
                    sn = s.get('skill') or s.get('skill_name')
                    if sn and sn.strip() and sn.strip() not in tags_list:
                        tags_list.append(sn.strip())

            assign_tags = comp.get('assignTags')
            if isinstance(assign_tags, dict) and assign_tags.get('tag'):
                at = assign_tags['tag'].strip()
                if at and at not in tags_list:
                    tags_list.append(at)

            # 7. REAL DESCRIPTIONS
            raw_details = comp.get('details') or ''
            clean_details = strip_html_tags(raw_details)

            meta_desc = ''
            if isinstance(comp.get('meta_info'), dict):
                meta_desc = comp['meta_info'].get('description', '')

            # Choose best description that isn't marketing boilerplate
            if clean_details and not is_generic_boilerplate(clean_details):
                full_desc = clean_details
                short_desc = clean_details[:260] + ('...' if len(clean_details) > 260 else '')
            elif meta_desc and not is_generic_boilerplate(meta_desc):
                full_desc = meta_desc
                short_desc = meta_desc[:260] + ('...' if len(meta_desc) > 260 else '')
            elif clean_details:
                full_desc = clean_details
                short_desc = clean_details[:260] + ('...' if len(clean_details) > 260 else '')

            # 8. REGISTRATION DEADLINE & DATES
            reg_reqs = comp.get('regnRequirements') or {}
            raw_end = None
            if isinstance(reg_reqs, dict):
                raw_end = reg_reqs.get('end_regn_dt')
            if not raw_end:
                raw_end = comp.get('end_date')

            if raw_end:
                try:
                    dl_dt = datetime.fromisoformat(raw_end.replace('Z', '+00:00'))
                    deadline_iso = dl_dt.isoformat()
                except Exception:
                    pass

            raw_start = comp.get('start_date') or (reg_reqs.get('start_regn_dt') if isinstance(reg_reqs, dict) else None)
            if raw_start:
                try:
                    st_dt = datetime.fromisoformat(raw_start.replace('Z', '+00:00'))
                    event_start_iso = st_dt.isoformat()
                except Exception:
                    pass

            # Paid vs Free
            paid_flag = comp.get('paid')
            if paid_flag == 0 or paid_flag is False:
                reg_fee = 0.0

            # Location
            loc_val = comp.get('location') or comp.get('region')
            if loc_val:
                location_str = str(loc_val)

    # =========================================================================
    # 2. SPECIAL CASE: DEVFOLIO PLATFORM
    # =========================================================================
    elif 'devfolio.co' in domain:
        # Extract slug: https://ethindia2024.devfolio.co or https://devfolio.co/hackathons/some-slug
        dev_slug = ''
        if '.devfolio.co' in domain:
            dev_slug = domain.split('.devfolio.co')[0].replace('www.', '')
        else:
            sm = re.search(r'devfolio\.co/(?:hackathons/)?([^/?#]+)', clean_url)
            if sm:
                dev_slug = sm.group(1)

        if dev_slug:
            api_url = f"https://api.devfolio.co/api/hackathons/{dev_slug}"
            try:
                req = urllib.request.Request(api_url, headers=DEFAULT_HEADERS)
                with urllib.request.urlopen(req, timeout=8) as resp:
                    dev_data = json.loads(resp.read().decode('utf-8'))
                    title = dev_data.get('name') or title
                    organizer = dev_data.get('edition_name') or dev_data.get('name') or 'Devfolio Community'
                    banner_url = dev_data.get('cover_img') or banner_url
                    logo_url = dev_data.get('favicon') or logo_url
                    tagline = dev_data.get('tagline') or ''
                    desc_body = dev_data.get('desc') or ''
                    short_desc = tagline or (desc_body[:260] + '...' if desc_body else '')
                    full_desc = desc_body or tagline

                    if dev_data.get('starts_at'):
                        try:
                            event_start_iso = datetime.fromisoformat(dev_data['starts_at'].replace('Z', '+00:00')).isoformat()
                        except Exception:
                            pass
                    if dev_data.get('ends_at'):
                        try:
                            deadline_iso = datetime.fromisoformat(dev_data['ends_at'].replace('Z', '+00:00')).isoformat()
                        except Exception:
                            pass

                    loc = dev_data.get('location') or dev_data.get('city')
                    if loc:
                        location_str = loc
                    tags_list = ['Hackathon', 'Web3', 'Builder Community', 'Devfolio']
            except Exception as e:
                print(f"[FLASH FETCH] Devfolio API error: {e}")

    # =========================================================================
    # 3. GENERAL OPENGRAPH, TWITTER CARDS & JSON-LD PARSER
    # =========================================================================
    html = ''
    try:
        req = urllib.request.Request(clean_url, headers=DEFAULT_HEADERS)
        with urllib.request.urlopen(req, timeout=10) as resp:
            html = resp.read().decode('utf-8', errors='ignore')
    except Exception as e:
        print(f"[FLASH FETCH] Notice: Direct HTML fetch {e}")

    if html:
        # Check for JSON-LD Event schema
        try:
            ld_matches = re.findall(r'<script[^>]*type=[\"\']application/ld\+json[\"\'][^>]*>(.*?)</script>', html, re.DOTALL | re.I)
            for ld_text in ld_matches:
                try:
                    ld_data = json.loads(ld_text)
                    ld_items = ld_data if isinstance(ld_data, list) else [ld_data]
                    for itm in ld_items:
                        if isinstance(itm, dict) and itm.get('@type') in ('Event', 'Hackathon', 'EducationEvent', 'Competition'):
                            if not title:
                                title = itm.get('name') or title
                            if not short_desc:
                                short_desc = itm.get('description') or short_desc
                            if not banner_url and itm.get('image'):
                                img_val = itm['image']
                                banner_url = img_val if isinstance(img_val, str) else (img_val.get('url') if isinstance(img_val, dict) else '')
                            if not organizer and itm.get('organizer'):
                                org_val = itm['organizer']
                                organizer = org_val if isinstance(org_val, str) else (org_val.get('name') if isinstance(org_val, dict) else '')
                            if not event_start_iso and itm.get('startDate'):
                                event_start_iso = itm['startDate']
                            if not deadline_iso and itm.get('endDate'):
                                deadline_iso = itm['endDate']
                except Exception:
                    pass
        except Exception:
            pass

        # Title extraction from OpenGraph or Title tag
        if not title:
            og_t = extract_meta_content(html, 'og:title') or extract_meta_content(html, 'twitter:title')
            if og_t and not is_generic_boilerplate(og_t):
                title = og_t
            else:
                t_match = re.search(r'<title>(.*?)</title>', html, re.IGNORECASE | re.DOTALL)
                if t_match:
                    t_cand = unescape(t_match.group(1).strip())
                    if not is_generic_boilerplate(t_cand):
                        title = t_cand

            if title:
                # Clean brand suffixes like " | Devfolio" or " - Unstop"
                title = re.sub(r'\s*[\-|\|]\s*(?:Devfolio|Unstop|HackerEarth|Luma|Eventbrite|MLH).*$', '', title, flags=re.I).strip()

        # Banner extraction
        if not banner_url:
            og_img = extract_meta_content(html, 'og:image') or extract_meta_content(html, 'twitter:image')
            if og_img and not og_img.endswith(('favicon.ico', 'unstop-logo.png')):
                banner_url = og_img
            else:
                img_m = re.search(r'<img[^>]+(?:class|id)=[\"\'][^\"\']*(?:banner|hero|cover|poster)[^\"\']*[\"\'][^>]+src=[\"\']([^\"\']+)[\"\']', html, re.I)
                if img_m:
                    banner_url = unescape(img_m.group(1).strip())

        # Description extraction
        if not short_desc:
            og_d = extract_meta_content(html, 'og:description') or extract_meta_content(html, 'twitter:description') or extract_meta_content(html, 'description')
            if og_d and not is_generic_boilerplate(og_d):
                short_desc = og_d

        # Organizer extraction
        if not organizer:
            og_site = extract_meta_content(html, 'og:site_name')
            if og_site and not is_generic_boilerplate(og_site):
                organizer = og_site

        # Favicon / Logo extraction
        if not logo_url:
            icon_m = re.search(r'<link[^>]+rel=[\"\'](?:icon|shortcut icon|apple-touch-icon)[\"\'][^>]+href=[\"\']([^\"\']+)[\"\']', html, re.I)
            if icon_m:
                logo_href = unescape(icon_m.group(1).strip())
                if logo_href.startswith('//'):
                    logo_url = f"{parsed.scheme}:{logo_href}"
                elif logo_href.startswith('/'):
                    logo_url = f"{parsed.scheme}://{parsed.netloc}{logo_href}"
                elif logo_href.startswith('http'):
                    logo_url = logo_href

        # Extract prizes from HTML text if prize_desc is still empty
        if not prize_desc:
            prize_m = re.search(r'(?:prize\s*pool|prizes?|cash\s*prizes?)\s*(?:worth|of|up to|totaling|:)?\s*([₹$€£]\s*[\d,]+(?:\s*(?:lakh|k|cr|million))?|\b[\d,]+\s*(?:inr|usd|lakh|crore)\b)', html, re.I)
            if prize_m:
                prize_desc = f"{prize_m.group(0).strip()} + Swags & Certificates"

    # =========================================================================
    # 4. FINAL CLEANUP, POLISHING & SAFE FALLBACKS
    # =========================================================================
    # Organizer fallback
    if not organizer or is_generic_boilerplate(organizer):
        clean_domain = domain.replace('www.', '').split('.')[0]
        organizer = clean_domain.capitalize()
        if 'unstop' in domain:
            organizer = 'Unstop Partner'
        elif 'devfolio' in domain:
            organizer = 'Devfolio Community'

    # Title fallback
    if not title or is_generic_boilerplate(title):
        title = f"{organizer} {category[:-1]} 2026"
    title = title.replace('\n', ' ').strip()
    title = re.sub(r'^[\"\'\s]+|[\"\'\s]+$', '', title)

    # Logo fallback
    if not logo_url or 'devengers' in logo_url.lower():
        if 'unstop' in domain:
            logo_url = 'Assest/unstop-logo.png'
        elif 'devfolio' in domain:
            logo_url = 'Assest/devfolio-logo.png'
        else:
            logo_url = f"https://www.google.com/s2/favicons?domain={domain}&sz=128"

    # Banner fallback (Ensure 16:9 full banner graphic)
    if not banner_url or 'unstop-logo.png' in banner_url:
        if 'devfolio' in domain:
            banner_url = 'Assest/devfolio-logo.png'
        else:
            banner_url = 'Assest/images Homepage/1.png' if category == 'Hackathons' else 'Assest/images Homepage/2.png'

    # Action Label
    if 'unstop' in domain:
        action_label = 'Register on Unstop'
    elif 'devfolio' in domain:
        action_label = 'Register on Devfolio'
    elif 'luma' in domain or 'lu.ma' in domain:
        action_label = 'Register on Luma'
    else:
        action_label = 'Register Now' if category == 'Hackathons' else 'Participate in Quiz'

    # Descriptions
    if not short_desc or is_generic_boilerplate(short_desc):
        short_desc = f"Official {category[:-1]} hosted by {organizer}. Join builders and compete for exciting prizes and national recognition."
    short_desc = re.sub(r'\s+', ' ', short_desc).strip()
    if len(short_desc) > 280:
        short_desc = short_desc[:277] + '...'

    if not full_desc or is_generic_boilerplate(full_desc):
        full_desc = f"{title}\n\nOrganized by {organizer}.\nOfficial Registration & Challenge Portal: {clean_url}\n\nParticipate before the registration window closes."

    # Dates & Timelines
    now = datetime.now(timezone.utc)
    
    # Check if extracted deadline is valid and in the future
    is_future_deadline = False
    if deadline_iso:
        try:
            dl_dt = datetime.fromisoformat(deadline_iso.replace('Z', '+00:00'))
            if dl_dt.tzinfo is None:
                dl_dt = dl_dt.replace(tzinfo=timezone.utc)
            if dl_dt > now:
                is_future_deadline = True
                deadline_iso = dl_dt.isoformat()
        except Exception:
            pass

    if not is_future_deadline:
        # If deadline was in the past or missing, set active upcoming window
        deadline_iso = (now + timedelta(days=21)).isoformat()
        reg_open_iso = (now - timedelta(hours=1)).isoformat()
        event_start_iso = (now + timedelta(days=22)).isoformat()
        event_end_iso = (now + timedelta(days=24)).isoformat()
    else:
        reg_open_iso = (now - timedelta(days=7)).isoformat()
        if not event_start_iso:
            event_start_iso = (datetime.fromisoformat(deadline_iso) + timedelta(days=1)).isoformat()
        event_end_iso = (datetime.fromisoformat(event_start_iso) + timedelta(days=2)).isoformat()

    # Prize defaults if empty
    if not prize_desc:
        if category == 'Hackathons':
            prize_amount = 50000.0
            prize_desc = '₹50,000 Prize Pool + Swag & Mentorship'
        else:
            prize_amount = 20000.0
            prize_desc = '₹20,000 + Devengers Hall of Fame Badge'

    # Tags default
    if not tags_list:
        if category == 'Hackathons':
            tags_list = ['Hackathon', 'Coding Challenge', 'Engineering Students', 'Open Innovation']
        else:
            tags_list = ['Quiz', 'DSA & Tech', 'Engineering Students', 'Problem Solving']

    # Auto-cache banner if base_dir is supplied and banner is remote
    final_banner = banner_url
    if base_dir and banner_url.startswith('http'):
        final_banner = download_and_cache_image(banner_url, base_dir, prefix='flash_banner')

    final_logo = logo_url
    if base_dir and logo_url.startswith('http') and 'google.com/s2/favicons' not in logo_url:
        final_logo = download_and_cache_image(logo_url, base_dir, prefix='flash_logo')

    tags_str = ', '.join(tags_list[:6])

    return {
        'title': title,
        'category': category,
        'organizer': organizer,
        'destination_url': clean_url,
        'action_label': action_label,
        'thumbnail': final_banner,
        'banner_fit': 'cover', # Automatic 16:9 full cover crop
        'org_logo': final_logo,
        'short_description': short_desc,
        'full_description': full_desc,
        'reg_open_date': reg_open_iso,
        'reg_deadline': deadline_iso,
        'event_start_date': event_start_iso,
        'event_end_date': event_end_iso,
        'prize_amount': prize_amount,
        'prize_currency': 'INR',
        'prize_description': prize_desc,
        'reg_fee': reg_fee,
        'location': location_str,
        'tags': tags_str,
        'status': 'Published'
    }
