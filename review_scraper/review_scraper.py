import asyncio
import csv
import json
import re
from pathlib import Path
from urllib.parse import urljoin

from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

try:
    from crawl4ai import AsyncWebCrawler, CrawlerRunConfig
except Exception:  # pragma: no cover - fallback for older/newer crawl4ai layouts
    AsyncWebCrawler = None
    CrawlerRunConfig = None

try:
    from crawl4ai.async_configs import BrowserConfig
except Exception:  # pragma: no cover - fallback for newer crawl4ai releases
    try:
        from crawl4ai import BrowserConfig
    except Exception:  # pragma: no cover
        BrowserConfig = None


def crawl4ai_available():
    return AsyncWebCrawler is not None and CrawlerRunConfig is not None and BrowserConfig is not None


# ============================================================
# CONFIG
# ============================================================

# PROFILE_DIR = r"F:\review_scrapper\amazon_browser"

# JSON_FILE = r"F:\review_scrapper\amazon_reviews.json"
# CSV_FILE = r"F:\review_scrapper\amazon_reviews.csv"

BASE_DIR = Path(__file__).resolve().parent

PROFILE_DIR = BASE_DIR / "amazon_browser"

JSON_FILE = BASE_DIR / "amazon_reviews.json"

CSV_FILE = BASE_DIR / "amazon_reviews.csv"

MAX_LOAD_CYCLES = 100


# ============================================================
# ASIN
# ============================================================

def extract_asin(url):

    patterns = [
        r"/dp/([A-Z0-9]{10})",
        r"/product-reviews/([A-Z0-9]{10})",
        r"/portal/customer-reviews/([A-Z0-9]{10})",
    ]

    for pattern in patterns:

        match = re.search(pattern, url, re.I)

        if match:
            return match.group(1).upper()

    return None


# ============================================================
# CLEAN TEXT
# ============================================================

def clean_text(value):

    if value is None:
        return ""

    return re.sub(
        r"\s+",
        " ",
        str(value)
    ).strip()


# ============================================================
# REVIEW ID
# ============================================================

async def get_review_id(review):

    value = await review.get_attribute("id")

    if value:

        value = value.strip()

        if value.startswith("customer_review-"):
            return value.replace(
                "customer_review-",
                ""
            )

        if value.startswith("R"):
            return value

    for attr in [
        "data-review-id",
        "data-hook-review-id",
    ]:

        value = await review.get_attribute(attr)

        if value:
            return value.strip()

    links = review.locator("a")

    for i in range(await links.count()):

        try:

            href = await links.nth(i).get_attribute(
                "href"
            )

            if not href:
                continue

            match = re.search(
                r"/(?:gp/customer-reviews|portal/customer-reviews/srp)/([A-Z0-9]+)",
                href,
                re.I
            )

            if match:
                return match.group(1)

        except Exception:
            pass

    return None


# ============================================================
# RATING
# ============================================================

async def get_rating(review):

    selectors = [
        "[data-hook='review-star-rating']",
        "[data-hook='cmps-review-star-rating']",
    ]

    for selector in selectors:

        try:

            loc = review.locator(selector)

            if await loc.count() == 0:
                continue

            text = clean_text(
                await loc.first.inner_text()
            )

            match = re.search(
                r"([1-5](?:\.\d+)?)\s+out of 5",
                text,
                re.I
            )

            if match:
                return float(match.group(1))

            aria = await loc.first.get_attribute(
                "aria-label"
            )

            if aria:

                match = re.search(
                    r"([1-5](?:\.\d+)?)",
                    aria
                )

                if match:
                    return float(match.group(1))

        except Exception:
            pass

    try:

        text = clean_text(
            await review.inner_text()
        )

        match = re.search(
            r"\b([1-5])(?:\.0)?\s+out of 5 stars\b",
            text,
            re.I
        )

        if match:
            return float(match.group(1))

    except Exception:
        pass

    return None


# ============================================================
# EXTRACT ONE REVIEW
# ============================================================

