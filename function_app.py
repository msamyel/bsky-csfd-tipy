import azure.functions as func
import os
import random
import json
import requests
import bs4
from datetime import datetime, timezone

def get_random_id() -> int:
    ranges = os.getenv('MOVIE_ID_RANGES').split(',')
    range_ints = []
    total_id_count = 0
    for range in ranges:
        split_range = range.split('-')
        start = int(split_range[0])
        end = int(split_range[1])
        range_ints.append((start, end))
        total_id_count += end - start + 1
    
    random_id_index = random.randint(0, total_id_count)
    for start, end in range_ints:
        if random_id_index <= end - start:
            return start + random_id_index
        else:
            random_id_index -= end - start + 1

def fix_poster_url(poster_url: str) -> str:
    if poster_url.startswith('//'):
        return f"https:{poster_url}"
    return poster_url

def get_movie_summary_url(random_id: int) -> str:
    return os.getenv('SUMMARY_PAGE_URL_PATTERN').format(movie_id=random_id)

def get_movie_posters_url(random_id: int) -> str:
    return os.getenv('POSTERS_PAGE_URL_PATTERN').format(movie_id=random_id)

def get_page_soup(url: str) -> bs4.BeautifulSoup:
    headers = {'User-Agent': os.getenv('HEADERS_USER_AGENT')}
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    return bs4.BeautifulSoup(response.text, 'html.parser')

def download_image(url: str) -> bytes:
    headers = {'User-Agent': os.getenv('HEADERS_USER_AGENT')}
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    return response.content

def get_movie_title(summary_page_soup: bs4.BeautifulSoup) -> str:
    title_element_id = os.getenv('TITLE_ELEMENT_ID')
    title_element = summary_page_soup.select_one(title_element_id)
    return title_element.text if title_element else None

def get_summary_text(summary_page_soup: bs4.BeautifulSoup) -> str:
    summary_element_id = os.getenv('SUMMARY_ELEMENT_ID')
    description_element = summary_page_soup.select_one(summary_element_id)
    return description_element.text if description_element else None

def get_poster_url(posters_page_soup: bs4.BeautifulSoup) -> str:
    poster_element_id = os.getenv('POSTER_ELEMENT_ID')
    poster_element = posters_page_soup.select_one(poster_element_id)
    return poster_element['src'] if poster_element else None

def scrape_movie_details() -> tuple[bool, str, str, str, str]: # (success, title, summary, movie_url, poster_url)
    random_id = get_random_id()
    summary_url = get_movie_summary_url(random_id)
    posters_url = get_movie_posters_url(random_id)
    summary_page_soup = get_page_soup(summary_url)
    title = get_movie_title(summary_page_soup)
    if not title:
        return False, None, None, None, None
    
    summary = get_summary_text(summary_page_soup)
    if not summary:
        return False, title, None, summary_url, None

    posters_page_soup = get_page_soup(posters_url)
    poster_url = get_poster_url(posters_page_soup)
    if not poster_url:
        return False, title, summary, summary_url, None

    return True, title, summary, summary_url, poster_url

def login_to_bluesky():

    BLUESKY_HANDLE = os.getenv("BLUESKY_HANDLE")
    BLUESKY_APP_PASSWORD = os.getenv("BLUESKY_APP_PASSWORD")

    print(f"Logging in as {BLUESKY_HANDLE}...")

    resp = requests.post(
        "https://bsky.social/xrpc/com.atproto.server.createSession",
        json={"identifier": BLUESKY_HANDLE, "password": BLUESKY_APP_PASSWORD},
    )
    resp.raise_for_status()
    session = resp.json()
    print(session["accessJwt"])
    return session


def post_with_image(session, title, summary, movie_url, blob):
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    title_bytes = title.encode("UTF-8")
    title_bytes_len = len(title_bytes)

    MAX_POST_LENGTH = 300
    # subtract title length and 3 for " - " separator
    remaining_characters = MAX_POST_LENGTH - len(title) - 3
    # If the post is too long, truncate it
    if len(summary) > remaining_characters:
        summary = summary[:remaining_characters - 3] + "..."

    content = f"{title} - {summary}"

    # Required fields that each post must include
    post = {"$type": "app.bsky.feed.post",
            "text": content,
            "createdAt": now,
            "langs": ["cs", "sk"],
            "facets": [
            {
                "index": {
                    "byteStart": 0,
                    "byteEnd": title_bytes_len,
                },
                "features": [
                    {
                        "$type": "app.bsky.richtext.facet#link",
                        "uri": movie_url
                    }
                ]
            }
            ],
            "embed": {
                "$type": "app.bsky.embed.images",
                "images": [{
                    "alt": title,
                    "image": blob,
                }],
            }
        }

    resp = requests.post(
        "https://bsky.social/xrpc/com.atproto.repo.createRecord",
        headers={"Authorization": "Bearer " + session["accessJwt"]},
        json={
            "repo": session["did"],
            "collection": "app.bsky.feed.post",
            "record": post,
        },
    )
    print(json.dumps(resp.json(), indent=2))
    resp.raise_for_status()


def upload_image_data(session, img_bytes):
    IMAGE_MIMETYPE = "image/jpg"

    # this size limit is specified in the app.bsky.embed.images lexicon
    if len(img_bytes) > 1000000:
        raise Exception(
            f"image file size too large. 1000000 bytes maximum, got: {len(img_bytes)}"
        )

    resp = requests.post(
        "https://bsky.social/xrpc/com.atproto.repo.uploadBlob",
        headers={
            "Content-Type": IMAGE_MIMETYPE,
            "Authorization": "Bearer " + session["accessJwt"],
        },
        data=img_bytes,
    )
    resp.raise_for_status()
    blob = resp.json()["blob"]
    return blob

def try_get_movie_details() -> tuple[bool, str, str, str, str]: # (success, title, summary, movie_url, poster_url)
    MAX_TRY_COUNT = int(os.getenv('MAX_TRY_COUNT'))
    try_count = 0
    while try_count < MAX_TRY_COUNT:
        try_count += 1
        try:
            success, title, summary, summary_url, poster_url = scrape_movie_details()
            if success:
                # title and summary must be trimmed to avoid leading/trailing whitespaces
                # poster_url must be prefixed with "https:" to form a valid URL
                return True, title.strip(), summary.strip(), summary_url, fix_poster_url(poster_url)
        except Exception as e:
            print(e)
    return False, None, None, None, None

def post_movie_to_bluesky(title, summary, movie_url, img_bytes):
    session = login_to_bluesky()
    blob = upload_image_data(session, img_bytes)
    post_with_image(session, title, summary, movie_url, blob)

def main():
    success, title, summary, movie_url, poster_url = try_get_movie_details()
    if not success:
        return
    
    img_bytes = download_image(poster_url)
    post_movie_to_bluesky(title, summary, movie_url, img_bytes)

app = func.FunctionApp()

@app.schedule(schedule="0 0 16 * * *", arg_name="myTimer", run_on_startup=False,
              use_monitor=False) 
def timer_trigger(myTimer: func.TimerRequest) -> None:
    main()