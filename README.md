# News Extractor Web App

A responsive, modern news application built with HTML, CSS, and JavaScript. Displays top headlines with an InShorts-style card interface that supports swiping, keyboard navigation, and a country selector.

## Features

✨ **Responsive Card Interface**
- Modern card-based design inspired by InShorts
- Swipe left/right to navigate (touch devices)
- Arrow keys or navigation buttons for desktop
- Smooth animations and transitions

🌍 **Country Selector**
- Select from 10+ countries (Canada, US, UK, Australia, India, Germany, France, Japan, Brazil, Mexico)
- Defaults to Canada
- Instant news refresh on country change

🔄 **Smart API Management**
- Built with Netlify Functions for serverless backend
- Daily request limit: 1000 (NewsAPI quota)
- Automatic usage tracking and warnings
- Warns when reaching 80% of daily limit

📱 **User-Friendly Features**
- Share articles via native share or copy to clipboard
- Save articles to browser storage
- Read full articles on NewsAPI source
- Timestamps showing how long ago article was published

## Project Structure

```
News_Extractor_Claude/
├── index.html              # Main HTML file
├── app.js                  # Frontend JavaScript
├── styles.css              # Responsive styling
├── package.json            # Dependencies
├── netlify.toml            # Netlify configuration
├── .gitignore              # Git ignore rules
└── netlify/
    └── functions/
        └── fetch-news.js   # Serverless API function
```

## Setup & Installation

### Prerequisites
- Node.js (v14 or higher)
- Git
- Netlify CLI (optional but recommended)
- NewsAPI key from [newsapi.org](https://newsapi.org)

### Local Development

1. **Clone the repository**
```bash
git clone <repository-url>
cd News_Extractor_Claude
```

2. **Install dependencies**
```bash
npm install
```

3. **Set up environment variables**

Create a `.env` file in the root directory:
```
NEWS_API_KEY=your_news_api_key_here
```

4. **Run locally**

Using Netlify CLI (recommended):
```bash
netlify dev
```

This starts the app at `http://localhost:8888` with local function support.

Alternatively, use Python's simple server for static files:
```bash
python -m http.server 8000
# Then access http://localhost:8000
```

Note: Without the Netlify Functions running, you'll need to configure CORS or use a proxy.

## Deployment to Netlify

### Step 1: Push to Git

```bash
git add .
git commit -m "Initial commit: News app with Netlify Functions"
git push origin main
```

### Step 2: Connect to Netlify

1. Go to [netlify.com](https://netlify.com) and sign in
2. Click "New site from Git"
3. Select your repository
4. Netlify will auto-detect `netlify.toml` settings

### Step 3: Set Environment Variables

In Netlify Dashboard:
1. Go to Site Settings → Build & Deploy → Environment
2. Add new variable:
   - **Key:** `NEWS_API_KEY`
   - **Value:** Your NewsAPI key

### Step 4: Deploy

Just push to your main branch - Netlify will automatically deploy!

```bash
git push origin main
```

## API Limits & Monitoring

**NewsAPI Limits:**
- 1,000 requests per day (free tier)
- 100 requests per day per IP/key in development

**Usage Tracking:**
- The backend logs all API requests
- Warning appears when usage reaches 80% (800 requests)
- Requests blocked when limit is reached
- Check Netlify Functions logs to monitor usage

View logs:
```bash
netlify logs --functions
```

## Browser Support

- Chrome/Edge (latest)
- Firefox (latest)
- Safari (latest)
- Mobile browsers supporting Fetch API

## File Descriptions

### `index.html`
- HTML structure with header, news carousel, navigation
- Country dropdown selector
- Refresh button
- Loading spinner and error/warning messages

### `app.js`
- Frontend state management
- News card rendering
- Touch/swipe event handling
- Keyboard navigation (arrow keys)
- Share and save functionality
- Date formatting utilities

### `styles.css`
- Mobile-first responsive design
- Card animations and transitions
- Flexbox layout
- Touch-friendly button sizes
- Dark mode compatible gradient background

### `netlify/functions/fetch-news.js`
- Serverless function to fetch from NewsAPI
- API key management via environment variables
- Request counting and usage warnings
- Error handling and CORS support
- Timeout and rate limit handling

### `netlify.toml`
- Build and publish configuration
- Function directory specification
- Redirect rules for SPA routing
- Cache headers for performance

## Keyboard Shortcuts

- **←** Left arrow: Previous article
- **→** Right arrow: Next article
- **Touch swipe**: Left/right to navigate

## Troubleshooting

**"API key not found" error:**
- Check that `NEWS_API_KEY` is set in Netlify environment variables
- Verify the `.env` file in local development

**CORS errors:**
- Ensure the Netlify Functions are running (`netlify dev`)
- Check browser console for detailed error messages

**No articles appear:**
- Verify your NewsAPI key is valid
- Check internet connection
- Try a different country
- Check Netlify function logs for API errors

**Blank cards:**
- Some articles may not have images - they'll show a 📰 emoji instead
- This is expected behavior

## Future Enhancements

- [ ] Category filtering (business, tech, sports, etc.)
- [ ] Search functionality
- [ ] Advanced saved articles management with export
- [ ] Dark mode toggle
- [ ] Multiple language support
- [ ] Caching layer to reduce API calls
- [ ] Better error recovery and retry logic

## License

MIT - Feel free to use this project for personal or commercial purposes.

## Support

For issues or questions:
1. Check the browser console for error details
2. Review Netlify function logs
3. Verify NewsAPI key and connectivity

---

**Built with:** HTML5, CSS3, Vanilla JavaScript, Netlify Functions, NewsAPI
