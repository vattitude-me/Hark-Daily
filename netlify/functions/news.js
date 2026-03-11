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

    // Generate demo news as fallback (always works)
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
        title: "Breaking: Technology News in Canada",
        gist: "This is a significant technology story that is currently developing.\n\nAuthorities are investigating the situation.\n\nMore information will be provided as it becomes available.\n\nStay tuned for updates.",
        source: 'Demo News',
        time: new Date().toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' }),
        url: ''
      },
      {
        title: "Breaking: Politics News in Canada", 
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

function generateDemoNews() {
  const topics = [
    "Technology", "Politics", "Sports", "Science", "Health", 
    "Environment", "Business", "Entertainment", "Education", "International"
  ];
  
  const news = [];
  
  for (let i = 0; i < 8; i++) {
    const topic = topics[i % topics.length];
    news.push({
      title: `Breaking: Major ${topic} Development in Canada`,
      gist: `This is a significant ${topic.toLowerCase()} story that is currently developing.\n\nAuthorities are investigating the situation.\n\nMore information will be provided as it becomes available.\n\nStay tuned for updates.`,
      source: 'Demo News',
      time: new Date().toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' }),
      url: ''
    });
  }
  
  return news;
}
