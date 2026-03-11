import axios from 'axios';

// Track API usage in memory (resets on function cold start)
// For production, use a database service
let requestCount = 0;
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

export const handler = async (event) => {
    try {
        // CORS headers
        const headers = {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Content-Type',
            'Content-Type': 'application/json'
        };

        // Handle OPTIONS requests
        if (event.httpMethod === 'OPTIONS') {
            return {
                statusCode: 200,
                headers,
                body: JSON.stringify({ message: 'OK' })
            };
        }

        // Get API key from environment variables
        const apiKey = process.env.NEWS_API_KEY;
        if (!apiKey) {
            console.error('NEWS_API_KEY not found in environment variables');
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
        const newsApiUrl = `https://newsapi.org/v2/top-headlines`;
        const response = await axios.get(newsApiUrl, {
            params: {
                country: country,
                apiKey: apiKey,
                pageSize: 20,
                sortBy: 'publishedAt'
            },
            timeout: 10000
        });

        if (response.data.status !== 'ok') {
            console.error('NewsAPI Error:', response.data);
            return {
                statusCode: 400,
                headers,
                body: JSON.stringify({
                    error: response.data.message || 'Failed to fetch news from NewsAPI'
                })
            };
        }

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

        return {
            statusCode: 200,
            headers,
            body: JSON.stringify(result)
        };
    } catch (error) {
        console.error('Function error:', error);

        const headers = {
            'Access-Control-Allow-Origin': '*',
            'Content-Type': 'application/json'
        };

        let errorMessage = 'Failed to fetch news. Please try again later.';
        let statusCode = 500;

        if (error.code === 'ECONNABORTED') {
            errorMessage = 'Request timeout. Please try again.';
            statusCode = 504;
        } else if (error.response?.status === 401) {
            errorMessage = 'Invalid API key. Check server configuration.';
            statusCode = 401;
        } else if (error.response?.status === 429) {
            errorMessage = 'NewsAPI rate limit reached. Please try again later.';
            statusCode = 429;
        }

        return {
            statusCode,
            headers,
            body: JSON.stringify({ error: errorMessage })
        };
    }
};
