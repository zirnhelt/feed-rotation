#!/usr/bin/env python3
"""
Podcast feed generator.

Reads feeds.opml for sources, fetches articles from the last N days,
scores them against the day's theme keywords from config/podcast_schedule.json,
and writes feed-podcast-{day}.json.

Output fields per article:
  _keyword_matches  — int: how many theme keywords appear in title + summary
  _boosted_score    — int 0-100: min(100, hits × 20 + quality × 0.3)
  _is_bonus         — bool: True when keyword_matches == 0, except on Saturday
                      for LOCAL_BC_SOURCES

Usage:
  python generate_podcast_feed.py              # generates today's day
  python generate_podcast_feed.py monday       # generates specific day
  python generate_podcast_feed.py --all        # generates all 7 days
"""

import json
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    import feedparser
except ImportError:
    print("ERROR: feedparser is required. Install with: pip install feedparser")
    sys.exit(1)

# ── Constants ────────────────────────────────────────────────────────────────

DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

# Sources that get the Saturday exemption: included with _is_bonus=False even
# when _keyword_matches == 0. Keep in sync with feeds.opml local sources.
LOCAL_BC_SOURCES = {
    "Williams Lake Tribune",
    "Quesnel Cariboo Observer",
    "My East Kootenay Now",
    "My Cariboo Now",
}

CONFIG_DIR = Path("config")
FEEDS_OPML = Path("feeds.opml")
OUTPUT_DIR = Path(".")

# ── Config loading ────────────────────────────────────────────────────────────

def load_json(path):
    with open(path) as f:
        return json.load(f)


def load_schedule():
    return load_json(CONFIG_DIR / "podcast_schedule.json")["schedule"]


def load_source_prefs():
    data = load_json(CONFIG_DIR / "source_preferences.json")
    return data.get("source_map", {}), data.get("quality_scores", {})


def load_filters():
    data = load_json(CONFIG_DIR / "filters.json")
    patterns = [re.compile(p, re.IGNORECASE) for p in data.get("title_patterns_blocklist", [])]
    return {
        "source_blocklist": set(data.get("source_blocklist", [])),
        "domain_blocklist": set(data.get("domain_blocklist", [])),
        "title_patterns": patterns,
    }


def load_limits():
    return load_json(CONFIG_DIR / "limits.json")

# ── OPML parsing ─────────────────────────────────────────────────────────────

def parse_feeds_opml(path):
    """Return list of dicts with keys: text, xmlUrl, htmlUrl, theme, source_type."""
    tree = ET.parse(path)
    feeds = []
    for outline in tree.iter("outline"):
        url = outline.get("xmlUrl")
        if not url:
            continue
        feeds.append({
            "text": outline.get("text", ""),
            "xmlUrl": url,
            "htmlUrl": outline.get("htmlUrl", ""),
            "theme": outline.get("theme", "all"),
            "source_type": outline.get("source_type", ""),
        })
    return feeds

# ── Feed fetching ─────────────────────────────────────────────────────────────

