#!/usr/bin/env python3
"""
Brave API Feed Discovery & Paywall Verification

Uses the Brave Search API to:
  1. Discover new RSS feed candidates by searching for topics/categories
  2. Verify whether existing or candidate feeds are behind paywalls
  3. Optionally add verified, free feeds to discovery_pool.json

Usage:
  export BRAVE_API_KEY=your_key
  python brave_discovery.py --mode both --add-to-pool
  python brave_discovery.py --mode verify
  python brave_discovery.py --mode discover --categories tech science
"""

import argparse
import gzip
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

BRAVE_API_URL = "https://api.search.brave.com/res/v1/web/search"

# Hard-coded known-paywall domains for fast first-pass filtering.
# Only include domains where virtually ALL content requires a subscription.
# medium.com and substack.com are NOT here — they host many free RSS feeds.
KNOWN_PAYWALLS = {
    "nytimes.com",
    "wsj.com",
    "ft.com",
    "bloomberg.com",
    "economist.com",
    "newyorker.com",
    "washingtonpost.com",
    "theatlantic.com",
    "wired.com",
    "technologyreview.com",
    "hbr.org",
    "foreignaffairs.com",
    "spectator.co.uk",
    "thetimes.co.uk",
    "telegraph.co.uk",
}

# Hard paywall phrases — unambiguous access-denial language.
# Deliberately narrow to avoid false positives from adblock nag screens.
PAYWALL_PHRASES = [
    "subscriber only",
    "subscribe to read",
    "subscribe to continue reading",
    "sign in to read",
    "log in to read",
    "members only",
    "for subscribers only",
    "paywall",
    "subscription required",
    "register to read",
    "exclusive for subscribers",
    "free articles left",
    "articles remaining this month",
    "metered paywall",
]

# Phrases that indicate an adblock detection wall, NOT a content paywall.
# If these appear alongside paywall-ish language, we treat the site as free.
ADBLOCK_PHRASES = [
    "ad blocker",
    "adblocker",
    "adblock",
    "disable your ad",
    "turn off your ad",
    "whitelist",
    "we noticed you",
    "please allow ads",
    "ad-free experience",
    "support us by disabling",
    "ad revenue",
]

# Search queries per category for discovering new feeds
DISCOVERY_QUERIES = {
    "tech": [
        'technology blog "RSS feed" analysis in-depth -site:medium.com -site:substack.com',
        'software engineering "RSS" blog feed -paywall -subscription',
        '"RSS feed" "open source" technology news free',
    ],
    "science": [
        'science blog "RSS feed" accessible free open-access',
        '"RSS" science research news free -paywall',
        'academic science writing RSS free articles',
    ],
    "culture": [
        'culture criticism "RSS feed" longform free articles',
        '"RSS" arts literature criticism blog free',
        'cultural commentary RSS independent blog',
    ],
    "environment": [
        'climate environment journalism "RSS feed" free',
        '"RSS" environmental news analysis free -paywall',
        'sustainability blog RSS free content',
    ],
    "economics": [
        'economics policy analysis "RSS feed" free',
        '"RSS" economic research blog accessible -paywall',
        'political economy blog RSS free articles',
    ],
    "health": [
        'public health science blog "RSS feed" evidence-based free',
        '"RSS" medical research news free accessible',
    ],
    "philosophy": [
        'philosophy blog "RSS feed" free articles',
        '"RSS" ethics philosophy commentary free',
    ],
}


# ---------------------------------------------------------------------------
# Brave Search
# ---------------------------------------------------------------------------

def brave_search(query: str, api_key: str, count: int = 10) -> dict:
    """Execute a Brave Web Search and return the parsed JSON response."""
    params = urllib.parse.urlencode({
        "q": query,
        "count": min(count, 20),
        "text_decorations": "false",
        "search_lang": "en",
    })
    url = f"{BRAVE_API_URL}?{params}"
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "X-Subscription-Token": api_key,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read()
            if resp.info().get("Content-Encoding") == "gzip":
                raw = gzip.decompress(raw)
            return json.loads(raw)
    except urllib.error.HTTPError as e:
        print(f"    [HTTP {e.code}] Brave API error for query: {query!r}")
        return {}
    except Exception as e:
        print(f"    [Error] Brave search failed: {e}")
        return {}


