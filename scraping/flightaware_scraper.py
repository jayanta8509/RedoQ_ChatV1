"""
FlightAware Web Scraper
This module scrapes flight data from FlightAware.com including all accessible sublinks.
"""

import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import time
import json
from typing import Set, Dict, List
import logging
from collections import deque

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class FlightAwareScraper:
    def __init__(self, base_urls: List[str] = None, max_pages: int = 100):
        """
        Initialize the FlightAware scraper.
        
        Args:
            base_urls: List of base URLs to start scraping from
            max_pages: Maximum number of pages to scrape (to prevent infinite crawling)
        """
        if base_urls is None:
            base_urls = ["https://www.flightaware.com/"]
        self.base_urls = base_urls if isinstance(base_urls, list) else [base_urls]
        self.max_pages = max_pages
        self.visited_urls: Set[str] = set()
        self.scraped_data: List[Dict] = []
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        
    def is_valid_url(self, url: str) -> bool:
        """Check if URL belongs to FlightAware domain."""
        parsed = urlparse(url)
        return parsed.netloc == 'www.flightaware.com' or parsed.netloc == 'flightaware.com'
    
    def get_page_content(self, url: str) -> BeautifulSoup:
        """
        Fetch and parse a webpage.
        
        Args:
            url: The URL to fetch
            
        Returns:
            BeautifulSoup object containing parsed HTML
        """
        try:
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            return BeautifulSoup(response.content, 'html.parser')
        except requests.RequestException as e:
            logger.error(f"Error fetching {url}: {e}")
            return None
    
    def extract_links(self, soup: BeautifulSoup, current_url: str) -> Set[str]:
        """
        Extract all valid links from a page.
        
        Args:
            soup: BeautifulSoup object of the page
            current_url: Current page URL for resolving relative links
            
        Returns:
            Set of absolute URLs found on the page
        """
        links = set()
        if not soup:
            return links
            
        for anchor in soup.find_all('a', href=True):
            href = anchor['href']
            absolute_url = urljoin(current_url, href)
            
            # Remove fragments and query parameters for deduplication
            parsed = urlparse(absolute_url)
            clean_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
            
            if self.is_valid_url(clean_url) and clean_url not in self.visited_urls:
                links.add(clean_url)
                
        return links
    
    def extract_page_data(self, soup: BeautifulSoup, url: str) -> Dict:
        """
        Extract relevant data from a page.
        
        Args:
            soup: BeautifulSoup object of the page
            url: URL of the page
            
        Returns:
            Dictionary containing extracted data
        """
        if not soup:
            return {}
        
        data = {
            'url': url,
            'title': '',
            'content': '',
            'metadata': {}
        }
        
        # Extract title
        title_tag = soup.find('title')
        if title_tag:
            data['title'] = title_tag.get_text(strip=True)
        
        # Extract main content
        # Remove script and style elements
        for script in soup(['script', 'style', 'nav', 'footer', 'header']):
            script.decompose()
        
        # Get text content
        text_content = soup.get_text(separator=' ', strip=True)
        data['content'] = ' '.join(text_content.split())  # Clean up whitespace
        
        # Extract meta tags
        meta_tags = soup.find_all('meta')
        for meta in meta_tags:
            if meta.get('name'):
                data['metadata'][meta.get('name')] = meta.get('content', '')
            elif meta.get('property'):
                data['metadata'][meta.get('property')] = meta.get('content', '')
        
        # Extract flight-specific data if present
        # This is a placeholder - you may need to adjust based on actual page structure
        flight_info = {}
        
        # Look for flight tables
        tables = soup.find_all('table')
        for table in tables:
            rows = table.find_all('tr')
            for row in rows:
                cells = row.find_all(['td', 'th'])
                if len(cells) >= 2:
                    key = cells[0].get_text(strip=True)
                    value = cells[1].get_text(strip=True)
                    if key and value:
                        flight_info[key] = value
        
        if flight_info:
            data['flight_info'] = flight_info
        
        return data
    
    def scrape(self) -> List[Dict]:
        """
        Main scraping method using BFS to crawl the website.
        
        Returns:
            List of dictionaries containing scraped data
        """
        logger.info(f"Starting scrape of {len(self.base_urls)} URL(s)")
        
        # Use BFS for crawling
        urls_to_visit = deque(self.base_urls)
        
        while urls_to_visit and len(self.visited_urls) < self.max_pages:
            current_url = urls_to_visit.popleft()
            
            if current_url in self.visited_urls:
                continue
            
            logger.info(f"Scraping ({len(self.visited_urls) + 1}/{self.max_pages}): {current_url}")
            
            # Mark as visited
            self.visited_urls.add(current_url)
            
            # Get page content
            soup = self.get_page_content(current_url)
            
            if soup:
                # Extract data from current page
                page_data = self.extract_page_data(soup, current_url)
                if page_data.get('content'):  # Only add if there's content
                    self.scraped_data.append(page_data)
                
                # Extract links for further crawling
                new_links = self.extract_links(soup, current_url)
                urls_to_visit.extend(new_links)
            
            # Be polite - don't hammer the server
            time.sleep(1)
        
        logger.info(f"Scraping complete. Collected {len(self.scraped_data)} pages.")
        return self.scraped_data
    
    def save_to_json(self, filename: str = 'flightaware_data.json'):
        """
        Save scraped data to a JSON file.
        
        Args:
            filename: Output filename
        """
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(self.scraped_data, f, indent=2, ensure_ascii=False)
        logger.info(f"Data saved to {filename}")


def scrape_flightaware(base_urls: List[str] = None, max_pages: int = 100, output_filename: str = 'flightaware_data.json') -> List[Dict]:
    """
    Main function to scrape FlightAware website.
    
    Args:
        base_urls: List of base URLs to start scraping from
        max_pages: Maximum number of pages to scrape
        output_filename: Name of the JSON file to save the scraped data
        
    Returns:
        List of dictionaries containing scraped data
    """
    scraper = FlightAwareScraper(base_urls=base_urls, max_pages=max_pages)
    data = scraper.scrape()
    scraper.save_to_json(filename=output_filename)
    return data


if __name__ == "__main__":
    # Example usage
    scraped_data = scrape_flightaware(
        base_urls=["https://www.flightaware.com/"],
        max_pages=500,
        output_filename='flightaware_data.json'
    )
