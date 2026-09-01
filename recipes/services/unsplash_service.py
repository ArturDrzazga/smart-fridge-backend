"""
Fetches a representative stock photo for a recipe from the Unsplash API,
searching by the recipe's title.

Unsplash's API Terms require: (1) hotlinking the returned image URL
directly rather than downloading/re-hosting it, (2) displaying visible
attribution (photographer name + Unsplash, both linked) wherever the
photo is shown, and (3) pinging the `download_location` endpoint once
per "download" event (i.e. once the photo is actually shown to a user).
This module returns everything the frontend needs to satisfy (1) and
(2); triggering (3) is the frontend's responsibility at display time,
since that's when a photo is actually "used".
"""

import logging
import os

import requests

logger = logging.getLogger("django")

UNSPLASH_SEARCH_URL = "https://api.unsplash.com/search/photos"
REQUEST_TIMEOUT_SECONDS = 4


def get_recipe_image(title):
    """
    Searches Unsplash for a photo matching the recipe title and returns
    a dict with the image URL and required attribution data, or None if
    no photo was found or the request failed/timed out.

    Failures are deliberately swallowed (logged, not raised): a missing
    recipe image should never block recipe generation.
    """
    access_key = os.getenv("UNSPLASH_ACCESS_KEY")
    if not access_key:
        logger.warning("UNSPLASH_ACCESS_KEY is not set; skipping recipe image fetch")
        return None

    try:
        response = requests.get(
            UNSPLASH_SEARCH_URL,
            params={"query": title, "per_page": 1, "orientation": "landscape"},
            headers={"Authorization": f"Client-ID {access_key}"},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        results = response.json().get("results", [])
    except requests.RequestException as exc:
        logger.warning(f"Unsplash request failed for '{title}': {str(exc)}")
        return None

    if not results:
        return None

    photo = results[0]
    photographer = photo.get("user", {})

    return {
        "url": photo.get("urls", {}).get("regular"),
        "unsplash_url": photo.get("links", {}).get("html"),
        "download_location": photo.get("links", {}).get("download_location"),
        "photographer_name": photographer.get("name"),
        "photographer_url": photographer.get("links", {}).get("html"),
    }