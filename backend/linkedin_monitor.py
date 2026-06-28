import logging
from datetime import datetime, date
from typing import Optional

logger = logging.getLogger(__name__)


def get_latest_post_date(linkedin_url: str, apify_token: str) -> Optional[date]:
    """
    Uses Apify client to run the LinkedIn profile scraper and extract the date
    of the most recent post.

    Args:
        linkedin_url (str): The LinkedIn profile URL to scrape
        apify_token (str): Apify API token

    Returns:
        date | None: Date of the most recent post, or None if no posts found or scrape fails

    Uses the `apify-client` Python package. Handles failures silently —
    returns None, does not crash the scheduler.
    """
    try:
        from apify_client import ApifyClient

        client = ApifyClient(apify_token)

        # Run the LinkedIn profile scraper actor
        run_input = {
            "url": linkedin_url,
            "includePosts": True,
            "maxPosts": 10  # Only need recent posts
        }

        # Start the actor run
        actor_run = client.actor("apify/linkedin-profile-scraper").call(run_input=run_input)

        # Wait for completion
        finished_run = client.wait_for_finish(actor_run)

        if not finished_run:
            logger.error("LinkedIn scraper did not finish")
            return None

        # Get the results
        dataset_id = finished_run.get('defaultDatasetId')
        if not dataset_id:
            logger.error("No dataset ID in scraper response")
            return None

        # Fetch items from dataset
        dataset = client.dataset(dataset_id)
        items = dataset.list_items()

        if not items or len(items) == 0:
            logger.info(f"No posts found for {linkedin_url}")
            return None

        # Extract post dates and find the most recent
        latest_post_date = None
        for item in items:
            posts = item.get('posts', [])
            if posts:
                for post in posts:
                    post_date_str = post.get('date') or post.get('postedAt')
                    if post_date_str:
                        try:
                            post_date = parse_linkedin_date(post_date_str)
                            if post_date:
                                if latest_post_date is None or post_date > latest_post_date:
                                    latest_post_date = post_date
                        except (ValueError, TypeError) as e:
                            logger.warning(f"Error parsing post date: {e}")
                            continue

        return latest_post_date

    except ImportError:
        logger.error("apify-client not installed. Install with: pip install apify-client")
        return None
    except Exception as e:
        logger.error(f"Error scraping LinkedIn profile: {e}")
        return None


def parse_linkedin_date(date_str: str) -> Optional[date]:
    """
    Parse date string from LinkedIn scraper.

    Handles formats like:
    - ISO format: 2024-01-15T10:30:00Z
    - Relative: "2 days ago", "1 week ago"
    - Standard: "Jan 15, 2024"

    Returns:
        date | None: Parsed date or None if parsing fails
    """
    if not date_str:
        return None

    # Try ISO format first
    try:
        if 'T' in date_str:
            return datetime.fromisoformat(date_str.replace('Z', '+00:00')).date()
    except ValueError:
        pass

    # Try standard datetime formats
    formats = [
        '%Y-%m-%d',
        '%b %d, %Y',
        '%B %d, %Y',
        '%d %b %Y',
        '%d %B %Y',
    ]

    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt).date()
        except ValueError:
            continue

    # Try relative dates like "2 days ago"
    import re
    relative_match = re.search(r'(\d+)\s*(day|days|week|weeks|month|months)\s*ago', date_str, re.IGNORECASE)
    if relative_match:
        from datetime import timedelta
        value = int(relative_match.group(1))
        unit = relative_match.group(2).lower()

        if 'week' in unit:
            days = value * 7
        elif 'month' in unit:
            days = value * 30  # Approximate
        else:
            days = value

        return (datetime.now() - timedelta(days=days)).date()

    return None