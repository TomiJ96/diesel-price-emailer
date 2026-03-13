"""
Brisbane Diesel Price Daily Emailer — Skip Trans
Fetches diesel prices from the QLD Government Fuel Price API
and sends a daily email via Microsoft 365.

MOCK MODE: Set USE_MOCK_DATA = True to test without an API token.
LIVE MODE: Set USE_MOCK_DATA = False once you have your API token.
"""

import os
import requests
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

# ==============================================================================
# TOGGLE — switch to False once your QLD Fuel API token is ready
# ==============================================================================
USE_MOCK_DATA = False

# ==============================================================================
# CREDENTIALS — loaded from GitHub Secrets (never hard-code these)
# ==============================================================================
FUEL_API_TOKEN = os.environ.get("FUEL_API_TOKEN", "")
M365_EMAIL     = os.environ.get("M365_EMAIL",     "")
M365_PASSWORD  = os.environ.get("M365_PASSWORD",  "")
_recipients    = os.environ.get("RECIPIENTS",     "")
RECIPIENTS     = [r.strip() for r in _recipients.split(",")]

# ==============================================================================
# STATIONS
# Site IDs are placeholders — replace once you have your API token:
#   1. Set USE_MOCK_DATA = False and FUEL_API_TOKEN to your token
#   2. Set FIND_STATIONS = True and run the workflow manually
#   3. Check the Action log for the printed station list
#   4. Copy the correct Site IDs in below
#   5. Set FIND_STATIONS = False
# ==============================================================================
MONITORED_STATIONS = [
    {"name": "Pacific Fuel - Blacksoil",  "site_id": 61402913, "region_id": 1},
    {"name": "Pacific Fuel - Rocklea",    "site_id": 61401427, "region_id": 1},
    {"name": "Pacific Fuel - Yatala",     "site_id": 61477080, "region_id": 1},
    {"name": "Pacific Fuel - Hemmant",    "site_id": 61478256, "region_id": 1},
    {"name": "United Petrol - Archerfield",      "site_id": 61477778, "region_id": 1},
    {"name": "United Petrol - Brendale",         "site_id": 61477709, "region_id": 1},
    {"name": "United Petrol - Loganlea",         "site_id": 61401773, "region_id": 1},
    {"name": "United Petrol - Park Ridge",       "site_id": 61402439, "region_id": 1},
]

SUPPLIER_DISCOUNTS = {
    "Pacific": 9.0,
    "United":  4.0,
}

DIESEL_FUEL_IDS = {
    2:    "Unleaded 91",
    3:    "Diesel",
    5:    "Unleaded 95",
    6:    "ULSD",
    8:    "Unleaded 98",
    12:   "Ethanol 10",
    14:   "Premium Diesel",
    1000: "Diesel/Premium",
}
FIND_STATIONS    = False   # set True temporarily to discover real Site IDs
M365_SMTP_SERVER = "smtp.office365.com"
M365_SMTP_PORT   = 587
API_BASE         = "https://fppdirectapi-prod.fuelpricesqld.com.au"

# ==============================================================================
# MOCK DATA — realistic prices used when USE_MOCK_DATA = True
# Update these occasionally to keep test emails looking realistic
# ==============================================================================
MOCK_PRICES = {
    61402913: 186.7,   # Pacific Fuel Blacksoil
    61401427: 187.9,   # Pacific Fuel Rocklea
    61477080: 185.5,   # Pacific Fuel Yatala
    61478256: 189.4,   # Pacific Fuel Hemmant
    61477778: 188.1,   # United Archerfield
    61477709: 191.3,   # United Brendale
    61401773: 187.5,   # United Loganlea
    61402439: 188.8,   # United Park Ridge
}


def get_prices(region_id=1):
    headers = {
        "Authorization": f"FPDAPI SubscriberToken={FUEL_API_TOKEN}",
        "Content-Type": "application/json",
    }
    url = f"{API_BASE}/Price/GetSitesPrices?countryId=21&geoRegionLevel=3&geoRegionId={region_id}"
    resp = requests.get(url, headers=headers, timeout=15)
    resp.raise_for_status()
    return resp.json().get("SitePrices", [])


def get_all_sites(region_id=1):
    headers = {
        "Authorization": f"FPDAPI SubscriberToken={FUEL_API_TOKEN}",
        "Content-Type": "application/json",
    }
    url = f"{API_BASE}/Subscriber/GetFullSiteDetails?countryId=21&geoRegionLevel=3&geoRegionId={region_id}"
    resp = requests.get(url, headers=headers, timeout=15)
    resp.raise_for_status()
    return resp.json().get("S", [])


