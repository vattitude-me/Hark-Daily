const axios = require('axios');
const cheerio = require('cheerio');

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

    // Fetch CNN Canada page
    const response = await axios.get('https://www.cnn.com/world/americas/canada', {
      headers: {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
      }
    });

    const $ = cheerio.load(response.data);
    const news = [];

    // Method 1: Look for article links
    const articleLinks = $('a[href*="/2024/"], a[href*="/2025/"], a[href*="/2026/"]');
    
    // Method 2: Look for article containers
    const articleContainers = $('.container__item, .card, .media__content, article');
    
    // Combine and process elements
    const allElements = [...articleLinks.toArray(), ...articleContainers.toArray()];
    
    for (let i = 0; i < Math.min(allElements.length, 15); i++) {
      const element = allElements[i];
      const $element = $(element);
      
      try {
        let title = '';
        
        // Try different methods to extract title
        const titleSelectors = ['h1', 'h2', 'h3', 'h4', '.headline', '.title', '.media__title', '.container__title'];
        
        for (const selector of titleSelectors) {
          const titleElement = $element.find(selector).first();
          if (titleElement.length > 0) {
            title = titleElement.text().trim();
            break;
          }
        }
        
        // If no title found in children, try the element itself
        if (!title) {
          title = $element.text().trim();
        }
        
        // Clean and validate title
        title = title.replace(/\s+/g, ' ').trim();
        
        if (title && title.length > 20 && title.split(' ').length > 4) {
          const gist = generateGist(title);
          
          // Get URL
          let url = '';
          if ($element.attr('href')) {
            url = $element.attr('href');
            if (url && !url.startsWith('http')) {
              if (url.startsWith('/')) {
                url = 'https://www.cnn.com' + url;
              } else {
                url = 'https://www.cnn.com/' + url;
              }
            }
          }
          
          news.push({
            title: title,
            gist: gist,
            source: 'CNN Canada',
            time: new Date().toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' }),
            url: url
          });
        }
      } catch (error) {
        continue;
      }
    }

    // Remove duplicates
    const uniqueNews = news.filter((item, index, self) => 
      index === self.findIndex(t => t.title === t.title)
    );

    // Return top 10
    const result = uniqueNews.slice(0, 10);

    return {
      statusCode: 200,
      headers,
      body: JSON.stringify(result)
    };

  } catch (error) {
    console.error('Error fetching news:', error);
    
    return {
      statusCode: 500,
      headers: {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Headers': 'Content-Type',
        'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
      },
      body: JSON.stringify({ error: 'Failed to fetch news' })
    };
  }
};

function generateGist(title) {
  const words = title.split(' ');
  
  if (words.length < 5) {
    return `${title}\n\nThis is a breaking news story.\n\nMore details to follow.\n\nStay tuned for updates.`;
  }
  
  const firstPart = words.slice(0, 4).join(' ');
  const secondPart = words.slice(4, 8).join(' ');
  const thirdPart = words.slice(8, 12).join(' ');
  
  return `${firstPart}...\n\n${secondPart}\n\n${thirdPart || 'This story is developing.'}`;
}