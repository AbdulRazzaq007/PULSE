#!/usr/bin/env python3
"""
saas_review_scraper_fixed.scraper
A simple, extensible CLI scraper for G2, Capterra and TrustRadius reviews.
Usage (examples):
  python scraper.py --source g2 --company "Zoom" --start 2023-01-01 --end 2024-12-31 --output zoom_reviews.json
  python scraper.py --source capterra --company "Zoom" --output zoom_capterra.json
Notes:
- This script performs live web requests when you run it. It does not include
  any external credentials.
- Results depend on the target site structure and may need maintenance.
- Use responsibly and follow each site's robots.txt and terms of service.
"""
import argparse
import json
import sys
import time
from datetime import datetime
from typing import List, Dict, Any, Optional

import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0 Safari/537.36"
}

def parse_date_try(dt_str: str) -> Optional[datetime]:
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d %B %Y", "%B %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(dt_str.strip(), fmt)
        except Exception:
            pass
    # fallback
    try:
        return datetime.fromisoformat(dt_str)
    except Exception:
        return None

def within_range(date_obj: datetime, start: Optional[datetime], end: Optional[datetime]) -> bool:
    if start and date_obj < start:
        return False
    if end and date_obj > end:
        return False
    return True

def scrape_g2(company: str, start: Optional[datetime], end: Optional[datetime]) -> List[Dict[str,Any]]:
    """
    Very basic G2 scraper:
    - Accepts either a product page URL (if 'company' contains 'http') or a company/product name.
    - If given a name, attempts to use G2 search page to find a first matching product.
    """
    reviews = []
    session = requests.Session()
    session.headers.update(HEADERS)

    # If company looks like a URL, use it directly
    if company.startswith("http"):
        product_url = company.rstrip("/")
    else:
        # Use G2 search to find product slug (best-effort)
        q = company.replace(" ", "+")
        search_url = f"https://www.g2.com/search?q={q}"
        r = session.get(search_url, timeout=20)
        soup = BeautifulSoup(r.text, "html.parser")
        # find first product link
        link = soup.find("a", {"data-qa": "product-card-link"})
        if link and link.get("href"):
            product_url = "https://www.g2.com" + link.get("href")
        else:
            # fallback: construct simple slug (may fail)
            slug = company.lower().replace(" ", "-")
            product_url = f"https://www.g2.com/products/{slug}/reviews"

    # iterate pages
    page = 1
    while True:
        page_url = product_url + (f"?page={page}" if "?" not in product_url else f"&page={page}")
        print("Fetching", page_url, file=sys.stderr)
        r = session.get(page_url, timeout=20)
        if r.status_code != 200:
            break
        soup = BeautifulSoup(r.text, "html.parser")
        items = soup.select("div[itemprop='review']")
        if not items:
            # try alternate selector used by G2 front-end cards
            items = soup.select("div.g2-review, div.review-card, div[class*='review']")
        if not items:
            break
        added = 0
        for it in items:
            # Extract title, body, date, rating
            title = it.find(lambda tag: tag.name in ["h3","h4","h2"])
            title_text = title.get_text(strip=True) if title else ""
            body_tag = it.find("p")
            body_text = body_tag.get_text(" ", strip=True) if body_tag else ""
            date_tag = it.find(lambda tag: tag.name == "time" or (tag.name=="span" and "date" in (tag.get("class") or [])))
            date_text = date_tag.get("datetime") if date_tag and date_tag.get("datetime") else (date_tag.get_text(strip=True) if date_tag else "")
            date_obj = parse_date_try(date_text) if date_text else None
            if date_obj and not within_range(date_obj, start, end):
                continue
            rating_tag = it.find(attrs={"data-qa":"rating"})
            rating = rating_tag.get_text(strip=True) if rating_tag else ""
            reviewer = it.find(attrs={"data-qa":"reviewer-name"}) or it.find("strong")
            reviewer_text = reviewer.get_text(strip=True) if reviewer else ""
            review = {
                "title": title_text,
                "review": body_text,
                "date": date_obj.isoformat() if date_obj else date_text,
                "rating": rating,
                "reviewer": reviewer_text,
                "source": "g2",
            }
            reviews.append(review)
            added += 1
        if added == 0:
            break
        page += 1
        time.sleep(1.0)
    return reviews

