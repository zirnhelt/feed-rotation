# Feed Rotation System

Automated RSS feed rotation system that combines stable core feeds with periodically rotating discovery feeds to maintain quality while introducing fresh perspectives.

## Overview

This system prevents information diet stagnation by:
- Maintaining a **core set** of high-quality feeds that never change
- Periodically **rotating in discovery feeds** from a larger pool
- Using **quality-weighted selection** to balance reliable sources with serendipity
- **Automating** the entire process via GitHub Actions

## How It Works

### Core Feeds (Stable)
High-signal sources organized by category in `core_feeds.opml`:
- Science & Deep Thinking (Quanta, Aeon, Nautilus, etc.)
- Tech Analysis & Deep Dives (Stratechery, Julia Evans, MIT Tech Review)
- Systems & Culture (Low Tech Magazine, The Marginalian)
- Climate & Environment (Carbon Brief)

### Discovery Pool (Rotating)
47 candidate feeds in `discovery_pool.json` with:
- Quality scores (1-10)
- Categories and tags
- Last included timestamps

### Rotation Strategy
Configured in `rotation_config.json`:
- **5 discovery feeds** included at a time
- Rotates **every 7 days** (weekly)
- Minimum **28 days** between re-inclusions
- Selection weighted **70% quality**, **30% randomness**

## Setup Instructions

### 1. Create GitHub Repository

```bash
# Create new repo on github.com named 'feed-rotation'
# Then clone it locally
git clone https://github.com/YOUR-USERNAME/feed-rotation.git
cd feed-rotation

# Copy all files from this directory into your repo
# (you already have them if you extracted the zip)
```

### 2. Push to GitHub

```bash
git add .
git commit -m "Initial commit: Feed rotation system"
git push origin main
```

### 3. Enable GitHub Pages

1. Go to your repo on github.com
2. Click **Settings** → **Pages** (left sidebar)
3. Under **Source**, select:
   - Branch: `main`
   - Folder: `/docs`
4. Click **Save**

After a few minutes, your feed will be available at:
```
https://YOUR-USERNAME.github.io/feed-rotation/feeds.opml
```

### 4. Test the Rotation

Manually trigger the workflow:
1. Go to **Actions** tab in your repo
2. Click **Rotate Feeds** workflow
3. Click **Run workflow** → **Run workflow**
4. Watch it execute (~30 seconds)

Check that `docs/feeds.opml` was created.

### 5. Subscribe in Inoreader

1. In Inoreader, go to **Preferences** → **OPML Subscriptions**
2. Add your GitHub Pages URL:
   ```
   https://YOUR-USERNAME.github.io/feed-rotation/feeds.opml
   ```
3. Set refresh frequency (Inoreader decides when to poll)

## File Structure

```
feed-rotation/
├── core_feeds.opml          # Stable feeds (edit manually)
├── discovery_pool.json      # Rotating feed candidates (edit to add/remove)
├── rotation_config.json     # Rotation parameters (tune behavior)
├── rotate_feeds.py          # Main rotation script
├── .github/
│   └── workflows/
│       └── rotate.yml       # GitHub Actions automation
├── docs/
│   └── feeds.opml          # Generated output (don't edit)
└── README.md               # This file
```

## Customization

### Add/Remove Core Feeds
Edit `core_feeds.opml` directly. These never rotate out.

### Manage Discovery Pool
Edit `discovery_pool.json`:

```json
{
  "title": "New Feed Name",
  "xmlUrl": "https://example.com/feed.xml",
  "htmlUrl": "https://example.com",
  "category": "tech",
  "tags": ["tag1", "tag2"],
  "quality_score": 7,
  "last_included": null
}
```

### Adjust Rotation Behavior
Edit `rotation_config.json`:

```json
{
  "num_discovery_feeds": 5,        # How many rotating feeds
  "rotation_frequency_days": 7,    # How often to rotate
  "min_days_between_includes": 28, # Cooldown period
  "quality_weight": 0.7,           # Favor quality (0-1)
  "randomness_weight": 0.3         # Add serendipity (0-1)
}
```

### Change Rotation Schedule
Edit `.github/workflows/rotate.yml`:

```yaml
schedule:
  - cron: '0 2 * * 0'  # Sunday 2am UTC
  # '0 2 * * 1' = Monday 2am
  # '0 2 1 * *' = 1st of month 2am
```

[Cron schedule syntax reference](https://crontab.guru/)

## Running Locally

Test rotation before pushing:

```bash
python rotate_feeds.py
```

This will:
1. Select new discovery feeds
2. Update `discovery_pool.json` timestamps
3. Generate `docs/feeds.opml`

## Monitoring

- **GitHub Actions**: Check workflow runs in the Actions tab
- **Feed output**: View generated OPML at your GitHub Pages URL
- **Rotation history**: Git commits show which feeds rotated in/out

## Philosophy

This system implements several principles for healthy information consumption:

1. **Stability + Discovery**: Core feeds provide consistent quality; discovery feeds introduce variety
2. **Quality-weighted randomness**: Favor high-quality sources while allowing wildcards
3. **Forced rotation**: Prevents filter bubble formation through systematic exposure
4. **Low-friction curation**: Add feeds to the pool without committing to long-term subscriptions
5. **Automation**: Let the system handle rotation; focus energy on pool curation

## Troubleshooting

**Workflow fails:**
- Check Actions tab for error logs
- Verify all JSON files are valid (use a JSON validator)
- Ensure OPML files have valid XML structure

**Inoreader not updating:**
- Inoreader controls poll frequency (you can't force it)
- Check that your GitHub Pages URL is accessible
- Verify OPML file was actually regenerated (check commit history)

**Want to force new feeds immediately:**
- Manually trigger workflow: Actions → Rotate Feeds → Run workflow
- Or reset timestamps in `discovery_pool.json` to `null`

## Future Enhancements

Ideas for extending the system:

- **Topic diversity tracking**: Ensure category balance in rotation
- **Engagement tracking**: Weight feeds by how much you actually read them
- **Seasonal themes**: Rotate based on current projects/interests
- **Feed quality monitoring**: Automatically demote inactive or low-quality feeds
- **Multi-tier rotation**: Different rotation speeds for different feed categories

## License

MIT - Use freely, modify as needed, share improvements!