def fetch_feed(url, source_name, days_lookback, limits):
    """Fetch and parse one RSS/Atom feed. Returns list of article dicts."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days_lookback)
    max_per_source = limits.get("max_articles_per_source", 10)

    try:
        parsed = feedparser.parse(url)
    except Exception as e:
        print(f"  ERROR fetching {source_name}: {e}")
        return [], str(e)

    if parsed.get("bozo") and not parsed.get("entries"):
        exc = parsed.get("bozo_exception", "unknown parse error")
        print(f"  WARN  {source_name}: bozo feed ({exc})")
        return [], str(exc)

    http_status = parsed.get("status", 0)
    if http_status in (403, 415):
        msg = f"HTTP {http_status}"
        print(f"  ERROR {source_name}: {msg}")
        return [], msg

    articles = []
    for entry in parsed.entries[:limits.get("max_articles_per_feed", 100)]:
        published = None
        for field in ("published_parsed", "updated_parsed", "created_parsed"):
            t = entry.get(field)
            if t:
                try:
                    published = datetime(*t[:6], tzinfo=timezone.utc)
                    break
                except Exception:
                    pass

        if published and published < cutoff:
            continue

        summary = entry.get("summary", "") or entry.get("description", "") or ""
        # Strip HTML tags from summary
        summary = re.sub(r"<[^>]+>", " ", summary).strip()

        articles.append({
            "title": entry.get("title", "").strip(),
            "link": entry.get("link", ""),
            "summary": summary[:500],
            "source": source_name,
            "published": published.isoformat() if published else None,
        })
        if len(articles) >= max_per_source:
            break

    return articles, None

# ── Scoring ───────────────────────────────────────────────────────────────────

def count_keyword_matches(article, keywords):
    """Count how many keywords appear (case-insensitive) in title + summary."""
    haystack = (article["title"] + " " + article["summary"]).lower()
    hits = sum(1 for kw in keywords if kw.lower() in haystack)
    return hits


def compute_boosted_score(keyword_hits, ai_quality_score):
    return min(100, keyword_hits * 20 + int(ai_quality_score * 0.3))


def source_quality_score(source_name, source_map, quality_scores):
    """Map a source name to a 0-100 quality proxy via source_preferences.json."""
    source_type = source_map.get(source_name, "digital")
    return quality_scores.get(source_type, 50)


def is_filtered(article, filters):
    if article["source"] in filters["source_blocklist"]:
        return True
    for pat in filters["title_patterns"]:
        if pat.search(article["title"]):
            return True
    return False

# ── Main generation ───────────────────────────────────────────────────────────

def generate_day(day_name, schedule, all_feeds, source_map, quality_scores,
                 filters, limits, errors_log):
    day_key = day_name.lower()
    if day_key not in schedule:
        print(f"ERROR: '{day_key}' not found in podcast_schedule.json")
        return

    day_config = schedule[day_key]
    keywords = day_config["keywords"]
    theme = day_config["theme"]
    theme_description = day_config["theme_description"]
    days_lookback = limits.get("days_lookback", 7)
    min_score = limits.get("min_claude_score", 15)

    print(f"\n── {day_name.capitalize()} ({theme}) ──")

    # Select feeds relevant to this day (theme == day_key or theme == "all")
    relevant_feeds = [
        f for f in all_feeds
        if f["theme"] == "all" or f["theme"] == day_key
    ]

    articles = []
    for feed in relevant_feeds:
        source_name = feed["text"]
        print(f"  Fetching: {source_name}")
        fetched, err = fetch_feed(feed["xmlUrl"], source_name, days_lookback, limits)
        if err:
            errors_log.append({
                "source": source_name,
                "url": feed["xmlUrl"],
                "error": err,
                "day": day_key,
                "date": datetime.now().isoformat(),
            })
        articles.extend(fetched)

    print(f"  Raw articles: {len(articles)}")

    # Apply filters and score
    scored = []
    for article in articles:
        if is_filtered(article, filters):
            continue

        quality = source_quality_score(article["source"], source_map, quality_scores)
        hits = count_keyword_matches(article, keywords)
        boosted = compute_boosted_score(hits, quality)

        # Score floor: use boosted_score as proxy for min_claude_score
        if boosted < min_score:
            continue

        is_bonus = (hits == 0)
        # Saturday exemption: local Cariboo sources are never bonus
        if day_key == "saturday" and article["source"] in LOCAL_BC_SOURCES:
            is_bonus = False

        article["_keyword_matches"] = hits
        article["_boosted_score"] = boosted
        article["_is_bonus"] = is_bonus
        scored.append(article)

    # Sort: non-bonus first, then by boosted_score descending
    scored.sort(key=lambda a: (a["_is_bonus"], -a["_boosted_score"]))

    target = limits.get("target_feed_size", 30)
    scored = scored[:target]

    warn_threshold = limits.get("min_feed_size_warn", 10)
    if len(scored) < warn_threshold:
        print(f"  WARN  Only {len(scored)} articles after scoring (threshold: {warn_threshold})")

    print(f"  Scored articles: {len(scored)} "
          f"(bonus: {sum(1 for a in scored if a['_is_bonus'])})")

    output = {
        "_podcast": {
            "theme": theme,
            "theme_description": theme_description,
            "day": day_key,
            "generated": datetime.now().isoformat(),
            "article_count": len(scored),
        },
        "articles": scored,
    }

    out_path = OUTPUT_DIR / f"feed-podcast-{day_key}.json"
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"  Written: {out_path}")

    return output

# ── TODO.md AUTO section ──────────────────────────────────────────────────────

def update_todo_auto_section(errors_log):
    """Regenerate the AUTO section of TODO.md with errors from this run."""
    todo_path = Path("TODO.md")

    auto_lines = ["<!-- AUTO-GENERATED: do not edit this section manually -->\n"]
    auto_lines.append(f"_Last regenerated: {datetime.now().strftime('%Y-%m-%d %H:%M')} UTC_\n\n")

    if not errors_log:
        auto_lines.append("No feed errors in this run.\n")
    else:
        auto_lines.append(f"### Feed errors ({len(errors_log)} source(s))\n\n")
        auto_lines.append("| Source | Day | Error | URL |\n")
        auto_lines.append("|---|---|---|---|\n")
        for err in errors_log:
            auto_lines.append(
                f"| {err['source']} | {err['day']} | `{err['error']}` | {err['url']} |\n"
            )

    auto_content = "".join(auto_lines)

    if not todo_path.exists():
        # Bootstrap a new TODO.md
        content = f"""# TODO