async def extract_review(review, page):

    review_id = await get_review_id(review)

    if not review_id:
        return None

    # --------------------------------------------------------
    # REVIEWER
    # --------------------------------------------------------

    reviewer_name = ""

    for selector in [
        "[data-hook='genome-widget']",
        ".a-profile-name",
        "[data-hook='reviewer-name']",
    ]:

        try:

            loc = review.locator(selector)

            if await loc.count():

                reviewer_name = clean_text(
                    await loc.first.inner_text()
                )

                if reviewer_name:
                    break

        except Exception:
            pass

    # --------------------------------------------------------
    # RATING
    # --------------------------------------------------------

    rating = await get_rating(review)

    # --------------------------------------------------------
    # TITLE
    # --------------------------------------------------------

    review_title = ""

    try:

        loc = review.locator(
            "[data-hook='review-title']"
        )

        if await loc.count():

            review_title = clean_text(
                await loc.first.inner_text()
            )

    except Exception:
        pass

    review_title = re.sub(
        r"^[1-5](?:\.0)?\s+out of 5 stars\s*",
        "",
        review_title,
        flags=re.I
    ).strip()

    # --------------------------------------------------------
    # REVIEW TEXT
    # --------------------------------------------------------

    review_text = ""

    try:

        loc = review.locator(
            "[data-hook='review-body']"
        )

        if await loc.count():

            review_text = clean_text(
                await loc.first.inner_text()
            )

    except Exception:
        pass

    # --------------------------------------------------------
    # DATE
    # --------------------------------------------------------

    review_date = ""

    try:

        loc = review.locator(
            "[data-hook='review-date']"
        )

        if await loc.count():

            review_date = clean_text(
                await loc.first.inner_text()
            )

    except Exception:
        pass

    # --------------------------------------------------------
    # VERIFIED PURCHASE
    # --------------------------------------------------------

    verified_purchase = False

    try:

        verified_purchase = (
            await review.locator(
                "[data-hook='avp-badge']"
            ).count()
            > 0
        )

    except Exception:
        pass

    # --------------------------------------------------------
    # HELPFUL VOTES
    # --------------------------------------------------------

    helpful_votes = 0

    try:

        text = clean_text(
            await review.inner_text()
        )

        match = re.search(
            r"([\d,]+)\s+people found this helpful",
            text,
            re.I
        )

        if match:

            helpful_votes = int(
                match.group(1).replace(",", "")
            )

    except Exception:
        pass

    # --------------------------------------------------------
    # REVIEW URL
    # --------------------------------------------------------

    review_url = ""

    try:

        links = review.locator("a")

        for i in range(await links.count()):

            href = await links.nth(i).get_attribute(
                "href"
            )

            if not href:
                continue

            if (
                "/gp/customer-reviews/"
                in href
                or
                "/portal/customer-reviews/srp/"
                in href
            ):

                review_url = urljoin(
                    page.url,
                    href
                )

                break

    except Exception:
        pass

    return {
        "review_id": review_id,
        "reviewer_name": reviewer_name,
        "rating": rating,
        "review_title": review_title,
        "review_text": review_text,
        "review_date": review_date,
        "verified_purchase": verified_purchase,
        "helpful_votes": helpful_votes,
        "review_url": review_url,
    }


# ============================================================
# EXTRACT REVIEWS FROM PLAYWRIGHT DOM
# ============================================================

async def extract_playwright_reviews(page):

    reviews = page.locator(
        "[data-hook='review']"
    )

    count = await reviews.count()

    result = []

    for i in range(count):

        try:

            review = await extract_review(
                reviews.nth(i),
                page
            )

            if review:
                result.append(review)

        except Exception:
            continue

    return result


# ============================================================
# CRAWL4AI PROCESSING
# ============================================================

