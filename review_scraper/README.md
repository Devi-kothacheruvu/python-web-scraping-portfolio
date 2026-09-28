# Amazon Review Scraper

A Python-based Amazon review scraper built using **Playwright and Crawl4AI**.

## Features

- Scrapes Amazon product reviews
- Uses Playwright for browser automation
- Uses Crawl4AI for crawling and dynamic page processing
- Loads additional reviews when available
- Removes duplicate reviews using review IDs
- Extracts reviewer information and review details
- Saves data in CSV and JSON formats
- Provides rating-wise review counts

## Data Extracted

The scraper collects:

- Review ID
- Reviewer name
- Rating
- Review title
- Review text
- Review date
- Verified purchase status
- Helpful votes
- Review URL

## Technologies Used

- Python
- Playwright
- Crawl4AI
- BeautifulSoup
- CSV
- JSON

## Project Structure

```text
review_scraper/
│
├── amazon_browser/
├── amazon_reviews.csv
├── amazon_reviews.json
├── review_scraper.py
└── README.md