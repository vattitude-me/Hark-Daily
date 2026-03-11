# Quick Start Guide

## 1. Get Your NewsAPI Key

1. Visit [newsapi.org](https://newsapi.org)
2. Sign up for a free account
3. Copy your API key from the dashboard

## 2. Local Development Setup

```bash
# Install dependencies
npm install

# Create .env file with your API key
echo 'NEWS_API_KEY=your_key_here' > .env

# Start development server
netlify dev
```

Visit `http://localhost:8888`

## 3. Deploy to Netlify

### Option A: Using CLI

```bash
# Install Netlify CLI
npm install -g netlify-cli

# Deploy
netlify deploy --prod
```

### Option B: Using GitHub

1. Push code to GitHub:
```bash
git add .
git commit -m "Initial commit"
git push origin main
```

2. In Netlify Dashboard:
   - Click "New site from Git"
   - Select your GitHub repo
   - Add `NEWS_API_KEY` in Build & Deploy → Environment
   - Deploy

## 4. Set Environment Variables in Netlify

**Netlify Dashboard → Site Settings → Build & Deploy → Environment**

Add:
- Key: `NEWS_API_KEY`
- Value: Your API key from newsapi.org

## 5. Test the App

- Open your Netlify URL
- Try different countries from dropdown
- Test navigation with arrow keys or swipes
- Share and save articles

## API Limit Tracking

You'll see:
- ✅ Green: Normal usage (0-80%)
- ⚠️ Yellow: Warning (80%+)
- ❌ Red: Limit reached (1000/1000)

Check logs: `netlify logs --functions`

## Troubleshooting

| Issue | Solution |
|-------|----------|
| "API key not found" | Set `NEWS_API_KEY` in .env or Netlify dashboard |
| CORS errors | Make sure using Netlify functions via `/.netlify/functions/fetch-news` |
| No articles | Check internet, try different country, verify API key validity |
| Blank images | Normal - some articles don't have images, shows 📰 emoji |

## Common Commands

```bash
# Local development
netlify dev

# View live logs
netlify logs --functions

# Deploy manually
netlify deploy --prod

# Check status
netlify status
```

That's it! Your news app is ready to use. 🚀
