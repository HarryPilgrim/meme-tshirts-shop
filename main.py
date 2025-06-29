import requests
from printify import PrintifyUploader
#from printify_catalog_dumper import PrintifyCatalogDumper
#from printify_catalog_explorer import PrintifyCatalogExplorer
from reddit_downloads import RedditContent
from social_media_poster import SocialMediaPoster
from dotenv import load_dotenv
load_dotenv()
import time
import os

ACCESS_TOKEN = os.getenv("ACCESS_TOKEN")
SHOP_ID = os.getenv("SHOP_ID")       # from Printify
SHOPIFY_ID = os.getenv("SHOPIFY_ID")
REDDIT_CLIENT_ID = os.getenv("REDDIT_CLIENT_ID")
REDDIT_CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET")
REDDIT_USER_AGENT = os.getenv("REDDIT_USER_AGENT")
shopify_access_token = os.getenv("shopify_access_token")
SHOPIFY_DOMAIN = os.getenv("SHOPIFY_DOMAIN")
headers = {
    "Authorization": f"Bearer {ACCESS_TOKEN}",
    "Content-Type": "application/json"
}

# res = requests.get("https://api.printify.com/v1/shops.json", headers=headers)
# print(res.status_code, res.json())

# explorer = PrintifyCatalogExplorer(ACCESS_TOKEN)
# explorer.fetch_all_data("printify_catalog_output.csv")

# dumper = PrintifyCatalogDumper(ACCESS_TOKEN)
# dumper.run()
# print("✅ JSON dumps available in", dumper.output_dir)


subreddits = [
    'dankmemes', 'HistoryMemes', 'PoliticalMemes',
    'TrumpMemes', 'Memes_Of_The_Dank', 'PoliticalCompassMemes'
]

if __name__ == "__main__":
    print("Starting Reddit scraping...")
    scraper = RedditContent(subreddits, CLIENT_ID=REDDIT_CLIENT_ID, CLIENT_SECRET=REDDIT_CLIENT_SECRET, USER_AGENT=REDDIT_USER_AGENT)
    scraper.download_posts(limit=15, sort='hot')
    print("Reddit download complete.\n")
    time.sleep(2)

    print("Starting Printify upload...")
    print("Loaded SHOPIFY_DOMAIN:", SHOPIFY_DOMAIN)
    uploader = PrintifyUploader(ACCESS_TOKEN, SHOPIFY_ID, shopify_domain=SHOPIFY_DOMAIN, shopify_access_token=shopify_access_token)
    uploader.process_jsonl(
        in_path="reddit_images.jsonl",
        out_path="printify_upload.jsonl"
    )
    print("Printify upload complete.\n")
    time.sleep(2)

    print("Starting social media posting...")
    poster = SocialMediaPoster()
    poster.run()
    print("Social media posting complete.")

# scraper = RedditContent(subreddits, CLIENT_ID=REDDIT_CLIENT_ID, CLIENT_SECRET=REDDIT_CLIENT_SECRET, USER_AGENT=REDDIT_USER_AGENT)
# scraper.download_posts(limit=5, sort='hot')
# print('Download complete.')




# uploader = PrintifyUploader(ACCESS_TOKEN, SHOPIFY_ID, shopify_domain="tshirtmemes.org/", shopify_access_token=shopify_access_token)
# uploader.process_jsonl(
#     in_path="reddit_images.jsonl",         # your input JSONL
#     out_path="printify_upload.jsonl"       # where to write updated records
# )


# poster = SocialMediaPoster()
# poster.run()