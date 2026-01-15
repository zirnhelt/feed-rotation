# Quick Start Guide

Get your feed rotation system running in 10 minutes.

## Step 1: Push to GitHub (5 minutes)

```bash
# If you haven't already:
# 1. Create a new repo on github.com called 'feed-rotation'
# 2. Extract this folder and cd into it

git init
git add .
git commit -m "Initial commit: Feed rotation system"
git branch -M main
git remote add origin https://github.com/YOUR-USERNAME/feed-rotation.git
git push -u origin main
```

Replace `YOUR-USERNAME` with your actual GitHub username.

## Step 2: Enable GitHub Pages (2 minutes)

1. Go to your repo: `https://github.com/YOUR-USERNAME/feed-rotation`
2. Click **Settings** (top menu)
3. Click **Pages** (left sidebar)
4. Under "Build and deployment":
   - Source: **Deploy from a branch**
   - Branch: **main**
   - Folder: **/docs**
5. Click **Save**

Wait 2-3 minutes for deployment.

## Step 3: Test the Rotation (2 minutes)

1. In your repo, click **Actions** tab
2. Click **Rotate Feeds** in the left sidebar
3. Click **Run workflow** button (right side)
4. Click green **Run workflow** button
5. Wait ~30 seconds

You should see a green checkmark ✓

## Step 4: Subscribe in Inoreader (1 minute)

Your feed URL is:
```
https://YOUR-USERNAME.github.io/feed-rotation/feeds.opml
```

In Inoreader:
1. **Preferences** → **OPML Subscriptions**
2. Paste your URL
3. Click **Subscribe**

Done! 🎉

## What Happens Next?

- Every Sunday at 2am UTC: 5 new discovery feeds rotate in
- Your core 10 feeds never change
- Discovery feeds won't repeat for at least 28 days

## First Customizations to Try

**Add a feed to your discovery pool:**

Edit `discovery_pool.json`, add an entry like:

```json
{
  "title": "Example Feed",
  "xmlUrl": "https://example.com/feed.xml",
  "htmlUrl": "https://example.com",
  "category": "tech",
  "tags": ["example"],
  "quality_score": 7,
  "last_included": null
}
```

Commit and push. Next rotation will include it in the pool.

**Change rotation frequency:**

Edit `rotation_config.json`:
- `"num_discovery_feeds": 10` = rotate 10 instead of 5
- `"rotation_frequency_days": 3` = rotate every 3 days instead of 7

**Add a core feed:**

Edit `core_feeds.opml`, add an `<outline>` element under the appropriate category.

Core feeds never rotate out - they're always included.

## Troubleshooting

**GitHub Actions fails:**
- Check the Actions tab for error details
- Most common: JSON syntax error (use a validator)

**Inoreader shows old feeds:**
- Inoreader polls periodically (you can't control frequency)
- Check if `docs/feeds.opml` was actually updated (look at commits)

**Want to force immediate rotation:**
- Manually trigger: Actions → Rotate Feeds → Run workflow
- Or edit `discovery_pool.json` and set `"last_included": null` for feeds you want

## Next Steps

Read the full [README.md](README.md) for:
- Detailed customization options
- Rotation algorithm explanation  
- Ideas for future enhancements
