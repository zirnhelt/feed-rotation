#!/usr/bin/env python3
"""
Feed Rotation Script
Combines core feeds with podcast sources and rotating discovery feeds,
using the current day's podcast theme to weight what gets rotated in.

Outputs:
  docs/feeds.opml          — combined OPML for Inoreader (GitHub Pages)
  feed-podcast-{day}.json  — keyword-scored articles for the podcast generator
  TODO.md AUTO section     — regenerated with any feed errors from this run
"""

import json
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path
import random

try:
    import feedparser
    HAS_FEEDPARSER = True
except ImportError:
    HAS_FEEDPARSER = False

DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

# Sources that receive the Saturday exemption: included in the podcast feed
# with _is_bonus=False even when _keyword_matches == 0.
# Keep in sync with the local sources in feeds.opml.
LOCAL_BC_SOURCES = {
    "Williams Lake Tribune",
    "Quesnel Cariboo Observer",
    "My East Kootenay Now",
    "My Cariboo Now",
}


# ── Config helpers ────────────────────────────────────────────────────────────

def load_json(filepath):
    with open(filepath) as f:
        return json.load(f)


def save_json(filepath, data):
    with open(filepath, 'w') as f:
        json.dump(data, f, indent=2)


def load_opml(filepath):
    return ET.parse(filepath)


def load_podcast_schedule():
    """Return the day-keyed schedule dict, or None if config is absent."""
    path = Path("config/podcast_schedule.json")
    if not path.exists():
        return None
    return load_json(path)["schedule"]


def load_source_prefs():
    path = Path("config/source_preferences.json")
    if not path.exists():
        return {}, {}
    data = load_json(path)
    return data.get("source_map", {}), data.get("quality_scores", {})


def load_filters():
    path = Path("config/filters.json")
    if not path.exists():
        return {"source_blocklist": set(), "title_patterns": []}
    data = load_json(path)
    patterns = [re.compile(p, re.IGNORECASE) for p in data.get("title_patterns_blocklist", [])]
    return {"source_blocklist": set(data.get("source_blocklist", [])),
            "title_patterns": patterns}


def load_limits():
    path = Path("config/limits.json")
    if not path.exists():
        return {"min_claude_score": 15, "days_lookback": 7,
                "max_articles_per_source": 10, "max_articles_per_feed": 100,
                "target_feed_size": 30, "min_feed_size_warn": 10}
    return load_json(path)


def parse_podcast_feeds_opml(path):
    """Return a list of source dicts from feeds.opml."""
    if not Path(path).exists():
        return []
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


def today_day_name():
    return DAYS[datetime.now().weekday()]


# ── Discovery selection ───────────────────────────────────────────────────────

def theme_relevance_score(feed, keywords):
    """
    Score 0-1 based on how many of today's theme keywords appear in the
    discovery feed's title, category, and tags. This lets the rotator
    prefer feeds that serve the current podcast theme.

    Full score (1.0) is reached when ≥20% of keywords match.
    At theme_weight=0 in rotation_config.json this has no effect.
    """
    if not keywords:
        return 0.0
    text = " ".join([
        feed.get("title", ""),
        feed.get("category", ""),
        " ".join(feed.get("tags", [])),
    ]).lower()
    hits = sum(1 for kw in keywords if kw.lower() in text)
    return min(1.0, hits / max(1, len(keywords) * 0.2))