async def crawl4ai_process(html, base_url):

    """
    Crawl4AI processes the current Amazon HTML.

    It does NOT navigate Amazon independently.
    Playwright is responsible for Amazon interaction.
    """

    if not crawl4ai_available():
        print("Crawl4AI is not available in this environment. Skipping HTML processing.")
        return html

    try:

        browser_config = BrowserConfig(
            headless=True
        )

        run_config = CrawlerRunConfig(
            word_count_threshold=0
        )

        async with AsyncWebCrawler(
            config=browser_config
        ) as crawler:

            result = await crawler.arun(
                url="raw://" + html,
                config=run_config
            )

            if result.success:

                return result.html or html

    except Exception as e:

        print(
            "Crawl4AI processing warning:",
            str(e)
        )

    return html


# ============================================================
# SHOW MORE
# ============================================================

async def find_show_more(page):

    selectors = [
        "a:has-text('Show 10 more reviews')",
        "a:has-text('Show more reviews')",
        "a[href*='cm_cr_getr_d_paging']",
        "a[href*='cm_cr_arp_d_paging']",
    ]

    for selector in selectors:

        try:

            loc = page.locator(selector)

            for i in range(await loc.count()):

                element = loc.nth(i)

                try:

                    if not await element.is_visible():
                        continue

                    text = clean_text(
                        await element.inner_text()
                    )

                    href = await element.get_attribute(
                        "href"
                    )

                    if (
                        "more review" in text.lower()
                        or (
                            href
                            and "paging" in href.lower()
                        )
                    ):

                        return element

                except Exception:
                    continue

        except Exception:
            continue

    return None


# ============================================================
# SCRAPE ONE FILTER
# ============================================================

async def scrape_filter(
    page,
    crawler,
    url,
    filter_name,
    all_reviews
):

    print()
    print("=" * 70)
    print("FILTER:", filter_name)
    print("=" * 70)

    print("Opening:")
    print(url)

    try:

        await page.goto(
            url,
            wait_until="domcontentloaded",
            timeout=120000
        )

    except PlaywrightTimeoutError:

        print("Page timeout. Continuing...")

    await page.wait_for_timeout(3000)

    # --------------------------------------------------------
    # Amazon reported count
    # --------------------------------------------------------

    reported_count = None

    try:

        text = await page.locator(
            "body"
        ).inner_text()

        match = re.search(
            r"([\d,]+)\s+customer reviews?",
            text,
            re.I
        )

        if match:

            reported_count = int(
                match.group(1).replace(",", "")
            )

            print(
                "Amazon reported reviews:",
                reported_count
            )

    except Exception:
        pass

    # --------------------------------------------------------
    # INITIAL EXTRACTION
    # --------------------------------------------------------

    current = await extract_playwright_reviews(
        page
    )

    before = len(all_reviews)

    for review in current:

        if review["review_id"] not in all_reviews:

            all_reviews[
                review["review_id"]
            ] = review

    print(
        "Reviews on page:",
        len(current)
    )

    print(
        "New unique:",
        len(all_reviews) - before
    )

    print(
        "TOTAL:",
        len(all_reviews)
    )

    # --------------------------------------------------------
    # Crawl4AI processes current page
    # --------------------------------------------------------

    try:

        html = await page.content()

        await crawl4ai_process(
            html,
            page.url
        )

        print(
            "Crawl4AI: current page processed."
        )

    except Exception as e:

        print(
            "Crawl4AI warning:",
            str(e)
        )

    # --------------------------------------------------------
    # LOAD MORE
    # --------------------------------------------------------

    previous_dom = len(current)

    for cycle in range(1, MAX_LOAD_CYCLES + 1):

        print()
        print(
            f"LOAD CYCLE {cycle}"
        )

        current = await extract_playwright_reviews(
            page
        )

        before = len(all_reviews)

        for review in current:

            review_id = review["review_id"]

            if review_id not in all_reviews:

                all_reviews[
                    review_id
                ] = review

        new_unique = (
            len(all_reviews) - before
        )

        print(
            "DOM reviews:",
            len(current)
        )

        print(
            "New unique reviews:",
            new_unique
        )

        print(
            "TOTAL UNIQUE REVIEWS:",
            len(all_reviews)
        )

        # ----------------------------------------------------
        # FIND SHOW MORE
        # ----------------------------------------------------

        show_more = await find_show_more(
            page
        )

        if show_more is None:

            print(
                "No Show More Reviews link found."
            )

            break

        href = await show_more.get_attribute(
            "href"
        )

        print(
            "Show More href:",
            href
        )

        # ----------------------------------------------------
        # CLICK
        # ----------------------------------------------------

        try:

            await show_more.scroll_into_view_if_needed()

            await page.wait_for_timeout(500)

            old_count = len(current)

            await show_more.click(
                timeout=30000
            )

            # Wait for Amazon's new reviews
            await page.wait_for_timeout(2500)

            try:

                await page.wait_for_function(
                    """
                    oldCount => {
                        return document.querySelectorAll(
                            "[data-hook='review']"
                        ).length > oldCount;
                    }
                    """,
                    old_count,
                    timeout=15000
                )

            except Exception:
                pass

        except Exception as e:

            print(
                "Show More click failed:",
                str(e)
            )

            break

        # ----------------------------------------------------
        # CRAWL4AI AFTER EACH LOAD
        # ----------------------------------------------------

        try:

            html = await page.content()

            await crawl4ai_process(
                html,
                page.url
            )

            print(
                "Crawl4AI processed loaded reviews."
            )

        except Exception as e:

            print(
                "Crawl4AI warning:",
                str(e)
            )

        # ----------------------------------------------------
        # CHECK PROGRESS
        # ----------------------------------------------------

        new_dom = await page.locator(
            "[data-hook='review']"
        ).count()

        print(
            "Reviews increased:",
            old_count,
            "->",
            new_dom
        )

        if new_dom <= previous_dom:

            await page.wait_for_timeout(2000)

            retry_dom = await page.locator(
                "[data-hook='review']"
            ).count()

            if retry_dom <= previous_dom:

                print(
                    "Amazon exposed no additional reviews."
                )

                break

            new_dom = retry_dom

        previous_dom = new_dom

    return reported_count


