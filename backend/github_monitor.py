import requests
import logging
from datetime import datetime, date
from typing import Optional

logger = logging.getLogger(__name__)


def get_latest_commit_date(username: str) -> Optional[date]:
    """
    Calls GitHub public API to get the latest commit date for a user.

    Args:
        username (str): GitHub username

    Returns:
        date | None: Date of the most recent push, or None if not found or rate limited

    Endpoint:
        GET https://api.github.com/users/{username}/events/public

    Filters for PushEvent types and returns the date of the most recent push.
    No auth needed for public repos, but rate limited to 60 requests/hour.

    Handles rate limits gracefully — if API returns 403 or 429, returns None and logs it.
    """
    url = f"https://api.github.com/users/{username}/events/public"

    try:
        response = requests.get(url, timeout=10)

        if response.status_code in [403, 429]:
            logger.warning(f"GitHub API rate limit hit (status {response.status_code})")
            return None

        if response.status_code != 200:
            logger.error(f"GitHub API returned status {response.status_code}")
            return None

        events = response.json()

        if not events:
            logger.info(f"No public events found for user {username}")
            return None

        # Filter for PushEvent (commits/pushes)
        for event in events:
            if event.get('type') == 'PushEvent':
                created_at = event.get('created_at')
                if created_at:
                    commit_date = datetime.fromisoformat(created_at.replace('Z', '+00:00')).date()
                    return commit_date

        logger.info(f"No PushEvent found for user {username}")
        return None

    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching GitHub events: {e}")
        return None
    except (ValueError, KeyError) as e:
        logger.error(f"Error parsing GitHub response: {e}")
        return None