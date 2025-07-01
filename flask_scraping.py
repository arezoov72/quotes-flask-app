from flask import Flask, render_template, request, url_for
import pandas as pd
import requests
from bs4 import BeautifulSoup
import csv
import os
import threading
import time
import math

app = Flask(__name__)

CSV_FILENAME = "quotes.csv"
QUOTES_PER_PAGE = 10
SCRAPE_INTERVAL_SECONDS = 3 * 60 * 60  # every 3 hours

def scrape_all_quotes(max_quotes=1000):
    """
    Scrape quotes from all pages up to max_quotes.
    """
    all_quotes = []
    page = 1

    while len(all_quotes) < max_quotes:
        url = f"http://quotes.toscrape.com/page/{page}/"
        res = requests.get(url)

        if res.status_code != 200:
            break

        soup = BeautifulSoup(res.text, "html.parser")
        quotes_divs = soup.find_all("div", class_="quote")

        if not quotes_divs:
            break

        for div in quotes_divs:
            text = div.find("span", class_="text").get_text(strip=True)
            author = div.find("small", class_="author").get_text(strip=True)
            tags = [t.get_text(strip=True) for t in div.find_all("a", class_="tag")]
            all_quotes.append({
                "quote": text,
                "author": author,
                "tags": ", ".join(tags)
            })

            if len(all_quotes) >= max_quotes:
                break

        page += 1

    return all_quotes

def save_quotes_to_csv(quotes):
    with open(CSV_FILENAME, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["quote", "author", "tags"])
        writer.writeheader()
        writer.writerows(quotes)

def load_quotes_from_csv():
    if not os.path.exists(CSV_FILENAME):
        return pd.DataFrame(columns=["quote", "author", "tags"])
    return pd.read_csv(CSV_FILENAME)

def update_quotes_if_new():
    """
    Checks the website for new quotes and updates the CSV if new ones appear.
    """
    print("Checking for updates...")
    existing_df = load_quotes_from_csv()
    existing_quotes_texts = set(existing_df["quote"])

    new_scraped = scrape_all_quotes(max_quotes=1000)

    # Keep only new quotes
    new_quotes = [
        q for q in new_scraped if q["quote"] not in existing_quotes_texts
    ]

    if new_quotes:
        print(f"✨ Found {len(new_quotes)} new quote(s). Adding to CSV.")
        combined = pd.concat([existing_df, pd.DataFrame(new_quotes)], ignore_index=True)
        combined = combined.drop_duplicates(subset=["quote"])
        combined.to_csv(CSV_FILENAME, index=False, encoding="utf-8")
    else:
        print("✅ No update. No new quotes found.")

def scraper_loop():
    """
    Background loop to check every SCRAPE_INTERVAL_SECONDS.
    """
    while True:
        try:
            update_quotes_if_new()
        except Exception as e:
            print(f"Error during scraping: {e}")
        time.sleep(SCRAPE_INTERVAL_SECONDS)

# Launch the background scraper thread
threading.Thread(target=scraper_loop, daemon=True).start()

@app.route("/")
def index():
    df = load_quotes_from_csv()

    # Filters
    search_query = request.args.get("search", "").strip()
    author_filter = request.args.get("author", "").strip()
    tag_filter = request.args.get("tag", "").strip()
    page = int(request.args.get("page", 1))

    # Apply search
    if search_query:
        mask = df.apply(
            lambda row: row.astype(str).str.contains(search_query, case=False).any(),
            axis=1
        )
        df = df[mask]

    # Filter by author
    if author_filter:
        df = df[df["author"] == author_filter]

    # Filter by tag
    if tag_filter:
        df = df[df["tags"].str.contains(tag_filter, case=False, na=False)]

    # Pagination
    total_quotes = len(df)
    total_pages = max(1, math.ceil(total_quotes / QUOTES_PER_PAGE))
    start = (page - 1) * QUOTES_PER_PAGE
    end = start + QUOTES_PER_PAGE
    page_quotes = df.iloc[start:end].to_dict(orient="records")

    # Collect all unique tags for the filter dropdown
    all_tags = sorted({
        tag.strip()
        for tags in df["tags"].dropna()
        for tag in tags.split(",")
        if tag.strip()
    })

    return render_template(
        "index.html",
        quotes=page_quotes,
        search_query=search_query,
        author_filter=author_filter,
        tag_filter=tag_filter,
        all_tags=all_tags,
        current_page=page,
        total_pages=total_pages,
    )

if __name__ == "__main__":
    # On first run, scrape data if CSV is missing
    if not os.path.exists(CSV_FILENAME):
        print("No CSV found. Scraping fresh quotes...")
        quotes = scrape_all_quotes(max_quotes=1000)
        save_quotes_to_csv(quotes)
        print(f"Saved {len(quotes)} quotes to CSV.")

    app.run(debug=True)