# ============================================================
# SAVE JSON
# ============================================================

def save_json(reviews):

    data = list(reviews.values())

    with open(
        JSON_FILE,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            data,
            f,
            indent=2,
            ensure_ascii=False
        )

    print()
    print(
        "JSON saved:",
        JSON_FILE
    )


# ============================================================
# SAVE CSV
# ============================================================

def save_csv(reviews):

    fields = [
        "review_id",
        "reviewer_name",
        "rating",
        "review_title",
        "review_text",
        "review_date",
        "verified_purchase",
        "helpful_votes",
        "review_url"
    ]

    with open(
        CSV_FILE,
        "w",
        encoding="utf-8-sig",
        newline=""
    ) as f:

        writer = csv.DictWriter(
            f,
            fieldnames=fields
        )

        writer.writeheader()

        for review in reviews.values():

            writer.writerow(review)

    print(
        "CSV saved:",
        CSV_FILE
    )


# ============================================================
# MAIN
# ============================================================

async def main():

    print("=" * 70)
    print("       AMAZON REVIEW SCRAPER")
    print("       PLAYWRIGHT + CRAWL4AI")
    print("=" * 70)

    product_url = input(
        "\nPaste Amazon product URL: "
    ).strip()

    asin = extract_asin(
        product_url
    )

    if not asin:

        print(
            "ERROR: Could not find ASIN."
        )

        return

    print()
    print(
        "ASIN:",
        asin
    )

    base = (
        f"https://www.amazon.in/"
        f"portal/customer-reviews/"
        f"{asin}/"
    )

    # --------------------------------------------------------
    # All legitimate Amazon review views
    # --------------------------------------------------------

    filters = [

        (
            "all",
            base
            + "?reviewerType=all_reviews"
        ),

        (
            "all-recent",
            base
            + "?reviewerType=all_reviews"
            + "&sortBy=recent"
        ),

        (
            "5-star",
            base
            + "?filterByStar=five_star"
            + "&reviewerType=all_reviews"
        ),

        (
            "5-star-recent",
            base
            + "?filterByStar=five_star"
            + "&reviewerType=all_reviews"
            + "&sortBy=recent"
        ),

        (
            "4-star",
            base
            + "?filterByStar=four_star"
            + "&reviewerType=all_reviews"
        ),

        (
            "4-star-recent",
            base
            + "?filterByStar=four_star"
            + "&reviewerType=all_reviews"
            + "&sortBy=recent"
        ),

        (
            "3-star",
            base
            + "?filterByStar=three_star"
            + "&reviewerType=all_reviews"
        ),

        (
            "3-star-recent",
            base
            + "?filterByStar=three_star"
            + "&reviewerType=all_reviews"
            + "&sortBy=recent"
        ),

        (
            "2-star",
            base
            + "?filterByStar=two_star"
            + "&reviewerType=all_reviews"
        ),

        (
            "2-star-recent",
            base
            + "?filterByStar=two_star"
            + "&reviewerType=all_reviews"
            + "&sortBy=recent"
        ),

        (
            "1-star",
            base
            + "?filterByStar=one_star"
            + "&reviewerType=all_reviews"
        ),

        (
            "1-star-recent",
            base
            + "?filterByStar=one_star"
            + "&reviewerType=all_reviews"
            + "&sortBy=recent"
        ),
    ]

    all_reviews = {}

    reported_counts = []

    # --------------------------------------------------------
    # Playwright
    # --------------------------------------------------------

    async with async_playwright() as p:

        print()
        print(
            "Starting persistent browser..."
        )

        browser = await p.chromium.launch_persistent_context(
            PROFILE_DIR,
            headless=False,
            viewport={
                "width": 1440,
                "height": 1000
            }
        )

        page = (
            browser.pages[0]
            if browser.pages
            else await browser.new_page()
        )

        # ----------------------------------------------------
        # Crawl4AI object
        # ----------------------------------------------------

        crawler = None

        if crawl4ai_available():
            crawler = AsyncWebCrawler(
                config=BrowserConfig(
                    headless=True
                )
            )
            await crawler.__aenter__()

        try:

            for filter_name, url in filters:

                try:

                    reported = await scrape_filter(
                        page,
                        crawler,
                        url,
                        filter_name,
                        all_reviews
                    )

                    if reported:
                        reported_counts.append(
                            reported
                        )

                except Exception as e:

                    print()
                    print(
                        "FILTER ERROR:",
                        filter_name
                    )

                    print(
                        str(e)
                    )

                print()
                print(
                    "TOTAL UNIQUE REVIEWS SO FAR:",
                    len(all_reviews)
                )

        finally:

            if crawler is not None:
                await crawler.__aexit__(
                    None,
                    None,
                    None
                )

            await browser.close()

    # ========================================================
    # FINAL
    # ========================================================

    total = len(all_reviews)

    reported = (
        max(reported_counts)
        if reported_counts
        else None
    )

    print()
    print("#" * 70)
    print("FINAL RESULT")
    print("#" * 70)

    print()
    print(
        "Amazon reported reviews:",
        reported if reported else "Unknown"
    )

    print(
        "Unique reviews collected:",
        total
    )

    if reported:

        missing = max(
            reported - total,
            0
        )

        print(
            "Not exposed to this session:",
            missing
        )

    # --------------------------------------------------------
    # Rating breakdown
    # --------------------------------------------------------

    breakdown = {
        "5": 0,
        "4": 0,
        "3": 0,
        "2": 0,
        "1": 0,
        "Unknown": 0
    }

    for review in all_reviews.values():

        rating = review.get(
            "rating"
        )

        if rating is None:

            breakdown["Unknown"] += 1

        else:

            key = str(
                int(float(rating))
            )

            if key in breakdown:
                breakdown[key] += 1
            else:
                breakdown["Unknown"] += 1

    print()
    print("RATING BREAKDOWN")

    for rating, count in breakdown.items():

        print(
            f"{rating}-star:",
            count
        )

    # --------------------------------------------------------
    # SAVE
    # --------------------------------------------------------

    save_json(
        all_reviews
    )

    save_csv(
        all_reviews
    )

    print()
    print("=" * 70)
    print("COMPLETED")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())