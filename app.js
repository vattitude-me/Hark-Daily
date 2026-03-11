// State Management
let currentIndex = 0;
let newsData = [];
let currentCountry = 'us';
let touchStartX = 0;
let touchEndX = 0;

// DOM Elements
const countrySelect = document.getElementById('countrySelect');
const refreshBtn = document.getElementById('refreshBtn');
const prevBtn = document.getElementById('prevBtn');
const nextBtn = document.getElementById('nextBtn');
const newsCarousel = document.getElementById('newsCarousel');
const loadingSpinner = document.getElementById('loadingSpinner');
const errorMessage = document.getElementById('errorMessage');
const warningMessage = document.getElementById('warningMessage');
const cardInfo = document.getElementById('cardInfo');

// Constants
const COUNTRIES = {
    'ca': 'Canada',
    'us': 'United States',
    'gb': 'United Kingdom',
    'au': 'Australia',
    'in': 'India',
    'de': 'Germany',
    'fr': 'France',
    'jp': 'Japan',
    'br': 'Brazil',
    'mx': 'Mexico'
};

// Format date helper
function formatDate(dateString) {
    const date = new Date(dateString);
    const now = new Date();
    const diff = now - date;
    const hours = Math.floor(diff / (1000 * 60 * 60));
    const days = Math.floor(hours / 24);

    if (hours < 1) return 'Just now';
    if (hours < 24) return `${hours}h ago`;
    if (days < 7) return `${days}d ago`;
    
    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

// Show loading spinner
function showLoading() {
    loadingSpinner.classList.remove('hidden');
}

function hideLoading() {
    loadingSpinner.classList.add('hidden');
}

// Show error message
function showError(message) {
    errorMessage.textContent = '❌ ' + message;
    errorMessage.classList.remove('hidden');
    setTimeout(() => {
        errorMessage.classList.add('hidden');
    }, 5000);
}

// Show warning message
function showWarning(message) {
    warningMessage.textContent = '⚠️ ' + message;
    warningMessage.classList.remove('hidden');
    setTimeout(() => {
        warningMessage.classList.add('hidden');
    }, 8000);
}

// Fetch news from backend
async function fetchNews(country) {
    showLoading();
    try {
        console.log(`📡 Fetching news for country: ${country}`);
        const controller = new AbortController();
        const timeoutId = setTimeout(() => {
            console.error('⏱️ Request timeout - aborting');
            controller.abort();
        }, 15000);
        
        const url = `/.netlify/functions/fetch-news?country=${country}`;
        console.log(`📍 API URL: ${url}`);
        
        const response = await fetch(url, {
            signal: controller.signal
        });
        clearTimeout(timeoutId);
        
        console.log(`✅ Response received - Status: ${response.status}`);
        
        if (!response.ok) {
            throw new Error(`API error: ${response.statusText}`);
        }

        const data = await response.json();
        console.log(`📦 Data received:`, data);

        // Check for warnings
        if (data.warning) {
            showWarning(data.warning);
        }

        if (data.error) {
            showError(data.error);
            hideLoading();
            return;
        }

        if (!data.articles || data.articles.length === 0) {
            showError('No news articles found. Try another country.');
            hideLoading();
            return;
        }

        newsData = data.articles;
        currentIndex = 0;
        render();
        hideLoading();
    } catch (error) {
        console.error('❌ Error fetching news:', error);
        if (error.name === 'AbortError') {
            showError('Request timeout. Please try again.');
        } else {
            showError('Failed to fetch news. Please try again.');
        }
        hideLoading();
    }
}

// Render news cards
function render() {
    newsCarousel.innerHTML = '';

    newsData.forEach((article, index) => {
        const card = createNewsCard(article, index);
        newsCarousel.appendChild(card);
    });

    updateCardCounter();
    updateNavigationButtons();
}

// Create a single news card
function createNewsCard(article, index) {
    const card = document.createElement('div');
    card.className = `news-card ${index === currentIndex ? 'active' : ''} ${index < currentIndex ? 'prev' : ''}`;

    const imageUrl = article.urlToImage || '';
    const title = article.title || 'No Title';
    const description = article.description || 'No description available';
    const source = article.source?.name || 'Unknown Source';
    const date = formatDate(article.publishedAt);
    const url = article.url;

    card.innerHTML = `
        ${imageUrl ? `<img src="${escapeHtml(imageUrl)}" alt="${escapeHtml(title)}" class="card-image" onerror="this.style.display='none'">` : `<div class="card-image no-image">📰</div>`}
        <div class="card-content">
            <h2 class="card-title">${escapeHtml(title)}</h2>
            <p class="card-description">${escapeHtml(description)}</p>
            <div class="card-meta">
                <span class="card-source">${escapeHtml(source)}</span>
                <span class="card-time">${date}</span>
            </div>
            <div class="card-actions">
                <a href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer" class="action-btn">
                    🔗 Read Full
                </a>
                <button class="action-btn" onclick="shareArticle('${escapeHtml(article.title)}', '${escapeHtml(url)}')">
                    📤 Share
                </button>
                <button class="action-btn" onclick="saveArticle('${escapeHtml(JSON.stringify(article))}')" title="Save for later">
                    💾 Save
                </button>
            </div>
        </div>
    `;

    return card;
}

// Escape HTML to prevent XSS
function escapeHtml(unsafe) {
    return unsafe
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/'/g, '&#039;')
        .replace(/"/g, '&quot;');
}

// Update card counter
function updateCardCounter() {
    if (newsData.length === 0) {
        cardInfo.textContent = 'No articles';
    } else {
        cardInfo.textContent = `${currentIndex + 1} of ${newsData.length}`;
    }
}

// Update navigation buttons
function updateNavigationButtons() {
    prevBtn.disabled = currentIndex === 0;
    nextBtn.disabled = currentIndex === newsData.length - 1;
}

// Navigate to specific card
function goToCard(index) {
    if (index < 0 || index >= newsData.length) return;

    // Update previous card
    document.querySelectorAll('.news-card').forEach((card, i) => {
        card.classList.remove('active', 'prev');
        if (i < index) {
            card.classList.add('prev');
        } else if (i === index) {
            card.classList.add('active');
        }
    });

    currentIndex = index;
    updateCardCounter();
    updateNavigationButtons();
}

// Next card
function nextCard() {
    if (currentIndex < newsData.length - 1) {
        goToCard(currentIndex + 1);
    }
}

// Previous card
function prevCard() {
    if (currentIndex > 0) {
        goToCard(currentIndex - 1);
    }
}

// Keyboard navigation
function handleKeyPress(event) {
    if (event.key === 'ArrowRight') nextCard();
    if (event.key === 'ArrowLeft') prevCard();
}

// Touch/Swipe handling
function handleTouchStart(e) {
    touchStartX = e.changedTouches[0].screenX;
}

function handleTouchEnd(e) {
    touchEndX = e.changedTouches[0].screenX;
    handleSwipe();
}

function handleSwipe() {
    const difference = touchStartX - touchEndX;
    const threshold = 50; // minimum swipe distance

    if (Math.abs(difference) > threshold) {
        if (difference > 0) {
            // Swiped left - show next
            nextCard();
        } else {
            // Swiped right - show previous
            prevCard();
        }
    }
}

// Share article
function shareArticle(title, url) {
    if (navigator.share) {
        navigator.share({
            title: 'Check out this news',
            text: title,
            url: url
        }).catch(err => console.log('Share cancelled'));
    } else {
        // Fallback: copy to clipboard
        const text = `${title}\n${url}`;
        navigator.clipboard.writeText(text).then(() => {
            showWarning('Link copied to clipboard!');
        });
    }
}

// Save article to localStorage
function saveArticle(articleJson) {
    try {
        const article = JSON.parse(articleJson);
        let saved = JSON.parse(localStorage.getItem('savedArticles') || '[]');
        
        // Check if already saved
        if (saved.some(a => a.url === article.url)) {
            showWarning('Article already saved!');
            return;
        }

        saved.push(article);
        localStorage.setItem('savedArticles', JSON.stringify(saved));
        showWarning(`✓ Article saved! (${saved.length} total)`);
    } catch (error) {
        console.error('Error saving article:', error);
    }
}

// Event Listeners
countrySelect.addEventListener('change', (e) => {
    currentCountry = e.target.value;
    fetchNews(currentCountry);
});

refreshBtn.addEventListener('click', () => {
    refreshBtn.classList.add('loading');
    refreshBtn.disabled = true;
    fetchNews(currentCountry);
    setTimeout(() => {
        refreshBtn.classList.remove('loading');
        refreshBtn.disabled = false;
    }, 500);
});

prevBtn.addEventListener('click', prevCard);
nextBtn.addEventListener('click', nextCard);

document.addEventListener('keydown', handleKeyPress);
newsCarousel.addEventListener('touchstart', handleTouchStart, false);
newsCarousel.addEventListener('touchend', handleTouchEnd, false);

// Initial load
window.addEventListener('DOMContentLoaded', () => {
    countrySelect.value = currentCountry;
    fetchNews(currentCountry);
});