def scrape_capterra(company: str, start: Optional[datetime], end: Optional[datetime]) -> List[Dict[str,Any]]:
    """
    Simple Capterra scraper. Accepts company name OR a direct Capterra product URL.
    """
    reviews = []
    session = requests.Session()
    session.headers.update(HEADERS)
    if company.startswith("http"):
        product_url = company.rstrip("/")
    else:
        q = company.replace(" ", "+")
        search_url = f"https://www.capterra.com/search?q={q}"
        r = session.get(search_url, timeout=20)
        soup = BeautifulSoup(r.text, "html.parser")
        link = soup.find("a", {"data-qa": "product-name"})
        if link and link.get("href"):
            product_url = "https://www.capterra.com" + link.get("href")
        else:
            # naive fallback
            slug = company.lower().replace(" ", "-")
            product_url = f"https://www.capterra.com/p/{slug}/#reviews"

    page = 1
    while True:
        page_url = product_url + (f"?page={page}" if "?" not in product_url else f"&page={page}")
        print("Fetching", page_url, file=sys.stderr)
        r = session.get(page_url, timeout=20)
        if r.status_code != 200:
            break
        soup = BeautifulSoup(r.text, "html.parser")
        items = soup.select("div.c-review")
        if not items:
            items = soup.select("div.review, li.review")
        if not items:
            break
        added = 0
        for it in items:
            title = it.find(["h3","h4"])
            title_text = title.get_text(strip=True) if title else ""
            body = it.find("p")
            body_text = body.get_text(" ", strip=True) if body else ""
            date_tag = it.find(lambda tag: tag.name=="time" or tag.name=="span")
            date_text = date_tag.get("datetime") if date_tag and date_tag.get("datetime") else (date_tag.get_text(strip=True) if date_tag else "")
            date_obj = parse_date_try(date_text) if date_text else None
            if date_obj and not within_range(date_obj, start, end):
                continue
            rating = it.find(attrs={"class":"rating"})
            rating_text = rating.get_text(strip=True) if rating else ""
            reviewer = it.find(attrs={"class":"reviewer-name"}) or it.find("strong")
            reviewer_text = reviewer.get_text(strip=True) if reviewer else ""
            review = {
                "title": title_text,
                "review": body_text,
                "date": date_obj.isoformat() if date_obj else date_text,
                "rating": rating_text,
                "reviewer": reviewer_text,
                "source": "capterra",
            }
            reviews.append(review)
            added += 1
        if added == 0:
            break
        page += 1
        time.sleep(1.0)
    return reviews

def scrape_trustradius(company: str, start: Optional[datetime], end: Optional[datetime]) -> List[Dict[str,Any]]:
    """
    Basic TrustRadius scraper (bonus source).
    """
    reviews = []
    session = requests.Session()
    session.headers.update(HEADERS)
    if company.startswith("http"):
        product_url = company.rstrip("/")
    else:
        q = company.replace(" ", "+")
        search_url = f"https://www.trustradius.com/search?query={q}"
        r = session.get(search_url, timeout=20)
        soup = BeautifulSoup(r.text, "html.parser")
        link = soup.find("a", {"class":"search-result-link"})
        if link and link.get("href"):
            product_url = "https://www.trustradius.com" + link.get("href")
        else:
            slug = company.lower().replace(" ", "-")
            product_url = f"https://www.trustradius.com/products/{slug}/reviews"

    page = 1
    while True:
        page_url = product_url + (f"/reviews?page={page}" if "/reviews" not in product_url else f"?page={page}")
        print("Fetching", page_url, file=sys.stderr)
        r = session.get(page_url, timeout=20)
        if r.status_code != 200:
            break
        soup = BeautifulSoup(r.text, "html.parser")
        items = soup.select("div.review-card, article.review")
        if not items:
            break
        added = 0
        for it in items:
            title = it.find(["h3","h4"])
            title_text = title.get_text(strip=True) if title else ""
            body = it.find("div", {"class":"review-body"}) or it.find("p")
            body_text = body.get_text(" ", strip=True) if body else ""
            date_tag = it.find("time")
            date_text = date_tag.get("datetime") if date_tag and date_tag.get("datetime") else (date_tag.get_text(strip=True) if date_tag else "")
            date_obj = parse_date_try(date_text) if date_text else None
            if date_obj and not within_range(date_obj, start, end):
                continue
            rating = it.find(attrs={"class":"rating"})
            rating_text = rating.get_text(strip=True) if rating else ""
            reviewer = it.find(attrs={"class":"user-name"}) or it.find("strong")
            reviewer_text = reviewer.get_text(strip=True) if reviewer else ""
            review = {
                "title": title_text,
                "review": body_text,
                "date": date_obj.isoformat() if date_obj else date_text,
                "rating": rating_text,
                "reviewer": reviewer_text,
                "source": "trustradius",
            }
            reviews.append(review)
            added += 1
        if added == 0:
            break
        page += 1
        time.sleep(1.0)
    return reviews

def main():
    parser = argparse.ArgumentParser(description="Scrape SaaS reviews from G2, Capterra, TrustRadius")
    parser.add_argument("--company", required=True, help="Company name or product URL")
    parser.add_argument("--start", required=False, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", required=False, help="End date (YYYY-MM-DD)")
    parser.add_argument("--source", required=False, choices=["g2","capterra","trustradius","all"], default="all")
    parser.add_argument("--output", required=False, default="reviews_output.json")
    args = parser.parse_args()

    start = parse_date_try(args.start) if args.start else None
    end = parse_date_try(args.end) if args.end else None

    all_reviews = []
    sources = ["g2","capterra","trustradius"] if args.source=="all" else [args.source]
    for s in sources:
        try:
            if s=="g2":
                res = scrape_g2(args.company, start, end)
            elif s=="capterra":
                res = scrape_capterra(args.company, start, end)
            elif s=="trustradius":
                res = scrape_trustradius(args.company, start, end)
            else:
                res = []
            print(f"Found {len(res)} reviews from {s}", file=sys.stderr)
            all_reviews.extend(res)
        except Exception as e:
            print(f"Error scraping {s}: {e}", file=sys.stderr)

    # Save output
    with open(args.output, "w", encoding="utf-8") as fh:
        json.dump(all_reviews, fh, indent=2, ensure_ascii=False)
    print(f"Wrote {len(all_reviews)} reviews to {args.output}", file=sys.stderr)

if __name__ == "__main__":
    main()