def select_discovery_feeds(pool, config, theme_keywords=None):
    """
    Select feeds based on quality, recency, randomness, category diversity,
    and relevance to today's podcast theme.

    theme_weight in rotation_config.json controls the podcast theme influence.
    At 0.0 (default if absent) behaviour is identical to before this change.
    The three weights are renormalised so they always sum to 1.
    """
    eligible = []
    today = datetime.now()
    min_gap = timedelta(days=config['min_days_between_includes'])
    max_per_category = config.get('max_per_category', 2)
    skip_paywalled = config.get('skip_paywalled', True)

    for feed in pool['feeds']:
        if skip_paywalled and feed.get('paywall_status') == 'paywalled' and not feed.get('subscriber'):
            continue
        if feed['last_included'] is None:
            eligible.append(feed)
        else:
            last_date = datetime.fromisoformat(feed['last_included'])
            if today - last_date >= min_gap:
                eligible.append(feed)

    print(f"  Eligible feeds: {len(eligible)} out of {len(pool['feeds'])}")

    quality_w = config['quality_weight']
    random_w = config['randomness_weight']
    theme_w = config.get('theme_weight', 0.0)
    total_w = quality_w + random_w + theme_w
    quality_w /= total_w
    random_w /= total_w
    theme_w /= total_w

    scored_feeds = []
    for feed in eligible:
        quality_score = feed['quality_score'] / 10.0
        random_score = random.random()
        t_score = theme_relevance_score(feed, theme_keywords or []) if theme_w > 0 else 0.0
        final_score = (quality_w * quality_score
                       + random_w * random_score
                       + theme_w * t_score)
        scored_feeds.append((final_score, feed))

    scored_feeds.sort(reverse=True, key=lambda x: x[0])

    selected = []
    category_counts = {}
    for score, feed in scored_feeds:
        if len(selected) >= config['num_discovery_feeds']:
            break
        cat = feed.get('category', 'uncategorized')
        if category_counts.get(cat, 0) < max_per_category:
            selected.append(feed)
            category_counts[cat] = category_counts.get(cat, 0) + 1

    return selected


# ── OPML generation ───────────────────────────────────────────────────────────

def create_combined_opml(core_tree, podcast_feeds, discovery_feeds):
    """
    Combine core feeds (stable) + podcast sources (stable, themed) +
    discovery rotation (rotating). Podcast sources sit between core and
    discovery so subscribers always receive them regardless of rotation state.
    """
    root = ET.Element('opml', version='2.0')
    head = ET.SubElement(root, 'head')
    ET.SubElement(head, 'title').text = 'Feed Rotation - Generated'
    ET.SubElement(head, 'dateCreated').text = datetime.now().isoformat()
    body = ET.SubElement(root, 'body')

    # Core feeds — copy full category structure from core_feeds.opml
    for outline in core_tree.getroot().find('body'):
        body.append(outline)

    # Podcast sources — stable themed feeds from feeds.opml
    if podcast_feeds:
        pod = ET.SubElement(body, 'outline', text='Podcast Sources', title='Podcast Sources')
        for feed in podcast_feeds:
            ET.SubElement(pod, 'outline',
                          type='rss',
                          text=feed['text'],
                          title=feed['text'],
                          xmlUrl=feed['xmlUrl'],
                          htmlUrl=feed.get('htmlUrl', ''))

    # Discovery rotation
    if discovery_feeds:
        disc = ET.SubElement(body, 'outline', text='Discovery Rotation', title='Discovery Rotation')
        for feed in discovery_feeds:
            ET.SubElement(disc, 'outline',
                          type='rss',
                          text=feed['title'],
                          title=feed['title'],
                          xmlUrl=feed['xmlUrl'],
                          htmlUrl=feed.get('htmlUrl', ''))

    return ET.ElementTree(root)


def indent_xml(elem, level=0):
    i = "\n" + level * "  "
    if len(elem):
        if not elem.text or not elem.text.strip():
            elem.text = i + "  "
        if not elem.tail or not elem.tail.strip():
            elem.tail = i
        for child in elem:
            indent_xml(child, level + 1)
        if not child.tail or not child.tail.strip():
            child.tail = i
    else:
        if level and (not elem.tail or not elem.tail.strip()):
            elem.tail = i


# ── Podcast feed generation ───────────────────────────────────────────────────