# ---------------------------------------------------------------------------
# Paywall Detection
# ---------------------------------------------------------------------------

def check_paywall(domain: str, api_key: str) -> dict:
    """
    Determine whether a domain is paywalled.

    Strategy:
      1. Fast lookup in known-paywall list
      2. Search for recent site pages and scan snippets for paywall phrases
      3. Explicit paywall-keyword search for the domain
    """
    clean = domain.replace("www.", "")
    if clean in KNOWN_PAYWALLS:
        return {"paywalled": True, "evidence": "known paywall list", "confidence": "high"}

    # --- pass 2: scan organic snippets ---
    results = brave_search(f"site:{domain}", api_key, count=5)
    web_results = results.get("web", {}).get("results", [])

    if web_results:
        all_text = " ".join(
            (r.get("description", "") + " " + r.get("title", "")).lower()
            for r in web_results
        )
        found = [p for p in PAYWALL_PHRASES if p in all_text]
        if found:
            # Before flagging: check whether this looks like an adblock wall,
            # not a content paywall. Adblock messages often contain subscribe-
            # adjacent language but aren't restricting content access.
            adblock_signals = [p for p in ADBLOCK_PHRASES if p in all_text]
            if adblock_signals:
                return {
                    "paywalled": False,
                    "evidence": f"adblock wall only (not a content paywall): {', '.join(adblock_signals)}",
                    "confidence": "medium",
                }
            return {
                "paywalled": True,
                "evidence": f"snippet phrases: {', '.join(found)}",
                "confidence": "medium",
            }

    # --- pass 3: explicit paywall search ---
    pw_results = brave_search(
        f'site:{domain} "subscribe" OR "paywall" OR "sign in to read"',
        api_key,
        count=3,
    )
    pw_text = " ".join(
        (r.get("description", "") + " " + r.get("title", "")).lower()
        for r in pw_results.get("web", {}).get("results", [])
    )
    found_pw = [p for p in PAYWALL_PHRASES if p in pw_text]
    if found_pw:
        adblock_signals = [p for p in ADBLOCK_PHRASES if p in pw_text]
        if adblock_signals:
            return {
                "paywalled": False,
                "evidence": f"adblock wall only: {', '.join(adblock_signals)}",
                "confidence": "medium",
            }
        return {
            "paywalled": True,
            "evidence": f"paywall search: {', '.join(found_pw)}",
            "confidence": "medium",
        }

    return {"paywalled": False, "evidence": "no paywall indicators found", "confidence": "medium"}


# ---------------------------------------------------------------------------
# Feed URL verification
# ---------------------------------------------------------------------------

def extract_feed_links_from_html(site_url: str) -> list:
    """Scrape <link rel=alternate type=application/rss+xml> tags from a homepage."""
    try:
        req = urllib.request.Request(
            site_url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; feed-discovery/1.0)"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            html = resp.read().decode("utf-8", errors="replace")
        pattern = (
            r'<link[^>]+type=["\']application/(?:rss|atom)\+xml["\'][^>]*'
            r'href=["\']([^"\']+)["\']'
        )
        return re.findall(pattern, html, re.IGNORECASE)
    except Exception:
        return []


def verify_feed(url: str) -> dict:
    """Fetch a URL and confirm it returns a valid RSS/Atom feed."""
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; feed-verifier/1.0)"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            content_type = resp.headers.get("Content-Type", "").lower()
            raw = resp.read(65536)

        ct_ok = any(ct in content_type for ct in ["rss", "atom", "xml", "feed"])

        try:
            root = ET.fromstring(raw)
            tag = root.tag.lower()
            xml_ok = (
                "rss" in tag
                or "feed" in tag
                or root.find("channel") is not None
                or root.find("{http://www.w3.org/2005/Atom}entry") is not None
            )
        except ET.ParseError:
            xml_ok = False

        return {"valid": ct_ok or xml_ok, "accessible": True, "content_type": content_type}

    except urllib.error.HTTPError as e:
        return {"valid": False, "accessible": False, "error": f"HTTP {e.code}"}
    except Exception as e:
        return {"valid": False, "accessible": False, "error": str(e)}


