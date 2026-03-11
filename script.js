// News Card Application
class NewsSwipeApp {
    constructor() {
        this.currentNews = [];
        this.currentIndex = 0;
        this.isSwiping = false;
        this.startX = 0;
        this.currentX = 0;
        
        // DOM Elements
        this.container = document.getElementById('news-container');
        this.loading = document.getElementById('loading');
        this.errorMessage = document.getElementById('error-message');
        this.refreshBtn = document.getElementById('refresh-btn');
        this.prevBtn = document.getElementById('prev-btn');
        this.nextBtn = document.getElementById('next-btn');
        
        // Event Listeners
        this.refreshBtn.addEventListener('click', () => this.loadNews());
        this.prevBtn.addEventListener('click', () => this.previousCard());
        this.nextBtn.addEventListener('click', () => this.nextCard());
        
        // Touch/Mouse Events for swiping
        this.container.addEventListener('mousedown', this.handleSwipeStart.bind(this));
        this.container.addEventListener('touchstart', this.handleSwipeStart.bind(this));
        window.addEventListener('mouseup', this.handleSwipeEnd.bind(this));
        window.addEventListener('touchend', this.handleSwipeEnd.bind(this));
        window.addEventListener('mousemove', this.handleSwipeMove.bind(this));
        window.addEventListener('touchmove', this.handleSwipeMove.bind(this), { passive: false });
        
        // Load initial news
        this.loadNews();
    }
    
    async loadNews() {
        try {
            this.showLoading();
            this.errorMessage.style.display = 'none';
            
            // Fetch news from Netlify Function with country parameter
            const country = 'ca'; // Canada - can be changed to any country code
            const response = await fetch(`/api/news?country=${country}`);
            if (!response.ok) {
                throw new Error('Failed to fetch news');
            }
            
            const newsData = await response.json();
            this.currentNews = newsData;
            this.currentIndex = 0;
            
            this.renderNews();
            this.updateControls();
        } catch (error) {
            console.error('Error loading news:', error);
            this.showError();
        }
    }
    
    renderNews() {
        // Clear existing cards
        this.container.innerHTML = '';
        
        if (this.currentNews.length === 0) {
            this.showError('No news available');
            return;
        }
        
        // Create 3 cards: previous, current, next
        const indices = this.getCardIndices();
        
        indices.forEach((index, position) => {
            if (index !== null) {
                const newsItem = this.currentNews[index];
                const card = this.createCard(newsItem, index);
                
                // Add appropriate class based on position
                if (position === 0) card.classList.add('previous');
                else if (position === 1) card.classList.add('current');
                else card.classList.add('next');
                
                this.container.appendChild(card);
            }
        });
        
        this.hideLoading();
    }
    
    createCard(newsItem, index) {
        const card = document.createElement('div');
        card.className = 'news-card';
        card.dataset.index = index;
        
        // Generate a random image URL for demo purposes
        const imageUrl = `https://source.unsplash.com/random/800x600?news,${encodeURIComponent(newsItem.title.split(' ')[0])}`;
        
        card.innerHTML = `
            <div class="card-image" style="background-image: url('${imageUrl}')"></div>
            <div class="card-content">
                <h2 class="card-title">${this.escapeHtml(newsItem.title)}</h2>
                <p class="card-gist">${this.escapeHtml(newsItem.gist)}</p>
                <div class="card-meta">
                    <span class="source">${newsItem.source || 'News Source'}</span>
                    <span class="time">${newsItem.time || ''}</span>
                </div>
            </div>
            <div class="swipe-hint">Swipe left for next story →</div>
        `;
        
        // Add swipe event listeners to the card
        card.addEventListener('mousedown', this.handleCardSwipeStart.bind(this));
        card.addEventListener('touchstart', this.handleCardSwipeStart.bind(this));
        
        return card;
    }
    
    getCardIndices() {
        const total = this.currentNews.length;
        if (total === 0) return [null, null, null];
        
        const current = this.currentIndex;
        const previous = current > 0 ? current - 1 : total - 1;
        const next = current < total - 1 ? current + 1 : 0;
        
        return [previous, current, next];
    }
    
    nextCard() {
        if (this.currentNews.length === 0) return;
        
        this.currentIndex = (this.currentIndex + 1) % this.currentNews.length;
        this.renderNews();
        this.updateControls();
    }
    
    previousCard() {
        if (this.currentNews.length === 0) return;
        
        this.currentIndex = this.currentIndex > 0 ? this.currentIndex - 1 : this.currentNews.length - 1;
        this.renderNews();
        this.updateControls();
    }
    
    updateControls() {
        const total = this.currentNews.length;
        if (total <= 1) {
            this.prevBtn.disabled = true;
            this.nextBtn.disabled = true;
        } else {
            this.prevBtn.disabled = false;
            this.nextBtn.disabled = false;
        }
    }
    
    // Swipe handling
    handleSwipeStart(e) {
        if (this.currentNews.length === 0) return;
        
        this.isSwiping = true;
        this.startX = e.type === 'touchstart' ? e.touches[0].clientX : e.clientX;
        this.currentX = this.startX;
        
        // Add active class to current card
        const currentCard = this.container.querySelector('.news-card.current');
        if (currentCard) {
            currentCard.style.transition = 'none';
        }
    }
    
    handleCardSwipeStart(e) {
        // Prevent default to avoid text selection during swipe
        e.preventDefault();
    }
    
    handleSwipeMove(e) {
        if (!this.isSwiping) return;
        
        this.currentX = e.type === 'touchmove' ? e.touches[0].clientX : e.clientX;
        const diff = this.currentX - this.startX;
        
        const currentCard = this.container.querySelector('.news-card.current');
        if (currentCard) {
            // Limit swipe distance
            const maxSwipe = 100;
            const swipeDistance = Math.max(-maxSwipe, Math.min(maxSwipe, diff));
            
            currentCard.style.transform = `translateX(${swipeDistance}px) scale(${1 - Math.abs(swipeDistance) / 500})`;
            currentCard.style.opacity = 1 - Math.abs(swipeDistance) / 300;
        }
    }
    
    handleSwipeEnd(e) {
        if (!this.isSwiping) return;
        
        this.isSwiping = false;
        const diff = this.currentX - this.startX;
        const threshold = 50; // Minimum swipe distance to trigger action
        
        const currentCard = this.container.querySelector('.news-card.current');
        if (currentCard) {
            currentCard.style.transition = 'transform 0.3s ease, opacity 0.3s ease';
            currentCard.style.transform = 'none';
            currentCard.style.opacity = '1';
        }
        
        if (Math.abs(diff) > threshold) {
            if (diff > 0) {
                this.previousCard();
            } else {
                this.nextCard();
            }
        }
    }
    
    // Utility functions
    showLoading() {
        this.loading.style.display = 'flex';
    }
    
    hideLoading() {
        this.loading.style.display = 'none';
    }
    
    showError(message = 'Failed to load news. Please try again.') {
        this.hideLoading();
        this.errorMessage.style.display = 'block';
        this.errorMessage.querySelector('p').textContent = message;
    }
    
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
}

// Initialize the app when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    new NewsSwipeApp();
});