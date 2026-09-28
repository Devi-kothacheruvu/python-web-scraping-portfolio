import asyncio
import json
import pandas as pd
from playwright.async_api import async_playwright


BASE_URL = "https://books.toscrape.com/catalogue/page-{}.html"


async def scrape_books():
    all_books = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        page_number = 1

        while True:
            url = BASE_URL.format(page_number)

            print(f"Scraping page {page_number}...")

            response = await page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=60000
            )

            if response is None or response.status >= 400:
                print("No more pages found.")
                break

            books = await page.locator("article.product_pod").all()

            if not books:
                print("No books found. Stopping.")
                break

            for book in books:
                title = await book.locator("h3 a").get_attribute("title")

                price = await book.locator(".price_color").inner_text()

                rating = await book.locator("p.star-rating").get_attribute("class")

                availability = await book.locator(
                    ".availability"
                ).inner_text()

                product_url = await book.locator(
                    "h3 a"
                ).get_attribute("href")

                all_books.append({
                    "title": title.strip() if title else "",
                    "price": price.strip(),
                    "rating": rating.replace(
                        "star-rating", ""
                    ).strip() if rating else "",
                    "availability": availability.strip(),
                    "product_url": product_url
                })

            next_button = page.locator(
                "li.next a"
            )

            if await next_button.count() == 0:
                print("Reached the last page.")
                break

            page_number += 1

        await browser.close()

    return all_books


async def main():
    books = await scrape_books()

    print(f"\nTotal books scraped: {len(books)}")

    # Save JSON
    with open(
        "books.json",
        "w",
        encoding="utf-8"
    ) as file:
        json.dump(
            books,
            file,
            indent=4,
            ensure_ascii=False
        )

    # Save CSV
    df = pd.DataFrame(books)

    df.to_csv(
        "books.csv",
        index=False,
        encoding="utf-8-sig"
    )

    # Save Excel
    df.to_excel(
        "books.xlsx",
        index=False
    )

    print("\nFiles created successfully:")
    print("books.json")
    print("books.csv")
    print("books.xlsx")


if __name__ == "__main__":
    asyncio.run(main())