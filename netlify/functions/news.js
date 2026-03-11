const axios = require('axios');

exports.handler = async (event, context) => {
  try {
    // Set CORS headers
    const headers = {
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Headers': 'Content-Type',
      'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
    };

    // Handle preflight requests
    if (event.httpMethod === 'OPTIONS') {
      return {
        statusCode: 200,
        headers,
        body: JSON.stringify({ message: 'CORS preflight' })
      };
    }

    // Get country from query parameter or default to 'ca' (Canada)
    const url = new URL(event.path, `https://${event.headers.host}`);
    const country = url.searchParams.get('country') || 'ca';
    
    // Get API key from environment variables (Netlify secrets)
    const apiKey = process.env.NEWS_API_KEY;
    
    if (!apiKey) {
      console.log('No API key found, using demo news');
      const demoNews = generateDemoNews();
      return {
        statusCode: 200,
        headers,
        body: JSON.stringify(demoNews)
      };
    }

    try {
      // Fetch news from NewsAPI.org
      const response = await axios.get('https://newsapi.org/v2/top-headlines', {
        params: {
          country: country,
          apiKey: apiKey,
          pageSize: 10
        },
        headers: {
          'User-Agent': 'NewsSwipeApp/1.0'
        },
        timeout: 10000
      });

      const apiNews = response.data.articles;
      
      if (apiNews && apiNews.length > 0) {
        // Transform NewsAPI response to our format
        const news = apiNews.map(article => ({
          title: article.title || 'Breaking News',
          gist: generateGist(article.description || article.title || 'News story'),
          source: article.source?.name || 'News Source',
          time: new Date(article.publishedAt).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' }),
          url: article.url || ''
        })).filter(newsItem => newsItem.title && newsItem.title.length > 10);

        return {
          statusCode: 200,
          headers,
          body: JSON.stringify(news.slice(0, 8))
        };
      }
    } catch (apiError) {
      console.log('NewsAPI failed:', apiError.message);
    }

    // Fallback to demo news if API fails
    const demoNews = generateDemoNews();
    return {
      statusCode: 200,
      headers,
      body: JSON.stringify(demoNews)
    };

  } catch (error) {
    console.error('Error in news function:', error);
    
    // Final fallback with minimal demo news
    const minimalNews = [
      {
        title: "Breaking: Technology News",
        gist: "This is a significant technology story that is currently developing.\n\nAuthorities are investigating the situation.\n\nMore information will be provided as it becomes available.\n\nStay tuned for updates.",
        source: 'Demo News',
        time: new Date().toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' }),
        url: ''
      },
      {
        title: "Breaking: Politics News", 
        gist: "This is a significant politics story that is currently developing.\n\nAuthorities are investigating the situation.\n\nMore information will be provided as it becomes available.\n\nStay tuned for updates.",
        source: 'Demo News',
        time: new Date().toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' }),
        url: ''
      }
    ];

    return {
      statusCode: 200,
      headers: {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Headers': 'Content-Type',
        'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
      },
      body: JSON.stringify(minimalNews)
    };
  }
};

function generateGist(description) {
  if (!description) return "Breaking news story.\n\nMore details to follow.\n\nStay tuned for updates.";
  
  const sentences = description.split(/[.!?]+/).filter(s => s.trim().length > 0);
  
  if (sentences.length >= 3) {
    return `${sentences[0].trim()}.\n\n${sentences[1].trim()}.\n\n${sentences[2].trim()}.`;
  } else if (sentences.length === 2) {
    return `${sentences[0].trim()}.\n\n${sentences[1].trim()}.\n\nThis story is developing.`;
  } else {
    return `${description}\n\nMore details to follow.\n\nStay tuned for updates.`;
  }
}

function generateDemoNews() {
  const topics = [
    "Technology", "Politics", "Sports", "Science", "Health", 
    "Environment", "Business", "Entertainment", "Education", "International"
  ];
  
  const news = [];
  
  for (let i = 0; i < 8; i++) {
    const topic = topics[i % topics.length];
    news.push({
      title: `Breaking: Major ${topic} Development`,
      gist: `This is a significant ${topic.toLowerCase()} story that is currently developing.\n\nAuthorities are investigating the situation.\n\nMore information will be provided as it becomes available.\n\nStay tuned for updates.`,
      source: 'Demo News',
      time: new Date().toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' }),
      url: ''
    });
  }
  
  return news;
}
