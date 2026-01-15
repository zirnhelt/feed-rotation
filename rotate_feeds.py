#!/usr/bin/env python3
"""
Feed Rotation Script
Combines core feeds with rotating discovery feeds
"""

import json
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
import random
from pathlib import Path

def load_json(filepath):
    """Load JSON file"""
    with open(filepath, 'r') as f:
        return json.load(f)

def save_json(filepath, data):
    """Save JSON file with pretty formatting"""
    with open(filepath, 'w') as f:
        json.dump(data, f, indent=2)

def load_opml(filepath):
    """Load OPML file"""
    tree = ET.parse(filepath)
    return tree

def select_discovery_feeds(pool, config):
    """
    Select feeds based on quality, recency, and randomness
    
    Selection algorithm:
    1. Filter out feeds that were included too recently
    2. Score remaining feeds based on quality and randomness
    3. Select top N feeds by score
    """
    eligible = []
    today = datetime.now()
    min_gap = timedelta(days=config['min_days_between_includes'])
    
    for feed in pool['feeds']:
        if feed['last_included'] is None:
            eligible.append(feed)
        else:
            last_date = datetime.fromisoformat(feed['last_included'])
            if today - last_date >= min_gap:
                eligible.append(feed)
    
    print(f"  Eligible feeds: {len(eligible)} out of {len(pool['feeds'])}")
    
    # Score each feed
    scored_feeds = []
    for feed in eligible:
        quality_score = feed['quality_score'] / 10.0
        random_score = random.random()
        
        final_score = (
            config['quality_weight'] * quality_score +
            config['randomness_weight'] * random_score
        )
        scored_feeds.append((final_score, feed))
    
    # Sort by score and take top N
    scored_feeds.sort(reverse=True, key=lambda x: x[0])
    selected = [feed for score, feed in scored_feeds[:config['num_discovery_feeds']]]
    
    return selected

def create_combined_opml(core_tree, discovery_feeds):
    """
    Combine core feeds with selected discovery feeds
    Returns a new OPML ElementTree
    """
    root = ET.Element('opml', version='2.0')
    head = ET.SubElement(root, 'head')
    title = ET.SubElement(head, 'title')
    title.text = 'Feed Rotation - Generated'
    
    date_created = ET.SubElement(head, 'dateCreated')
    date_created.text = datetime.now().isoformat()
    
    body = ET.SubElement(root, 'body')
    
    # Add core feeds (copy entire category structure)
    core_body = core_tree.getroot().find('body')
    for outline in core_body:
        # Deep copy to preserve structure
        body.append(outline)
    
    # Add discovery feeds as separate category
    if discovery_feeds:
        discovery_outline = ET.SubElement(body, 'outline', 
            text='Discovery Rotation', 
            title='Discovery Rotation')
        
        for feed in discovery_feeds:
            ET.SubElement(discovery_outline, 'outline',
                type='rss',
                text=feed['title'],
                title=feed['title'],
                xmlUrl=feed['xmlUrl'],
                htmlUrl=feed.get('htmlUrl', '')
            )
    
    return ET.ElementTree(root)

def indent_xml(elem, level=0):
    """Add indentation to XML for pretty printing"""
    i = "\n" + level * "  "
    if len(elem):
        if not elem.text or not elem.text.strip():
            elem.text = i + "  "
        if not elem.tail or not elem.tail.strip():
            elem.tail = i
        for child in elem:
            indent_xml(child, level+1)
        if not child.tail or not child.tail.strip():
            child.tail = i
    else:
        if level and (not elem.tail or not elem.tail.strip()):
            elem.tail = i

def main():
    print("=== Feed Rotation Script ===\n")
    
    # Load configuration
    print("Loading configuration...")
    config = load_json('rotation_config.json')
    pool = load_json('discovery_pool.json')
    core_tree = load_opml('core_feeds.opml')
    
    rss_xpath = './/outline[@type="rss"]'
    core_feed_count = len(core_tree.findall(rss_xpath))
    print(f"  Core feeds: {core_feed_count}")
    print(f"  Discovery pool size: {len(pool['feeds'])}")
    print(f"  Feeds to rotate in: {config['num_discovery_feeds']}\n")
    
    # Select discovery feeds
    print("Selecting discovery feeds...")
    selected = select_discovery_feeds(pool, config)
    
    print(f"\nSelected {len(selected)} discovery feeds:")
    for i, feed in enumerate(selected, 1):
        print(f"  {i}. {feed['title']} (score: {feed['quality_score']}, category: {feed.get('category', 'N/A')})")
    
    # Update last_included dates
    today_str = datetime.now().isoformat()
    for feed in pool['feeds']:
        if feed in selected:
            feed['last_included'] = today_str
    
    print("\nUpdating discovery pool state...")
    save_json('discovery_pool.json', pool)
    
    # Generate combined OPML
    print("Generating combined OPML...")
    output_tree = create_combined_opml(core_tree, selected)
    
    # Pretty print the XML
    indent_xml(output_tree.getroot())
    
    # Ensure docs directory exists
    Path('docs').mkdir(exist_ok=True)
    
    # Save to docs/ for GitHub Pages
    output_tree.write('docs/feeds.opml', 
                     encoding='utf-8', 
                     xml_declaration=True)
    
    rss_xpath = './/outline[@type="rss"]'
    total_feeds = len(core_tree.findall(rss_xpath)) + len(selected)
    core_count = len(core_tree.findall(rss_xpath))
    print(f"\n✓ Generated docs/feeds.opml with {total_feeds} total feeds")
    print(f"  - Core feeds: {core_count}")
    print(f"  - Discovery feeds: {len(selected)}")
    print("\nDone! 🎉")

if __name__ == '__main__':
    main()
