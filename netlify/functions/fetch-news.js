// Track API usage in memory (resets on function cold start)
// For production, use a database service
let requestTimestamps = [];
const DAILY_LIMIT = 1000;
const WARNING_THRESHOLD = 0.8; // Warn at 80% usage

// Clean old timestamps (older than 24 hours)
function cleanOldTimestamps() {
    const oneDayAgo = Date.now() - 24 * 60 * 60 * 1000;
    requestTimestamps = requestTimestamps.filter(ts => ts > oneDayAgo);
}

// Get remaining requests
function getRemainingRequests() {
    cleanOldTimestamps();
    return DAILY_LIMIT - requestTimestamps.length;
}

// Check if we should warn
function shouldWarn() {
    cleanOldTimestamps();
    const usagePercentage = requestTimestamps.length / DAILY_LIMIT;
    return usagePercentage >= WARNING_THRESHOLD;
}

// Helper function to make HTTPS request
async function makeRequest(url) {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 10000);
    
    try {
        const response = await fetch(url, {
            signal: controller.signal
        });
        const data = await response.json();
        return {
            status: response.status,
            data: data
        };
    } finally {
        clearTimeout(timeoutId);
    }
}

exports.handler = async (event) => {
    console.log('🔧 Function called:', { method: event.httpMethod, path: event.path });
    
    try {
        // CORS headers
        const headers = {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Content-Type',
            'Content-Type': 'application/json'
        };

        // Handle OPTIONS requests
        if (event.httpMethod === 'OPTIONS') {
            console.log('✅ Handling OPTIONS request');
            return {
                statusCode: 200,
                headers,
                body: JSON.stringify({ message: 'OK' })
            };
        }

        // Get API key from environment variables
        const apiKey = process.env.NEWS_API_KEY;
        if (!apiKey) {
            console.error('❌ NEWS_API_KEY not found in environment variables');
            return {
                statusCode: 500,
                headers,
                body: JSON.stringify({
                    error: 'Server configuration error. API key not found.'
                })
            };
        }

        // Get country from query parameters
        const country = event.queryStringParameters?.country || 'ca';
        console.log(`📍 Country requested: ${country}`);

        // Validate country parameter
        const validCountries = ['ca', 'us', 'gb', 'au', 'in', 'de', 'fr', 'jp', 'br', 'mx'];
        if (!validCountries.includes(country)) {
            return {
                statusCode: 400,
                headers,
                body: JSON.stringify({
                    error: `Invalid country code. Allowed: ${validCountries.join(', ')}`
                })
            };
        }

        // Track this request
        cleanOldTimestamps();
        const remaining = getRemainingRequests();

        if (remaining <= 0) {
            console.warn('❌ API LIMIT REACHED - Daily limit of 1000 requests exceeded');
            return {
                statusCode: 429,
                headers,
                body: JSON.stringify({
                    error: 'Daily API limit reached. Please try again tomorrow.',
                    remaining: 0
                })
            };
        }

        requestTimestamps.push(Date.now());
        const newRemaining = getRemainingRequests();
        const usagePercentage = Math.round(((DAILY_LIMIT - newRemaining) / DAILY_LIMIT) * 100);

        // Log request
        console.log(`📊 API Request #${DAILY_LIMIT - newRemaining} for country: ${country} | Remaining: ${newRemaining} (${usagePercentage}%)`);

        // Fetch news from NewsAPI
        const newsApiUrl = `https://newsapi.org/v2/top-headlines?country=${country}&apiKey=${apiKey}&pageSize=20`;
        
        console.log(`🔗 Calling NewsAPI for country: ${country}`);
        
        const response = await makeRequest(newsApiUrl);
        console.log(`📊 NewsAPI response status: ${response.status}`);

        if (response.status !== 200) {
            console.error(`❌ NewsAPI returned status ${response.status}:`, response.data);
            return {
                statusCode: response.status,
                headers,
                body: JSON.stringify({
                    error: response.data.message || `NewsAPI error: ${response.status}`
                })
            };
        }

        if (response.data.status !== 'ok') {
            console.error('❌ NewsAPI Error:', response.data);
            return {
                statusCode: 400,
                headers,
                body: JSON.stringify({
                    error: response.data.message || 'Failed to fetch news from NewsAPI'
                })
            };
        }

        console.log(`✅ NewsAPI returned ${response.data.articles?.length || 0} articles`);

        // Prepare response
        const result = {
            articles: response.data.articles || [],
            totalResults: response.data.totalResults,
            remaining: newRemaining,
            usage: usagePercentage,
            warning: null
        };

        // Add warning if approaching limit
        if (shouldWarn()) {
            const warningMsg = `⚠️ API USAGE WARNING: You've used ${usagePercentage}% of your daily limit (${DAILY_LIMIT - newRemaining}/${DAILY_LIMIT} requests)`;
            console.warn(warningMsg);
            result.warning = warningMsg;
        }

        console.log(`✅ Returning successful response with ${result.articles.length} articles`);
        return {
            statusCode: 200,
            headers,
            body: JSON.stringify(result)
        };
    } catch (error) {
        console.error('❌ Function error:', error.message);
        console.error('Error stack:', error.stack);

        const headers = {
            'Access-Control-Allow-Origin': '*',
            'Content-Type': 'application/json'
        };

        let errorMessage = 'Failed to fetch news. Please try again later.';
        let statusCode = 500;

        if (error.message.includes('timeout') || error.message.includes('ECONNABORTED')) {
            errorMessage = 'Request timeout. NewsAPI took too long to respond.';
            statusCode = 504;
        } else if (error.message.includes('Invalid JSON')) {
            errorMessage = 'Invalid response from NewsAPI.';
            statusCode = 502;
        }

        return {
            statusCode,
            headers,
            body: JSON.stringify({ error: errorMessage })
        };
    }
};
