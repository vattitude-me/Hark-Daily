#!/usr/bin/env python3
"""
Simple Flask server for the News Swipe App
Provides news scraping functionality and serves static files
"""

from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS
import requests
from bs4 import BeautifulSoup
import random
from datetime import datetime
import os

app = Flask(__name__, static_folder='.')
CORS(app)  # Enable CORS for all routes

class NewsScraper:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
    
    def scrape_reddit_worldnews(self):
        """Scrape top posts from r/worldnews"""
        try:
            url = 'https://www.reddit.com/r/worldnews/top/?t=day'
            response = self.session.get(url)
            soup = BeautifulSoup(response.content, 'html.parser')
            
            posts = []
            # Reddit uses data attributes and specific classes
            post_elements = soup.find_all('div', {'data-testid': 'post-container'})
            
            for post in post_elements[:10]:  # Get top 10
                try:
                    title_elem = post.find('h3')
                    if title_elem:
                        title = title_elem.text.strip()
                        # Generate a simple gist from the title
                        gist = self.generate_gist(title)
                        
                        posts.append({
                            'title': title,
                            'gist': gist,
                            'source': 'Reddit World News',
                            'time': datetime.now().strftime('%H:%M'),
                            'url': f"https://reddit.com{post.find('a')['href']}" if post.find('a') else ''
                        })
                except Exception as e:
                    continue
            
            return posts
        except Exception as e:
            print(f"Error scraping Reddit: {e}")
            return []
    
    def scrape_cnn_canada(self):
        """Scrape CNN Canada news headlines"""
        try:
            url = 'https://www.cnn.com/world/americas/canada'
            response = self.session.get(url)
            soup = BeautifulSoup(response.content, 'html.parser')
            
            posts = []
            
            # CNN uses various article containers - look for multiple patterns
            # Pattern 1: Standard article links
            article_links = soup.find_all('a', href=True)
            
            # Pattern 2: Look for article containers
            article_containers = soup.find_all(['article', 'div'], class_=['container__item', 'card', 'media__content'])
            
            # Combine both approaches
            all_elements = article_links + article_containers
            
            for element in all_elements[:15]:  # Get up to 15 items
                try:
                    # Try to find title in different ways
                    title_elem = None
                    
                    # Method 1: Direct text in the element
                    if hasattr(element, 'text') and element.text.strip():
                        title_text = element.text.strip()
                        if len(title_text) > 20 and len(title_text.split()) > 3:  # Reasonable title length
                            title_elem = element
                    
                    # Method 2: Look for h1, h2, h3 tags within the element
                    if not title_elem:
                        for tag in ['h1', 'h2', 'h3', 'h4']:
                            title_elem = element.find(tag)
                            if title_elem and title_elem.text.strip():
                                break
                    
                    # Method 3: Look for specific classes that might contain titles
                    if not title_elem:
                        for class_pattern in ['headline', 'title', 'media__title', 'container__title']:
                            title_elem = element.find(class_=lambda x: x and class_pattern in str(x).lower())
                            if title_elem and title_elem.text.strip():
                                break
                    
                    if title_elem:
                        title = title_elem.text.strip()
                        # Clean up the title
                        title = ' '.join(title.split())  # Remove extra whitespace
                        
                        if len(title) > 20 and len(title.split()) > 4:  # Filter out short/uninformative titles
                            gist = self.generate_gist(title)
                            
                            # Try to get URL
                            url = ''
                            if hasattr(element, 'get') and element.get('href'):
                                url = element.get('href')
                                if url and not url.startswith('http'):
                                    if url.startswith('/'):
                                        url = 'https://www.cnn.com' + url
                                    else:
                                        url = 'https://www.cnn.com/' + url
                            
                            posts.append({
                                'title': title,
                                'gist': gist,
                                'source': 'CNN Canada',
                                'time': datetime.now().strftime('%H:%M'),
                                'url': url
                            })
                except Exception as e:
                    continue
            
            # Remove duplicates based on title
            seen_titles = set()
            unique_posts = []
            for post in posts:
                if post['title'] not in seen_titles:
                    seen_titles.add(post['title'])
                    unique_posts.append(post)
            
            return unique_posts[:10]  # Return top 10 unique posts
            
        except Exception as e:
            print(f"Error scraping CNN Canada: {e}")
            return []
    
    def generate_gist(self, title):
        """Generate a 5-line gist from a news title"""
        # Split title into key phrases
        words = title.split()
        
        # Create a simple 5-line gist
        if len(words) < 5:
            return f"{title}\n\nThis is a breaking news story.\n\nMore details to follow.\n\nStay tuned for updates."
        
        # Take first few words and create a summary
        first_part = ' '.join(words[:4])
        second_part = ' '.join(words[4:8]) if len(words) > 4 else ''
        third_part = ' '.join(words[8:12]) if len(words) > 8 else ''
        
        gist_lines = [
            f"{first_part}...",
            "",
            f"{second_part}",
            "",
            f"{third_part}" if third_part else "This story is developing."
        ]
        
        return '\n'.join(gist_lines)
    
    def get_news(self):
        """Get news from multiple sources"""
        all_news = []
        
        # Try CNN Canada first
        cnn_news = self.scrape_cnn_canada()
        all_news.extend(cnn_news)
        
        # If CNN fails or we need more news, try Reddit
        if len(all_news) < 5:
            reddit_news = self.scrape_reddit_worldnews()
            all_news.extend(reddit_news)
        
        # If still not enough, generate some demo news
        if len(all_news) < 3:
            all_news.extend(self.generate_demo_news())
        
        # Remove duplicates and shuffle
        seen_titles = set()
        unique_news = []
        for news in all_news:
            if news['title'] not in seen_titles:
                seen_titles.add(news['title'])
                unique_news.append(news)
        
        random.shuffle(unique_news)
        return unique_news[:15]  # Return top 15
    
    def generate_demo_news(self):
        """Generate demo news if scraping fails"""
        demo_topics = [
            "Technology", "Politics", "Sports", "Science", "Health", 
            "Environment", "Business", "Entertainment", "Education", "International"
        ]
        
        demo_news = []
        for i in range(5):
            topic = random.choice(demo_topics)
            demo_news.append({
                'title': f"Breaking: Major {topic} Development Unfolds",
                'gist': f"This is a significant {topic.lower()} story that is currently developing.\n\nAuthorities are investigating the situation.\n\nMore information will be provided as it becomes available.\n\nStay tuned for updates.",
                'source': 'Demo News',
                'time': datetime.now().strftime('%H:%M'),
                'url': ''
            })
        
        return demo_news

# Initialize scraper
scraper = NewsScraper()

@app.route('/api/news')
def get_news():
    """API endpoint to get news headlines"""
    try:
        news = scraper.get_news()
        return jsonify(news)
    except Exception as e:
        print(f"Error in API: {e}")
        return jsonify([]), 500

@app.route('/')
def serve_index():
    """Serve the main HTML file"""
    return send_from_directory('.', 'index.html')

@app.route('/<path:filename>')
def serve_static(filename):
    """Serve static files (CSS, JS, etc.)"""
    return send_from_directory('.', filename)

if __name__ == '__main__':
    print("Starting News Swipe Server...")
    print("Visit http://localhost:5000 to view the app")
    app.run(debug=True, host='0.0.0.0', port=5000)