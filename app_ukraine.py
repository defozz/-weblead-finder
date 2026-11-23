"""LeadRadar Mobile — mobile-first ethical lead discovery, public OSM + Freelancehunt RSS.
Deploy on Streamlit Community Cloud. No credentials or paid APIs required.
"""
import csv
import hashlib
import html
import io
import re
import time
import threading
from datetime import datetime, timezone
from urllib.parse import quote, urlparse

import feedparser
import requests
import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(
    page_title="LeadRadar • Поиск клиентов",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="collapsed",
)

CSS = """
<style>
:root {color-scheme: dark;}
.stApp, [data-testid='stAppViewContainer'] {background: #090f1c; color: #eaf0ff;}
[data-testid='stHeader'] {background: rgba(9,15,28,.92);}
[data-testid='stToolbar'] {right:.1rem;}
section.main > div {max-width: 980px;}
.block-container {padding-top: 1.1rem; padding-bottom: 4.5rem;}
html, body, [class*='st-'], p, label {font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;}
h1,h2,h3 {letter-spacing:-.035em !important; color:#f2f6ff !important;}
h1 {font-size:2rem !important;} h3 {font-size:1.22rem !important;}
p, label, .stMarkdown, .stCaption {color:#e6eaf5;}
.stCaption, [data-testid='stCaptionContainer'], small {color:#98a9c5 !important;}
[data-testid='stVerticalBlockBorderWrapper'] > div:has(> [data-testid='stVerticalBlock']) {
 background: #121c2d; border: 1px solid #24344e; border-radius: 18px;
}
[data-testid='stMetric'] {background: #131e31; border:1px solid #263b58; border-radius:14px; padding:10px 12px;}
[data-testid='stMetricValue'] {font-size:1.45rem !important; color:#f4f8ff;}
[data-baseweb='input'] > div, [data-baseweb='select'] > div, [data-baseweb='textarea'] > div {
 background:#101b2b !important; border-color:#30415c !important; color:#f6f8fc !important;
}
input, textarea {color:#f6f8fc !important;}
button[kind='primary'] {background:linear-gradient(100deg,#6b7dff,#6272e8);color:white;border:0;border-radius:12px;font-weight:700;}
button[kind='secondary'], a[data-testid='stLinkButton'] {border-radius:11px !important;}
button {min-height:2.55rem;}
hr {border-color:#263246 !important;}
.hero {
 background: radial-gradient(circle at 96% 9%,rgba(112,100,243,.34),transparent 40%),
 linear-gradient(120deg,#152442,#112035 70%,#19203c);
 border:1px solid #30486d;border-radius:22px;padding:26px 24px 22px;margin:10px 0 19px;
}
.hero-kicker {letter-spacing:.14em; color:#8fd3ff;font-size:12px;font-weight:800;}
.hero h1{margin:6px 0 !important; font-size:2.35rem !important; line-height:1.1 !important;}
.hero p {max-width:560px;margin:9px 0 0;color:#b6c6e2;font-size:15px;line-height:1.5;}
.pill {display:inline-flex; align-items:center;gap:6px;border:1px solid #3b4f71;border-radius:999px;
 padding:3px 10px;font-size:11px;font-weight:750;color:#c7d6f0;background:#1c2941;}
.pill.strong {color:#abffe0;background:#103d34;border-color:#216c54;}
.pill.weak {color:#ffdfaa;background:#3d2c19;border-color:#6a4a24;}
.lead-title {font-size:17px;font-weight:750;line-height:1.35;color:#f5f7ff;margin:0 0 9px;}
.lead-meta {font-size:12px;color:#acb9cf;margin:7px 0;line-height:1.5;}
.lead-note {font-size:13px;color:#d3dceb;line-height:1.55;}
.section-head {margin-top:16px;margin-bottom:9px;font-size:21px;font-weight:750;color:#f4f7ff;}
.footer-notice {font-size:12px;color:#8798b4;line-height:1.6;margin:24px 0;}
@media(max-width:650px){
 .block-container{padding: .9rem .8rem 3.5rem !important;}
 .hero{padding:20px 16px;margin:3px 0 13px;border-radius:17px;}
 .hero h1{font-size:1.9rem !important;}
 .hero p{font-size:13px;}
 h1{font-size:1.7rem !important;}
 [data-testid='stMetricValue'] {font-size:1.2rem !important;}
}
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)
st.markdown('''<div class="hero"><div class="hero-kicker">LEADRADAR / UKRAINE + EUROPE</div>
<h1>🎯 Находи клиентов<br>на создание сайтов</h1>
<p>🇺🇦 Україна за замовчуванням: області, міста й селища. Публічні контакти, демо-сайти та замовлення — з телефона.</p></div>''', unsafe_allow_html=True)

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "LeadRadarMobile/2.0 (+https://github.com/defozz/-weblead-finder; public OSM lead research)", "Accept-Language": "uk,ru;q=0.9,en;q=0.6"})
GEO_LOCK = threading.Lock()
LAST_GEOCODE_TIME = [0.0]

CATEGORY = {
    "☕ Кав’ярні та ресторани": [('amenity', '^(cafe|restaurant|fast_food|bar|pub)$')],
    "💇 Краса і барбершопи": [('shop', '^(hairdresser|beauty|cosmetics|massage|tattoo)$'),('beauty','.')],
    "🛍 Магазини": [('shop','^(clothes|shoes|convenience|supermarket|bakery|florist|jewelry|mobile_phone|electronics|gift|pet|sports|books|furniture)$')],
    "🚗 Автосервіси": [('shop','^(car_repair|car|tyres|car_parts)$'),('amenity','^(car_wash|fuel)$')],
    "🦷 Медицина": [('amenity','^(clinic|doctors|dentist|pharmacy)$'),('healthcare','^(clinic|dentist|doctor)$')],
    "🏨 Готелі та відпочинок": [('tourism','^(hotel|hostel|guest_house|motel|apartment)$')],
    "🏋️ Спорт і фітнес": [('leisure','^(fitness_centre|sports_centre)$'),('sport','^(fitness|gym)$')],
}

# Location presets. Ukraine is the default. Other countries remain available.
COUNTRIES = {
    "🇺🇦 Україна": ("ua", "Україна", ["Дніпро", "Київ", "Харків", "Одеса", "Львів", "Запоріжжя", "Синельникове", "Кривий Ріг", "Полтава", "Вінниця", "Черкаси", "Тернопіль"]),
    "🇵🇱 Польща": ("pl", "Polska", ["Warszawa", "Kraków", "Wrocław", "Gdańsk", "Poznań", "Łódź"]),
    "🇨🇿 Чехія": ("cz", "Česko", ["Praha", "Brno", "Ostrava", "Plzeň"]),
    "🇩🇪 Німеччина": ("de", "Deutschland", ["Berlin", "Hamburg", "München", "Köln", "Frankfurt am Main"]),
    "🇸🇰 Словаччина": ("sk", "Slovensko", ["Bratislava", "Košice", "Prešov"]),
}

UKRAINE_REGIONS = {
    "Усі області / Не вказувати": [],
    "м. Київ": ["Київ"],
    "Вінницька область": ["Вінниця", "Жмеринка", "Козятин", "Могилів-Подільський"],
    "Волинська область": ["Луцьк", "Ковель", "Нововолинськ", "Володимир"],
    "Дніпропетровська область": ["Дніпро", "Кривий Ріг", "Кам’янське", "Нікополь", "Павлоград", "Синельникове"],
    "Донецька область": ["Краматорськ", "Слов’янськ", "Покровськ", "Маріуполь"],
    "Житомирська область": ["Житомир", "Бердичів", "Коростень"],
    "Закарпатська область": ["Ужгород", "Мукачево", "Хуст"],
    "Запорізька область": ["Запоріжжя", "Мелітополь", "Бердянськ"],
    "Івано-Франківська область": ["Івано-Франківськ", "Калуш", "Коломия"],
    "Київська область": ["Біла Церква", "Бровари", "Бориспіль", "Ірпінь", "Буча", "Вишневе"],
    "Кіровоградська область": ["Кропивницький", "Олександрія", "Знам’янка"],
    "Луганська область": ["Луганськ", "Сєвєродонецьк", "Лисичанськ"],
    "Львівська область": ["Львів", "Дрогобич", "Стрий", "Шептицький"],
    "Миколаївська область": ["Миколаїв", "Первомайськ", "Вознесенськ"],
    "Одеська область": ["Одеса", "Чорноморськ", "Ізмаїл", "Білгород-Дністровський"],
    "Полтавська область": ["Полтава", "Кременчук", "Миргород", "Лубни"],
    "Рівненська область": ["Рівне", "Дубно", "Вараш"],
    "Сумська область": ["Суми", "Конотоп", "Шостка", "Охтирка"],
    "Тернопільська область": ["Тернопіль", "Чортків", "Кременець"],
    "Харківська область": ["Харків", "Лозова", "Ізюм", "Чугуїв"],
    "Херсонська область": ["Херсон", "Нова Каховка", "Каховка"],
    "Хмельницька область": ["Хмельницький", "Кам’янець-Подільський", "Шепетівка"],
    "Черкаська область": ["Черкаси", "Умань", "Сміла", "Золотоноша"],
    "Чернівецька область": ["Чернівці", "Хотин", "Сторожинець"],
    "Чернігівська область": ["Чернігів", "Ніжин", "Прилуки"],
    "АР Крим": ["Сімферополь", "Севастополь", "Ялта", "Євпаторія"],
}

# Keep public services healthy: geocodes are cached for a day and require an explicit button click.
@st.cache_data(ttl=24 * 3600, show_spinner=False)
def geocode_city(city: str, country_code: str = "ua", country_label: str = "Україна", region: str = "") -> dict:
    location_query = ", ".join(x for x in (city, region, country_label) if x)
    with GEO_LOCK:
        elapsed = time.monotonic() - LAST_GEOCODE_TIME[0]
        if elapsed < 1.1:
            time.sleep(1.1 - elapsed)
        LAST_GEOCODE_TIME[0] = time.monotonic()
        response = SESSION.get("https://nominatim.openstreetmap.org/search", params={
            "q": location_query, "format": "jsonv2", "countrycodes": country_code, "limit": 1
        }, timeout=18)
    response.raise_for_status()
    data = response.json()
    if not data:
        raise ValueError("Населений пункт не знайдено. Перевір написання або прибери область.")
    result = data[0]
    return {"lat": float(result["lat"]), "lon": float(result["lon"]), "display_name": result["display_name"]}


def build_overpass_query(lat: float, lon: float, radius: int, category: str) -> str:
    selectors = CATEGORY.get(category, [])
    lines = []
    for key, pattern in selectors:
        # No user-supplied expressions are inserted into the query.
        lines.append(f'  nwr(around:{radius},{lat:.6f},{lon:.6f})["{key}"~"{pattern}"]["name"];')
    return '[out:json][timeout:28];\n(\n' + '\n'.join(lines) + '\n);\nout center 300;'


def safe_url(raw: str) -> str:
    raw = (raw or "").strip().split(";")[0].strip()
    if not raw:
        return ""
    if raw.startswith("www."):
        raw = "https://" + raw
    if not raw.startswith(("http://", "https://")) and "." in raw and " " not in raw and not raw.startswith("@"): 
        raw = "https://" + raw
    try:
        result = urlparse(raw)
        if result.scheme in ("https", "http") and result.netloc and " " not in result.netloc:
            return raw
    except Exception:
        pass
    return ""


def normalize_phone(phone: str) -> str:
    phone = (phone or "").split(";")[0].strip()
    if not phone or len(phone) > 35:
        return ""
    return phone


def osm_to_lead(element: dict, city: str) -> dict | None:
    tags = element.get("tags") or {}
    name = tags.get("name:uk") or tags.get("name") or tags.get("name:ru") or ""
    if not name.strip():
        return None
    location = element.get("center") or element
    lat, lon = location.get("lat"), location.get("lon")
    if lat is None or lon is None:
        return None
    website = safe_url(tags.get("website") or tags.get("contact:website") or tags.get("url") or "")
    instagram_raw = (tags.get("contact:instagram") or tags.get("instagram") or "").strip()
    if instagram_raw.startswith("@"):
        instagram = "https://www.instagram.com/" + quote(instagram_raw[1:])
    elif instagram_raw and "/" not in instagram_raw and "." not in instagram_raw:
        instagram = "https://www.instagram.com/" + quote(instagram_raw)
    else:
        instagram = safe_url(instagram_raw)
    phone = normalize_phone(tags.get("contact:phone") or tags.get("phone") or tags.get("mobile") or "")
    social = instagram or safe_url(tags.get("contact:facebook") or tags.get("facebook") or "")
    street = tags.get("addr:street", "")
    house = tags.get("addr:housenumber", "")
    address = " ".join(v for v in (street, house) if v).strip()
    if not address:
        address = city
    raw_category = (tags.get("amenity") or tags.get("shop") or tags.get("tourism") or tags.get("leisure") or tags.get("healthcare") or "бизнес")
    osm_type, osm_id = element.get("type", "node"), element.get("id", 0)
    map_url = f"https://www.openstreetmap.org/{osm_type}/{osm_id}"
    score = (4 if not website else 0) + (3 if phone else 0) + (2 if social else 0) + (1 if street else 0)
    return {"id": f"{osm_type}/{osm_id}", "name": name.strip(), "category": raw_category,
            "address": address, "city": city, "phone": phone, "website": website,
            "social": social, "osm_url": map_url, "lat": lat, "lon": lon,
            "score": score, "source": "OpenStreetMap"}


@st.cache_data(ttl=40 * 60, show_spinner=False)
def fetch_businesses(city: str, category: str, radius: int, country_code: str = "ua", country_label: str = "Україна", region: str = "") -> list[dict]:
    geo = geocode_city(city, country_code, country_label, region)
    query = build_overpass_query(geo["lat"], geo["lon"], radius, category)
    errors = []
    # Use one instance, fallback only on error. Never bulk crawl.
    for endpoint in ("https://overpass.kumi.systems/api/interpreter", "https://overpass-api.de/api/interpreter"):
        try:
            response = SESSION.post(endpoint, data={"data": query}, timeout=48)
            response.raise_for_status()
            data = response.json()
            if not isinstance(data.get("elements"), list):
                raise ValueError("Неверный ответ картографического сервиса")
            leads = [osm_to_lead(obj, city) for obj in data["elements"]]
            leads = [lead for lead in leads if lead]
            # Remove duplicate nodes/ways for identical premises, preserving different locations.
            unique = {}
            for lead in leads:
                marker = (lead["name"].casefold(), round(lead["lat"], 4), round(lead["lon"], 4))
                if marker not in unique or lead["score"] > unique[marker]["score"]:
                    unique[marker] = lead
            result = list(unique.values())
            result.sort(key=lambda lead: (-lead["score"], lead["name"].casefold()))
            return result[:160]
        except (requests.RequestException, ValueError, KeyError) as exc:
            errors.append(str(exc)[:140])
    raise RuntimeError("Серверы карт временно не отвечают. Повтори поиск позже. " + " | ".join(errors))

FEEDS = {
    "Все проекты": "https://freelancehunt.com/projects.rss",
    "Создание сайтов": "https://freelancehunt.com/projects/skill/sozdanie-sayta-pod-klyuch/96.html.rss",
    "Дизайн сайтов": "https://freelancehunt.com/projects/skill/dizayn-saytov/43.html.rss",
}
MATCH_WORDS = ["сайт", "website", "web site", "landing", "лендинг", "лендінг", "wordpress", "tilda", "shopify", "woocommerce", "webflow", "вебсайт", "інтернет-магазин", "интернет-магазин", "редизайн", "вёрстк", "верстк", "веб-дизайн", "web design"]


@st.cache_data(ttl=12 * 60, show_spinner=False)
def fetch_rss_feed(url: str) -> list[dict]:
    resp = SESSION.get(url, timeout=20)
    resp.raise_for_status()
    parsed = feedparser.parse(resp.content)
    if parsed.bozo and not parsed.entries:
        raise ValueError("Формат RSS изменился")
    rows = []
    for entry in parsed.entries:
        title = re.sub(r"\s+", " ", html.unescape(entry.get("title", ""))).strip()
        description = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", entry.get("summary", "")))).strip()
        url = entry.get("link", "")
        if not safe_url(url):
            continue
        txt = (title + " " + description).lower()
        score = sum(3 if word in title.lower() else 1 for word in MATCH_WORDS if word in txt)
        if score == 0:
            continue
        dt = entry.get("published_parsed") or entry.get("updated_parsed")
        date = datetime(*dt[:6], tzinfo=timezone.utc) if dt else None
        rows.append({"id": "job-" + hashlib.sha1(url.encode()).hexdigest()[:16], "title": title,
                     "description": description, "url": url, "date": date, "score": score})
    return rows


def lead_csv(rows: list[dict], status: dict) -> bytes:
    keys = ["name", "category", "city", "address", "phone", "website", "social", "osm_url", "status"]
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=keys)
    writer.writeheader()
    for item in rows:
        writer.writerow({k: status.get(item["id"], "Новый") if k == "status" else item.get(k, "") for k in keys})
    return buf.getvalue().encode("utf-8-sig")


def clean_tel(phone: str) -> str:
    return re.sub(r"[^\d+]", "", phone or "")


def demo_html(lead: dict, variant: str, language: str = "uk") -> str:
    title = html.escape(lead["name"])
    address = html.escape(lead["address"])
    category = html.escape(lead["category"])
    tel = clean_tel(lead.get("phone", ""))
    map_url = html.escape(lead["osm_url"], quote=True)
    themes = {
        "Тёплый / Кафе": ("#ffbd81", "#321918", "#1d0e11", "#fcf3e7", "☕"),
        "Чистый / Магазин": ("#b1e1d0", "#16372c", "#0e1c19", "#f1fff9", "✦"),
        "Смелый / Универсальный": ("#bfb3ff", "#322364", "#15122c", "#f3eeff", "✳"),
    }
    accent, accent_dark, bg, text, symbol = themes[variant]
    translations = {
        "uk": {
            "call": "Зателефонувати ↗", "contacts": "Контакти ↓", "contacts_link": "Контакти ↗",
            "eyebrow": "Ваш новий цифровий простір", "hello": "Знайомтесь.",
            "intro": "Зручний сучасний сайт, де клієнти можуть дізнатися про вас, знайти контакти та зв’язатися за кілька секунд.",
            "more": "Детальніше ↓", "about": "Про нас", "important": "Усе важливе — на одному екрані.",
            "tile1": "Впізнаваний дизайн вашого бренду", "tile2": "Зручна мобільна версія", "tile3": "Швидкий доступ до контактів",
            "find": "Як нас знайти", "welcome": "Будемо раді знайомству.", "map": "Відкрити на карті ↗",
            "concept": "Концепція сайту", "disclaimer": "ДЕМО-КОНЦЕПТ — не офіційний сайт закладу; дані слід перевірити",
        },
        "en": {
            "call": "Call ↗", "contacts": "Contact ↓", "contacts_link": "Contact ↗",
            "eyebrow": "Your new online space", "hello": "Welcome to",
            "intro": "A mobile-friendly website concept to help customers learn about your business and get in touch.",
            "more": "Learn more ↓", "about": "About", "important": "Everything important, all in one place.",
            "tile1": "A recognisable brand experience", "tile2": "Mobile-friendly design", "tile3": "Easy contact options",
            "find": "Find us", "welcome": "We'd love to meet you.", "map": "Open map ↗",
            "concept": "Website concept", "disclaimer": "DEMO CONCEPT — not an official business website; details must be verified",
        },
    }
    d = translations[language if language in translations else "uk"]
    phone_button = f'<a class="btn" href="tel:{html.escape(tel,quote=True)}">{d["call"]}</a>' if tel else f'<a class="btn" href="#contacts">{d["contacts"]}</a>'
    return f'''<!doctype html>
<html lang="{language}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow"><title>Демо • {title}</title>
<style>
*{{box-sizing:border-box}}html{{scroll-behavior:smooth}}body{{margin:0;font-family:system-ui,-apple-system,Segoe UI,sans-serif;background:{bg};color:{text}}}
.nav{{max-width:1000px;margin:auto;padding:26px 22px;display:flex;justify-content:space-between;align-items:center;gap:14px}}
.logo{{font-weight:900;font-size:20px;letter-spacing:-.035em}}.nav a{{text-decoration:none;color:{text};font-size:13px;opacity:.82}}
.hero{{max-width:1000px;margin:0 auto;padding:56px 22px 70px;min-height:520px;display:flex;align-items:center}}
.wrap{{max-width:780px}}.eyebrow{{font-size:12px;letter-spacing:.2em;text-transform:uppercase;color:{accent};font-weight:800}}
h1{{font-size:clamp(46px,9vw,98px);letter-spacing:-.07em;line-height:1.02;margin:17px 0 20px;overflow-wrap:anywhere}}
.hi{{color:{accent}}}p{{color:{text};opacity:.72;line-height:1.7;font-size:17px;max-width:640px}}.btn{{background:{accent};color:{accent_dark};display:inline-flex;align-items:center;padding:16px 24px;border-radius:100px;text-decoration:none;font-weight:800;margin:15px 9px 0 0}}
.btn.secondary{{background:transparent;border:1px solid {accent};color:{text}}}
.section{{max-width:1000px;margin:auto;padding:52px 22px}}.section h2{{font-size:clamp(29px,6vw,51px);letter-spacing:-.055em;line-height:1.1}}
.grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:13px;margin-top:30px}}.tile{{padding:24px;background:rgba(255,255,255,.065);border:1px solid rgba(255,255,255,.09);border-radius:20px;min-height:145px}}.tile b{{font-size:24px;color:{accent}}}
.footer{{border-top:1px solid rgba(255,255,255,.1);margin-top:35px;padding:25px 22px;color:{text};opacity:.7;font-size:13px}}.disclaimer{{position:fixed;bottom:10px;left:10px;right:10px;text-align:center;background:rgba(8,9,17,.9);padding:9px 14px;border-radius:13px;color:#fff;font-size:11px;z-index:3}}
@media(max-width:600px){{.hero{{min-height:440px;padding:35px 22px 55px}}.grid{{grid-template-columns:1fr}}.section{{padding:34px 22px}}}}
</style></head><body>
<header class="nav"><span class="logo">{symbol} {title}</span><a href="#contacts">{d["contacts_link"]}</a></header>
<main><section class="hero"><div class="wrap"><span class="eyebrow">{d["eyebrow"]}</span>
<h1>{d["hello"]}<br><span class="hi">{title}</span></h1>
<p>{d["intro"]}</p>
{phone_button}<a class="btn secondary" href="#about">{d["more"]}</a></div></section>
<section class="section" id="about"><span class="eyebrow">{d["about"]}</span><h2>{d["important"]}</h2>
<div class="grid"><div class="tile"><b>01</b><p>{d["tile1"]}</p></div><div class="tile"><b>02</b><p>{d["tile2"]}</p></div><div class="tile"><b>03</b><p>{d["tile3"]}</p></div></div></section>
<section class="section" id="contacts"><span class="eyebrow">{d["find"]}</span><h2>{d["welcome"]}</h2>
<p>{address} • {category}</p><a class="btn" href="{map_url}" target="_blank" rel="noopener">{d["map"]}</a>
{phone_button}</section></main><footer class="footer">{title} · {d["concept"]}</footer>
<div class="disclaimer">{d["disclaimer"]}</div></body></html>'''


def message_for_lead(lead: dict, tone: str, language: str = "Українська") -> str:
    name = lead["name"]
    if language == "English":
        if tone == "Короткий":
            return (f"Hello! I came across {name} and I design modern, mobile-friendly websites for small businesses. "
                    "Would you be interested in seeing a sample website concept for your business?")
        return (f"Hello! I noticed {name} and wanted to share an idea.\n\n"
                "I design mobile-friendly websites that make it easier for customers to find services, menus and contact details. "
                "I can prepare a no-obligation sample concept. May I send you an example?")
    if language == "Русский":
        if tone == "Короткий":
            return (f"Здравствуйте! Увидел «{name}». Я создаю современные сайты для малого бизнеса. "
                    "Могу показать, как мог бы выглядеть ваш сайт. Интересно посмотреть? 🙂")
        return (f"Здравствуйте! Увидел «{name}» и хотел предложить идею.\n\n"
                "Я создаю удобные сайты для телефона с услугами, меню и контактами. "
                "Могу показать пример дизайна без обязательств. Можно прислать? 🙂")
    if tone == "Короткий":
        return (f"Доброго дня! Звернув увагу на «{name}». Я створюю сучасні сайти для малого бізнесу. "
                "Можу показати, як міг би виглядати ваш сайт. Цікаво подивитися? 🙂")
    return (f"Доброго дня! Побачив «{name}» і хотів запропонувати ідею.\n\n"
            "Я розробляю адаптивні сайти, які допомагають клієнтам швидко знайти меню, послуги та контакти. "
            "Можу підготувати демо-концепцію без зобов'язань. Чи можна надіслати приклад? 🙂")


if "lead_status" not in st.session_state:
    st.session_state.lead_status = {}
if "chosen_lead" not in st.session_state:
    st.session_state.chosen_lead = ""

mode = st.radio("Режим поиска", ["🏪 Заведения из карт", "🔥 Заказы на сайты"], horizontal=True, label_visibility="collapsed")
st.markdown(" ")

if mode.startswith("🏪"):
    st.markdown('<div class="section-head">Найти потенциальных клиентов</div>', unsafe_allow_html=True)
    st.caption("Ищем публично отмеченные организации в OpenStreetMap, а не закрытые данные Google или 2ГИС.")
    country_choice = st.selectbox("🌍 Країна пошуку", list(COUNTRIES.keys()), index=0)
    country_code, country_label, preset_cities = COUNTRIES[country_choice]
    if country_code == "ua":
        region_choice = st.selectbox("📍 Область України (необов'язково)", list(UKRAINE_REGIONS.keys()), index=0)
        region = "" if region_choice.startswith("Усі області") else ("" if region_choice == "м. Київ" else region_choice)
        cities = list(UKRAINE_REGIONS[region_choice]) if region_choice != "Усі області / Не вказувати" else list(preset_cities)
        st.caption("🇺🇦 Можна шукати будь-яке місто або селище України, навіть якщо його немає в списку.")
    else:
        region = ""
        cities = list(preset_cities)
    city_select = st.selectbox("Місто / населений пункт", cities + ["✍️ Ввести своє місто…"], index=0)
    with st.form("search_business_form", border=True):
        other_city = st.text_input("Введи населений пункт", placeholder="Наприклад, Синельникове або Нікополь", max_chars=70) if city_select == "✍️ Ввести своє місто…" else ""
        city = (other_city if city_select == "✍️ Ввести своє місто…" else city_select).strip()
        category = st.selectbox("Сфера бізнесу", list(CATEGORY.keys()))
        radius = st.select_slider("Радіус пошуку", options=[1000, 2000, 3000, 5000], value=3000, format_func=lambda x: f"{x/1000:g} км")
        start = st.form_submit_button("🔎 Знайти заклади", type="primary", use_container_width=True)
    if start:
        if not city or len(city) > 70:
            st.error("Введи назву міста або селища (не довше 70 символів).")
        else:
            with st.spinner("Перевіряю карту та збираю публічні картки…"):
                try:
                    leads = fetch_businesses(city, category, radius, country_code, country_label, region)
                    st.session_state.last_leads = leads
                    st.session_state.search_label = f"{country_label} · {region + ' · ' if region else ''}{city} · {category} · {radius//1000} км"
                    st.session_state.chosen_lead = ""
                    st.session_state.last_country_code = country_code
                except Exception as exc:
                    st.error("Пошук не вдався: " + str(exc))
    leads = st.session_state.get("last_leads", None)
    if leads is None:
        st.info("Выбери город и категорию, затем нажми «Найти заведения». Например: Дніпро → Кафе и рестораны.")
    else:
        st.caption(st.session_state.get("search_label", ""))
        m1, m2, m3 = st.columns(3)
        m1.metric("Найдено", len(leads))
        m2.metric("Сайт не указан", sum(not l["website"] for l in leads))
        m3.metric("Есть контакты", sum(bool(l["phone"] or l["social"]) for l in leads))
        st.caption("⚠️ «Сайт не указан» означает отсутствие ссылки в OpenStreetMap, а не отсутствие сайта в интернете.")
        view = st.segmented_control("Фильтр", ["Без указанного сайта", "Все", "С контактами"], default="Без указанного сайта")
        keyword = st.text_input("Фильтр по названию", placeholder="Введите название заведения…")
        filtered = [l for l in leads if (view != "Без указанного сайта" or not l["website"]) and
                    (view != "С контактами" or l["phone"] or l["social"]) and keyword.casefold() in l["name"].casefold()]
        st.caption(f"Подходит: {len(filtered)} · показываем первые 65")
        if not filtered:
            st.info("По выбранному фильтру ничего нет. Попробуй вкладку «Все» или другой радиус.")
        for lead in filtered[:65]:
            with st.container(border=True):
                st.markdown(f'<div class="lead-title">{html.escape(lead["name"])}</div>', unsafe_allow_html=True)
                badge = "<span class='pill weak'>Сайт в карте не указан</span>" if not lead["website"] else "<span class='pill strong'>Сайт указан</span>"
                st.markdown(badge + f' <span class="pill">{html.escape(lead["category"])}</span>', unsafe_allow_html=True)
                st.markdown(f'<div class="lead-meta">📍 {html.escape(lead["address"])}<br>📞 {html.escape(lead["phone"] or "Не указан")}</div>', unsafe_allow_html=True)
                buttons = st.columns(2)
                buttons[0].link_button("🗺 Карта", lead["osm_url"], use_container_width=True)
                if lead["social"]:
                    buttons[1].link_button("📷 Соцсеть", lead["social"], use_container_width=True)
                elif lead["website"]:
                    buttons[1].link_button("🌐 Сайт", lead["website"], use_container_width=True)
                elif lead["phone"]:
                    buttons[1].markdown(f'<a href="tel:{html.escape(clean_tel(lead["phone"]), quote=True)}" style="display:inline-flex;align-items:center;justify-content:center;border:1px solid #425574;border-radius:10px;padding:11px;width:100%;text-decoration:none;color:#eaf0ff;">📞 Позвонить</a>', unsafe_allow_html=True)
                else:
                    buttons[1].caption("Других контактов нет")
                bottom = st.columns(2)
                status_options = ["Новый", "Написал", "Обсуждаем", "Не подходит"]
                old = st.session_state.lead_status.get(lead["id"], "Новый")
                value = bottom[0].selectbox("Статус", status_options, index=status_options.index(old), key=f"status_{lead['id']}", label_visibility="collapsed")
                st.session_state.lead_status[lead["id"]] = value
                if bottom[1].button("✨ Создать демо", key=f"demo_{lead['id']}", use_container_width=True):
                    st.session_state.chosen_lead = lead["id"]
        st.download_button("⬇️ Скачать найденные заведения (CSV)", data=lead_csv(filtered, st.session_state.lead_status), file_name="leadradar_businesses.csv", mime="text/csv", use_container_width=True)
        st.markdown('<div class="section-head">✨ Демо-сайт за пару нажатий</div>', unsafe_allow_html=True)
        if leads:
            all_leads = {l["id"]: l for l in leads}
            ordered_ids = list(all_leads)
            selected_id = st.session_state.chosen_lead if st.session_state.chosen_lead in all_leads else ordered_ids[0]
            choose = st.selectbox("Заведение для демо", ordered_ids, index=ordered_ids.index(selected_id), format_func=lambda i: all_leads[i]["name"])
            chosen = all_leads[choose]
            theme = st.selectbox("Стиль демо", ["Тёплый / Кафе", "Чистый / Магазин", "Смелый / Универсальный"])
            demo = demo_html(chosen, theme, "uk" if st.session_state.get("last_country_code", "ua") == "ua" else "en")
            st.caption("Демонстрационная концепция, не действующий официальный сайт. Содержимое и контактные данные требуют проверки.")
            with st.expander("👀 Посмотреть демо прямо здесь", expanded=False):
                components.html(demo, height=630, scrolling=True)
            st.download_button("💾 Скачать готовый демо-сайт (.html)", data=demo.encode("utf-8"), file_name="demo-site-" + str(chosen["id"].replace("/", "-")) + ".html", mime="text/html", use_container_width=True)
            st.markdown('<div class="section-head">💬 Сообщение владельцу</div>', unsafe_allow_html=True)
            tone = st.radio("Тон", ["Короткий", "Более подробный"], horizontal=True)
            msg_language = st.selectbox("Мова повідомлення", ["Українська", "Русский", "English"], index=0 if st.session_state.get("last_country_code", "ua") == "ua" else 2)
            sample_message = message_for_lead(chosen, tone, msg_language)
            st.text_area("Текст для Instagram / Telegram", value=sample_message, height=170, help="Скопируй и отправь вручную. Не заявляй, что у бизнеса точно нет сайта.")
            st.caption("Отправляй вручную и персонально, без массовых рассылок. Прежде чем предлагать сайт, проверь организацию и её официальный сайт.")
else:
    st.markdown('<div class="section-head">Заказы от людей, которым уже нужен сайт</div>', unsafe_allow_html=True)
    st.caption("🇺🇦 Українські проєкти Freelancehunt: прямий попит на створення сайтів, але конкуренція вища.")
    with st.form("jobs_form", border=True):
        feed_names = st.multiselect("Источники", list(FEEDS.keys()), default=["Все проекты", "Создание сайтов"])
        phrase = st.text_input("Поиск в объявлениях", placeholder="Например: магазин, кафе, WordPress")
        minimum = st.slider("Релевантность", 1, 10, value=2)
        submit_jobs = st.form_submit_button("🔥 Найти заказы", type="primary", use_container_width=True)
    if submit_jobs:
        if not feed_names:
            st.warning("Выбери хотя бы один источник")
        else:
            results, errors = {}, []
            with st.spinner("Читаю открытые RSS-ленты…"):
                for name in feed_names:
                    try:
                        for item in fetch_rss_feed(FEEDS[name]):
                            results[item["url"]] = item
                    except Exception as ex:
                        errors.append(f"{name}: {str(ex)[:130]}")
            st.session_state.last_jobs = sorted(results.values(), key=lambda r: (r["score"], r["date"] or datetime(1970,1,1,tzinfo=timezone.utc)), reverse=True)
            st.session_state.last_job_errors = errors
    rows = st.session_state.get("last_jobs", None)
    if rows is None:
        st.info("Нажми «Найти заказы», чтобы увидеть опубликованные заявки.")
    else:
        for error in st.session_state.get("last_job_errors", []):
            st.warning(error)
        visible = [r for r in rows if r["score"] >= minimum and phrase.casefold() in (r["title"] + " " + r["description"]).casefold()]
        st.metric("Подходящие проекты", len(visible))
        for job in visible[:60]:
            with st.container(border=True):
                st.markdown(f'<div class="lead-title">{html.escape(job["title"])}</div>', unsafe_allow_html=True)
                date = job["date"].strftime("%d.%m.%Y") if job["date"] else "Дата не указана"
                st.markdown(f'<span class="pill">⚡ Релевантность {job["score"]}</span> <span class="pill">{date}</span>', unsafe_allow_html=True)
                st.markdown('<div class="lead-note">'+html.escape(job["description"][:420])+'</div>', unsafe_allow_html=True)
                st.link_button("Открыть заказ ↗", job["url"], use_container_width=True)
        if not visible:
            st.info("Подходящих заказов нет. Уменьши релевантность или убери текстовый фильтр.")
        st.caption("Проверяй, открыт ли проект: публикация в RSS не гарантирует актуальность задания.")
        st.markdown("**Шаблон первого отклика:**")
        st.code("Доброго дня! Побачив ваше завдання щодо створення сайту. Можу запропонувати адаптивний дизайн та зрозумілу структуру. Чи можете поділитися прикладом сайту, який вам подобається, і бажаними термінами?", language=None)

st.markdown('''<div class="footer-notice">Источник заведений: © OpenStreetMap contributors (ODbL), через Overpass API. Поиск города: Nominatim. Источник заказов: открытые RSS Freelancehunt. Отсутствие сайта или контакта в OpenStreetMap не подтверждает фактического отсутствия. Сервис не рассылает сообщения, не обходит ограничения сайтов и не продаёт персональные данные.</div>''', unsafe_allow_html=True)