def fetch_feed_articles(url, source_name, days_lookback, limits):
    """Fetch articles from one RSS/Atom feed. Returns (articles, error_str|None)."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days_lookback)
    max_per_source = limits.get("max_articles_per_source", 10)

    try:
        parsed = feedparser.parse(url)
    except Exception as e:
        return [], str(e)

    http_status = parsed.get("status", 0)
    if http_status in (403, 415):
        return [], f"HTTP {http_status}"

    if parsed.get("bozo") and not parsed.get("entries"):
        return [], str(parsed.get("bozo_exception", "parse error"))

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


def score_articles(articles, keywords, day_name, source_map, quality_scores, filters, limits):
    """
    Apply keyword scoring (_keyword_matches, _boosted_score, _is_bonus) and
    return filtered, sorted article list.

    Formula: _boosted_score = min(100, keyword_hits × 20 + ai_quality_score × 0.3)
    """
    min_score = limits.get("min_claude_score", 15)
    scored = []
    for article in articles:
        if article["source"] in filters["source_blocklist"]:
            continue
        if any(p.search(article["title"]) for p in filters["title_patterns"]):
            continue

        source_type = source_map.get(article["source"], "digital")
        quality = quality_scores.get(source_type, 50)

        hits = sum(
            1 for kw in keywords
            if kw.lower() in (article["title"] + " " + article["summary"]).lower()
        )
        boosted = min(100, hits * 20 + int(quality * 0.3))
        if boosted < min_score:
            continue

        is_bonus = hits == 0
        if day_name == "saturday" and article["source"] in LOCAL_BC_SOURCES:
            is_bonus = False

        article["_keyword_matches"] = hits
        article["_boosted_score"] = boosted
        article["_is_bonus"] = is_bonus
        scored.append(article)

    scored.sort(key=lambda a: (a["_is_bonus"], -a["_boosted_score"]))
    return scored[:limits.get("target_feed_size", 30)]


def generate_podcast_feed(day_name, day_config, podcast_sources,
                          source_map, quality_scores, filters, limits):
    """
    Fetch articles from today's relevant podcast sources, score them, and
    write feed-podcast-{day}.json. Returns a list of error dicts.
    """
    keywords = day_config["keywords"]
    days_lookback = limits.get("days_lookback", 7)
    errors = []

    relevant = [s for s in podcast_sources if s["theme"] in ("all", day_name)]

    all_articles = []
    for src in relevant:
        articles, err = fetch_feed_articles(src["xmlUrl"], src["text"], days_lookback, limits)
        if err:
            print(f"    WARN  {src['text']}: {err}")
            errors.append({"source": src["text"], "url": src["xmlUrl"],
                           "error": err, "day": day_name,
                           "date": datetime.now().isoformat()})
        all_articles.extend(articles)

    scored = score_articles(all_articles, keywords, day_name,
                            source_map, quality_scores, filters, limits)

    warn_threshold = limits.get("min_feed_size_warn", 10)
    if len(scored) < warn_threshold:
        print(f"    WARN  Only {len(scored)} articles after scoring "
              f"(threshold: {warn_threshold}) — consider broadening keywords")

    output = {
        "_podcast": {
            "theme": day_config["theme"],
            "theme_description": day_config["theme_description"],
            "day": day_name,
            "generated": datetime.now().isoformat(),
            "article_count": len(scored),
        },
        "articles": scored,
    }
    out_path = Path(f"feed-podcast-{day_name}.json")
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    bonus_count = sum(1 for a in scored if a["_is_bonus"])
    print(f"  ✓ {out_path}: {len(scored)} articles "
          f"({len(scored) - bonus_count} theme, {bonus_count} bonus)")
    return errors


# ── TODO.md maintenance ───────────────────────────────────────────────────────

def update_todo_auto_section(errors_log):
    """Regenerate the AUTO section of TODO.md. The Notes section is preserved."""
    todo_path = Path("TODO.md")
    auto_header = "## AUTO — feed errors (regenerated on every run)\n"

    lines = [f"_Last regenerated: {datetime.now().strftime('%Y-%m-%d %H:%M')} UTC_\n\n"]
    if not errors_log:
        lines.append("No feed errors in this run.\n")
    else:
        lines.append(f"### Feed errors ({len(errors_log)} source(s))\n\n")
        lines.append("| Source | Day | Error | URL |\n")
        lines.append("|---|---|---|---|\n")
        for e in errors_log:
            lines.append(
                f"| {e['source']} | {e['day']} | `{e['error']}` | {e['url']} |\n"
            )
    auto_content = "".join(lines)

    if not todo_path.exists():
        todo_path.write_text(
            f"# TODO\n\n{auto_header}\n{auto_content}\n## Notes\n\n"
        )
        return

    text = todo_path.read_text()
    notes_marker = "## Notes\n"
    if auto_header in text and notes_marker in text:
        pre = text[: text.index(auto_header) + len(auto_header)]
        post = text[text.index(notes_marker):]
        todo_path.write_text(pre + "\n" + auto_content + "\n" + post)
    else:
        todo_path.write_text(text.rstrip() + f"\n\n{auto_header}\n{auto_content}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("=== Feed Rotation Script ===\n")

    # Load all config
    print("Loading configuration...")
    config = load_json('rotation_config.json')
    pool = load_json('discovery_pool.json')
    core_tree = load_opml('core_feeds.opml')
    podcast_feeds = parse_podcast_feeds_opml('feeds.opml')
    schedule = load_podcast_schedule()
    source_map, quality_scores = load_source_prefs()
    filters = load_filters()
    limits = load_limits()

    rss_xpath = './/outline[@type="rss"]'
    print(f"  Core feeds:          {len(core_tree.findall(rss_xpath))}")
    print(f"  Podcast sources:     {len(podcast_feeds)}")
    print(f"  Discovery pool size: {len(pool['feeds'])}")
    print(f"  Feeds to rotate in:  {config['num_discovery_feeds']}")

    # Determine today's podcast theme for weighted discovery selection
    day_name = today_day_name()
    theme_keywords = []
    if schedule and day_name in schedule:
        theme_keywords = schedule[day_name]["keywords"]
        theme = schedule[day_name]["theme"]
        theme_w = config.get("theme_weight", 0.0)
        print(f"\nToday: {day_name.capitalize()} — {theme}")
        if theme_w > 0:
            print(f"  theme_weight={theme_w}: discovery selection biased toward "
                  f"{len(theme_keywords)} theme keywords")
        else:
            print(f"  theme_weight=0: theme has no effect on discovery selection "
                  f"(set theme_weight in rotation_config.json to enable)")
    else:
        print(f"\nToday: {day_name.capitalize()} (no podcast schedule loaded)")

    # Select discovery feeds (theme-weighted when theme_weight > 0)
    print("\nSelecting discovery feeds...")
    selected = select_discovery_feeds(pool, config, theme_keywords)

    print(f"\nSelected {len(selected)} discovery feeds:")
    for i, feed in enumerate(selected, 1):
        print(f"  {i}. {feed['title']} "
              f"(quality: {feed['quality_score']}, category: {feed.get('category', 'N/A')})")

    # Update pool timestamps
    today_str = datetime.now().isoformat()
    for feed in pool['feeds']:
        if feed in selected:
            feed['last_included'] = today_str
    save_json('discovery_pool.json', pool)
    print("\nUpdated discovery_pool.json timestamps")

    # Generate docs/feeds.opml
    print("\nGenerating combined OPML...")
    output_tree = create_combined_opml(core_tree, podcast_feeds, selected)
    indent_xml(output_tree.getroot())
    Path('docs').mkdir(exist_ok=True)
    output_tree.write('docs/feeds.opml', encoding='utf-8', xml_declaration=True)

    core_count = len(core_tree.findall(rss_xpath))
    total = core_count + len(podcast_feeds) + len(selected)
    print(f"✓ docs/feeds.opml: {total} feeds "
          f"(core: {core_count}, podcast: {len(podcast_feeds)}, discovery: {len(selected)})")

    # Generate today's podcast feed JSON (requires feedparser)
    errors_log = []
    if schedule and day_name in schedule:
        if HAS_FEEDPARSER:
            print(f"\nGenerating feed-podcast-{day_name}.json...")
            errors = generate_podcast_feed(
                day_name, schedule[day_name], podcast_feeds,
                source_map, quality_scores, filters, limits
            )
            errors_log.extend(errors)
        else:
            print("\nSkipping podcast feed generation (feedparser not installed)")
            print("  pip install feedparser")

    # Update TODO.md AUTO section
    update_todo_auto_section(errors_log)

    print("\nDone!")


if __name__ == '__main__':
    main()