def find_valid_feed_url(site_url: str, netloc: str) -> str | None:
    """
    Try several strategies to locate a working RSS feed URL for a site.
    Returns the first verified feed URL, or None.
    """
    # Strategy 1: scrape <link> tags
    feed_links = extract_feed_links_from_html(site_url)
    for link in feed_links:
        if not link.startswith("http"):
            link = site_url.rstrip("/") + "/" + link.lstrip("/")
        v = verify_feed(link)
        if v["valid"]:
            return link
        time.sleep(0.1)

    # Strategy 2: common URL patterns
    common_paths = ["/feed", "/rss", "/feed.xml", "/atom.xml", "/rss.xml", "/feeds/posts/default"]
    for path in common_paths:
        candidate = f"https://{netloc}{path}"
        v = verify_feed(candidate)
        if v["valid"]:
            return candidate
        time.sleep(0.1)

    return None


# ---------------------------------------------------------------------------
# Pool helpers
# ---------------------------------------------------------------------------

def domain_in_pool(domain: str, pool: dict) -> bool:
    for feed in pool["feeds"]:
        existing = urllib.parse.urlparse(feed.get("htmlUrl", "")).netloc.replace("www.", "")
        if domain == existing:
            return True
    return False


def infer_quality(description: str) -> int:
    desc = description.lower()
    score = 5
    if any(w in desc for w in ["research", "analysis", "academic", "peer-reviewed", "evidence"]):
        score += 2
    if any(w in desc for w in ["longform", "in-depth", "investigation", "journal"]):
        score += 1
    if any(w in desc for w in ["personal", "newsletter", "independent"]):
        score += 1
    if any(w in desc for w in ["clickbait", "viral", "trending"]):
        score -= 2
    return max(1, min(10, score))


# ---------------------------------------------------------------------------
# Core operations
# ---------------------------------------------------------------------------

def verify_pool(pool: dict, api_key: str) -> list:
    """Check every feed in the pool for paywall status."""
    findings = []
    total = len(pool["feeds"])
    print(f"Checking {total} feeds for paywall status...\n")

    for i, feed in enumerate(pool["feeds"], 1):
        domain = urllib.parse.urlparse(feed.get("htmlUrl", "")).netloc.replace("www.", "")
        if not domain:
            continue

        print(f"  [{i}/{total}] {feed['title']} ({domain})")
        result = check_paywall(domain, api_key)
        time.sleep(0.4)

        findings.append({
            "title": feed["title"],
            "domain": domain,
            "xmlUrl": feed["xmlUrl"],
            "paywalled": result["paywalled"],
            "evidence": result["evidence"],
            "confidence": result["confidence"],
        })

        label = "PAYWALLED" if result["paywalled"] else "free"
        print(f"    -> {label} ({result['confidence']}): {result['evidence']}")

    return findings