def find_diesel_price(prices, site_id):
    matches = []
    for entry in prices:
        if entry.get("SiteId") == site_id and entry.get("FuelId") in DIESEL_FUEL_IDS:
            price = round(entry["Price"] / 10.0, 1)
            if price <= 500:
                matches.append({
                    "price": price,
                    "fuel_type": DIESEL_FUEL_IDS[entry["FuelId"]]
                })
    if not matches:
        return None
    return min(matches, key=lambda x: x["price"])


def build_results():
    """Return list of {name, price} dicts, using mock or live data."""
    if USE_MOCK_DATA:
        print("ℹ️  Running in MOCK DATA mode — prices are simulated.")
        return [
            {"name": s["name"], "price": round(MOCK_PRICES.get(s["site_id"]) - (9.0 if s["name"].startswith("Pacific") else 4.0), 1), "fuel_type": "Diesel"}

            for s in MONITORED_STATIONS
        ]


    region_ids = set(s["region_id"] for s in MONITORED_STATIONS)
    all_prices = {rid: get_prices(rid) for rid in region_ids}
    results = []
    for station in MONITORED_STATIONS:
        price = find_diesel_price(all_prices[station["region_id"]], station["site_id"])
        p = price["price"] if price else None
        t = price["fuel_type"] if price else None
        discount = SUPPLIER_DISCOUNTS["Pacific"] if station["name"].startswith("Pacific") else SUPPLIER_DISCOUNTS["United"]
        discounted = round(p - discount, 1) if p else None
        results.append({"name": station["name"], "price": discounted, "fuel_type": t})

        print(f"  {station['name']}: {f'{p:.1f}c/L ({t})' if p else 'not found'}")
    return results


def build_html_email(results, fetch_time):
    date_str = fetch_time.strftime("%A, %d %B %Y")
    time_str = fetch_time.strftime("%I:%M %p")
    mode_banner = ""
    if USE_MOCK_DATA:
        mode_banner = """
        <div style="background:#fff3cd; border:1px solid #ffc107; border-radius:6px;
                    padding:10px 16px; margin-bottom:16px; font-size:12px; color:#856404;">
            ⚠️ <strong>TEST MODE</strong> — prices are simulated.
            Set <code>USE_MOCK_DATA = False</code> once your API token is ready.
        </div>"""

    valid = [r["price"] for r in results if r["price"]]
    min_p = min(valid) if valid else None
    max_p = max(valid) if valid else None

    rows = ""
    for r in sorted(results, key=lambda x: (x["price"] is None, x["price"])):
        price = r["price"]
        if price is not None:
            fuel_type = r.get("fuel_type") or ""
            price_str = f"{price:.1f}c/L <span style='font-size:10px; color:#999;'>({fuel_type})</span>"
            if price == min_p:
                colour, weight, badge = "#28a745", "font-weight:bold;", " ✅"
            elif price == max_p:
                colour, weight, badge = "#dc3545", "", " 🔴"
            else:
                colour, weight, badge = "#333333", "", ""
        else:
            price_str, colour, weight, badge = "Not reported", "#999999", "", ""

        rows += f"""
        <tr>
            <td style="padding:10px 16px; border-bottom:1px solid #eee;">
                {r['name']}{badge}
            </td>
            <td style="padding:10px 16px; border-bottom:1px solid #eee;
                       text-align:right; color:{colour}; {weight}">
                {price_str}
            </td>
        </tr>"""

    return f"""
    <html><body style="font-family:Arial,sans-serif; background:#f5f5f5; padding:20px;">
    <div style="max-width:520px; margin:0 auto;">
        {mode_banner}
        <div style="background:#1a4b8c; padding:20px 24px; border-radius:8px 8px 0 0;">
            <h2 style="color:#fff; margin:0; font-size:20px;">⛽ Daily Diesel Prices</h2>
            <p style="color:#c8d8f0; margin:6px 0 0; font-size:13px;">
                {date_str} &nbsp;|&nbsp; Fetched at {time_str} AEST
            </p>
        </div>
        <div style="background:#fff; border-radius:0 0 8px 8px;
                    box-shadow:0 2px 8px rgba(0,0,0,0.08);">
            <table style="width:100%; border-collapse:collapse;">
                <thead>
                    <tr style="background:#f0f4fa;">
                        <th style="padding:10px 16px; text-align:left; font-size:12px;
                                   color:#555; text-transform:uppercase; letter-spacing:0.5px;">
                            Station
                        </th>
                        <th style="padding:10px 16px; text-align:right; font-size:12px;
                                   color:#555; text-transform:uppercase; letter-spacing:0.5px;">
                            Diesel
                        </th>
                    </tr>
                </thead>
                <tbody>{rows}</tbody>
            </table>
            <div style="padding:14px 16px; background:#f9f9f9; border-top:1px solid #eee;
                        border-radius:0 0 8px 8px;">
                <p style="margin:0; font-size:11px; color:#999;">
                    Prices in cents per litre (c/L). ✅ = cheapest &nbsp; 🔴 = most expensive.<br>
                    Source: Queensland Government Fuel Price Reporting API.
                </p>
            </div>
        </div>
    </div>
    </body></html>"""