## AUTO — feed errors (regenerated on every run)

{auto_content}

## Notes

_Record disabled sources, manual changes, and follow-ups here._

"""
        todo_path.write_text(content)
        print(f"\nCreated {todo_path}")
        return

    existing = todo_path.read_text()

    # Replace between AUTO section markers
    auto_start = "## AUTO — feed errors (regenerated on every run)\n"
    notes_start = "## Notes\n"

    if auto_start in existing and notes_start in existing:
        pre = existing[: existing.index(auto_start) + len(auto_start)]
        post = existing[existing.index(notes_start):]
        todo_path.write_text(pre + "\n" + auto_content + "\n" + post)
    else:
        # Fallback: append AUTO section
        todo_path.write_text(existing.rstrip() + "\n\n" + auto_start + "\n" + auto_content)

    print(f"Updated AUTO section in {todo_path}")

# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    args = sys.argv[1:]

    # Determine which days to generate
    if "--all" in args:
        days_to_run = DAYS
    elif args:
        day_arg = args[0].lower()
        if day_arg not in DAYS:
            print(f"ERROR: '{day_arg}' is not a valid day. Choose from: {', '.join(DAYS)}")
            sys.exit(1)
        days_to_run = [day_arg]
    else:
        # Default: today's weekday
        today_index = datetime.now().weekday()  # 0=Monday
        days_to_run = [DAYS[today_index]]

    print("=== Podcast Feed Generator ===\n")
    print(f"Generating: {', '.join(days_to_run)}\n")

    schedule = load_schedule()
    source_map, quality_scores = load_source_prefs()
    filters = load_filters()
    limits = load_limits()
    all_feeds = parse_feeds_opml(FEEDS_OPML)

    print(f"Loaded {len(all_feeds)} feed sources from {FEEDS_OPML}")

    errors_log = []

    for day in days_to_run:
        generate_day(day, schedule, all_feeds, source_map, quality_scores,
                     filters, limits, errors_log)

    update_todo_auto_section(errors_log)

    print("\nDone.")


if __name__ == "__main__":
    main()