def discover_feeds(categories: list, api_key: str, pool: dict) -> list:
    """Search Brave for new RSS feeds across given categories."""
    new_feeds = []

    for category in categories:
        queries = DISCOVERY_QUERIES.get(category, [f'"RSS feed" {category} free articles'])
        print(f"\n[{category}]")

        seen_domains = set()
        for query in queries:
            print(f"  Query: {query!r}")
            results = brave_search(query, api_key, count=10)
            web_results = results.get("web", {}).get("results", [])

            for r in web_results:
                parsed = urllib.parse.urlparse(r.get("url", ""))
                netloc = parsed.netloc
                domain = netloc.replace("www.", "")

                if not domain or domain in seen_domains:
                    continue
                seen_domains.add(domain)

                if domain_in_pool(domain, pool):
                    print(f"    Skip (already in pool): {domain}")
                    continue

                site_url = f"https://{netloc}"
                print(f"    Checking: {domain}")

                # Paywall check first (cheap)
                pw = check_paywall(domain, api_key)
                time.sleep(0.3)
                if pw["paywalled"]:
                    print(f"      -> paywalled, skipping")
                    continue

                # Feed URL discovery
                feed_url = find_valid_feed_url(site_url, netloc)
                if not feed_url:
                    print(f"      -> no valid feed found")
                    continue

                quality = infer_quality(r.get("description", ""))
                entry = {
                    "title": r.get("title", domain),
                    "xmlUrl": feed_url,
                    "htmlUrl": site_url,
                    "category": category,
                    "tags": ["discovered", "brave-api"],
                    "quality_score": quality,
                    "last_included": None,
                }
                new_feeds.append(entry)
                print(f"      + Added: {entry['title']} (score: {quality})")

            time.sleep(0.5)

    return new_feeds


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Brave API feed discovery & paywall verification"
    )
    parser.add_argument(
        "--api-key",
        default=os.environ.get("BRAVE_API_KEY"),
        help="Brave Search API key (or set BRAVE_API_KEY env var)",
    )
    parser.add_argument(
        "--mode",
        choices=["discover", "verify", "both"],
        default="both",
        help="discover=find new feeds, verify=check paywalls, both=do both (default: both)",
    )
    parser.add_argument(
        "--categories",
        nargs="+",
        default=list(DISCOVERY_QUERIES.keys()),
        help="Categories to search for new feeds",
    )
    parser.add_argument(
        "--add-to-pool",
        action="store_true",
        help="Automatically add discovered non-paywalled feeds to discovery_pool.json",
    )
    parser.add_argument(
        "--pool-file",
        default="discovery_pool.json",
        help="Path to discovery pool JSON file",
    )
    parser.add_argument(
        "--report-file",
        default="brave_discovery_report.json",
        help="Where to save the JSON report",
    )
    args = parser.parse_args()

    if not args.api_key:
        print("Error: set BRAVE_API_KEY or pass --api-key")
        return 1

    pool_path = Path(args.pool_file)
    pool = json.loads(pool_path.read_text())

    report = {
        "generated": datetime.now().isoformat(),
        "mode": args.mode,
        "paywall_checks": [],
        "discovered_feeds": [],
    }

    # ── VERIFY ────────────────────────────────────────────────────────────────
    if args.mode in ("verify", "both"):
        print("=" * 60)
        print("PAYWALL VERIFICATION")
        print("=" * 60)
        findings = verify_pool(pool, args.api_key)
        report["paywall_checks"] = findings

        paywalled = [f for f in findings if f["paywalled"]]
        print(f"\nResult: {len(paywalled)}/{len(findings)} feeds appear paywalled")
        if paywalled:
            print("\nPaywalled feeds detected:")
            for f in paywalled:
                print(f"  - {f['title']} ({f['domain']})")
                print(f"    evidence: {f['evidence']}")

        # Annotate pool entries with paywall_status
        domain_status = {f["domain"]: f["paywalled"] for f in findings}
        for feed in pool["feeds"]:
            domain = urllib.parse.urlparse(feed.get("htmlUrl", "")).netloc.replace("www.", "")
            if domain in domain_status:
                feed["paywall_status"] = "paywalled" if domain_status[domain] else "free"

        pool_path.write_text(json.dumps(pool, indent=2))
        print(f"\nUpdated paywall_status in {args.pool_file}")

    # ── DISCOVER ──────────────────────────────────────────────────────────────
    if args.mode in ("discover", "both"):
        print("\n" + "=" * 60)
        print("FEED DISCOVERY")
        print("=" * 60)

        new_feeds = discover_feeds(args.categories, args.api_key, pool)
        report["discovered_feeds"] = new_feeds

        print(f"\nDiscovered {len(new_feeds)} new candidate feeds")

        if args.add_to_pool and new_feeds:
            pool["feeds"].extend(new_feeds)
            pool_path.write_text(json.dumps(pool, indent=2))
            print(f"Added {len(new_feeds)} feeds to {args.pool_file}")
        elif new_feeds and not args.add_to_pool:
            print("(Run with --add-to-pool to add these feeds to the discovery pool)")

    # ── REPORT ────────────────────────────────────────────────────────────────
    report_path = Path(args.report_file)
    report_path.write_text(json.dumps(report, indent=2))
    print(f"\nFull report saved to {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