def build_plain_text(results, fetch_time):
    date_str = fetch_time.strftime("%A, %d %B %Y")
    lines = [
        "Skip Trans — Daily Diesel Prices",
        f"{date_str}",
        "=" * 40,
    ]
    if USE_MOCK_DATA:
        lines.append("⚠ TEST MODE — prices are simulated\n")
    for r in sorted(results, key=lambda x: (x["price"] is None, x["price"])):
        price_str = f"{r['price']:.1f}c/L" if r["price"] else "Not reported"
        lines.append(f"{r['name']:<30} {price_str}")
    lines.append("\nSource: Queensland Government Fuel Price Reporting API")
    return "\n".join(lines)


def write_prices_json(results, fetch_time):
    """Write prices.json so the GitHub Pages dashboard stays current."""
    import json
    payload = {
        "last_updated":     fetch_time.strftime("%Y-%m-%dT%H:%M:%S"),
        "last_updated_str": fetch_time.strftime("%A, %d %B %Y at %I:%M %p"),
        "is_mock":          USE_MOCK_DATA,
        "stations": [
    {
        "name":      r["name"],
        "price":     r["price"],
        "price_str": f"{r['price']:.1f}c/L" if r["price"] else "Not reported",
        "fuel_type": r.get("fuel_type") or "",
    }
    for r in results
],
    }
    with open("prices.json", "w") as f:
        json.dump(payload, f, indent=2)
    print("✅ prices.json updated")


def send_email(html_body, plain_body, fetch_time):
    date_str = fetch_time.strftime("%d %b %Y")
    subject  = f"{'[TEST] ' if USE_MOCK_DATA else ''}Daily Diesel Prices – {date_str}"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = M365_EMAIL
    msg["To"]      = ", ".join(RECIPIENTS)
    msg.attach(MIMEText(plain_body, "plain"))
    msg.attach(MIMEText(html_body,  "html"))

    with smtplib.SMTP(M365_SMTP_SERVER, M365_SMTP_PORT) as server:
        server.ehlo()
        server.starttls()
        server.login(M365_EMAIL, M365_PASSWORD)
        server.sendmail(M365_EMAIL, RECIPIENTS, msg.as_string())

    print(f"✅ Email sent to: {', '.join(RECIPIENTS)}")


def discover_stations():
    """Print all Brisbane stations with their Site IDs. Set FIND_STATIONS=True to use."""
    print("🔍 Discovering Brisbane stations...\n")
    sites  = get_all_sites(region_id=1)
    prices = get_prices(region_id=1)
    diesel_ids = {p["SiteId"] for p in prices if p.get("FuelId") in DIESEL_FUEL_IDS}
    print(f"{'SiteId':<12} {'Has Diesel':<12} Name")
    print("-" * 65)
    for s in sorted(sites, key=lambda x: x.get("N", "")):
        tag = "✓" if s.get("S") in diesel_ids else ""
        print(f"{s.get('S'):<12} {tag:<12} {s.get('N', 'Unknown')}")

def main():
    if FIND_STATIONS:
        discover_stations()
        return

    from datetime import timezone, timedelta
    aest = timezone(timedelta(hours=10))
    fetch_time = datetime.now(tz=aest)

    print(f"📡 Fetching diesel prices — {fetch_time.strftime('%d %b %Y %H:%M')}")

    results = build_results()
    write_prices_json(results, fetch_time)
    html_body = build_html_email(results, fetch_time)
    plain_body = build_plain_text(results, fetch_time)
    if fetch_time.hour == 4:
        send_email(html_body, plain_body, fetch_time)
        print("📧 Email sent (3am run)")
    else:
        print("⏭ Prices updated — no email (non-morning run)")


if __name__ == "__main__":
    main()
