import os
import json
import base64
import requests
import tweepy
from blueskysocial import Client, Post, Image
#import Image
import time
import praw

# Load environment variables if needed
from dotenv import load_dotenv
load_dotenv()

# Twitter credentials (v1 and v2)
TW_OAUTH_KEY = os.getenv("TW_OAUTH_KEY")
TW_OAUTH_SECRET = os.getenv("TW_OAUTH_SECRET")
TW_ACCESS_TOKEN = os.getenv("TW_ACCESS_TOKEN")
TW_ACCESS_SECRET = os.getenv("TW_ACCESS_SECRET")
TW_BEARER_TOKEN = os.getenv("TW_BEARER_TOKEN")

#Reddit credentials
REDDIT_CLIENT_ID = os.getenv("REDDIT_CLIENT_ID")
REDDIT_CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET")
REDDIT_USER_AGENT = os.getenv("REDDIT_USER_AGENT")
REDDIT_USERNAME = os.getenv("REDDIT_USERNAME")
REDDIT_PASSWORD = os.getenv("REDDIT_PASSWORD")

# Bluesky credentials
BLUESKY_HANDLE = os.getenv("BLUESKY_HANDLE")
BLUESKY_APP_PASSWORD = os.getenv("BLUESKY_APP_PASSWORD")

class SocialMediaPoster:
    def __init__(self, jsonl_path='meme-tshirts-shop/printify_upload.jsonl'):
        self.jsonl_path = jsonl_path

        auth = tweepy.OAuth1UserHandler(
            TW_OAUTH_KEY, TW_OAUTH_SECRET,
            TW_ACCESS_TOKEN, TW_ACCESS_SECRET
        )
        self.tw_api_v1 = tweepy.API(auth)

        self.tw_client_v2 = tweepy.Client(
            bearer_token=TW_BEARER_TOKEN,
            consumer_key=TW_OAUTH_KEY,
            consumer_secret=TW_OAUTH_SECRET,
            access_token=TW_ACCESS_TOKEN,
            access_token_secret=TW_ACCESS_SECRET
        )

        self.bsky = Client()
        self.bsky.authenticate(BLUESKY_HANDLE, BLUESKY_APP_PASSWORD)

    def load_records(self):
        records = []
        with open(self.jsonl_path, encoding='utf-8') as fp:
            for line in fp:
                if line.strip():
                    records.append(json.loads(line))
        return records

    def save_records(self, records, out_path=None):
        path = out_path or self.jsonl_path
        with open(path, 'w', encoding='utf-8') as fp:
            for rec in records:
                fp.write(json.dumps(rec, ensure_ascii=False) + '\n')

    def try_with_retries(self, func, args=(), retries=3, delay=2, id=None, platform=None):
        for attempt in range(retries):
            try:
                return func(*args)
            except Exception as e:
                error_msg = str(e)
                print(f"{platform} attempt {attempt + 1} for {id} failed: {e}")

                # Check for specific conditions to skip retries
                if platform == "Bluesky":
                    if "image file size too large" in error_msg:
                        print(f"Skipping {platform} for {id} - image too large")
                        return None
                    elif "Maximum of 300 characters allowed" in error_msg:
                        print(f"Skipping {platform} for {id} - text too long")
                        return None
                elif platform == "Twitter":
                    if "No such file or directory" in error_msg:
                        print(f"Skipping {platform} for {id} - file not found")
                        return None

                time.sleep(delay * (2 ** attempt))  # Exponential backoff

        print(f"{platform} failed for {id} after {retries} retries.")
        return None

    # def try_with_retries(self, func, args=(), retries=3, delay=2, id=None, platform=None):
    #     for attempt in range(retries):
    #         try:
    #             return func(*args)
    #         except Exception as e:
    #             print(f"{platform} attempt {attempt+1} for {id} failed: {e}")
    #             time.sleep(delay * (2 ** attempt))  # Exponential backoff
    #     print(f"{platform} failed for {id} after {retries} retries. Deleting image.")
    #     try:
    #         os.remove(args[0]['local_path'])
    #         print(f"🗑️ Deleted {args[0]['local_path']}")
    #     except Exception as e:
    #         print(f"Image deletion error for {id}: {e}")
    #     return None

    def post_to_twitter(self, rec):
        media = self.tw_api_v1.media_upload(rec['local_path'])
        text = f"{rec['title']}\nBuy now: {rec['shopify_url']}"
        tweet = self.tw_client_v2.create_tweet(text=text, media_ids=[media.media_id_string], user_auth=True)
        return f"https://twitter.com/i/web/status/{tweet.data['id']}"

    def post_to_bluesky(self, rec):
        # Check file size first (1MB = 1000000 bytes)
        if os.path.getsize(rec['local_path']) > 1000000:
            raise Exception("image file size too large")

        # Truncate title for Bluesky's 300 character limit
        base_text = f"{rec['title']}\nBuy here: {rec['shopify_url']}"
        if len(base_text) > 300:
            # Calculate how much space we need for the URL part
            url_part = f"\nBuy here: {rec['shopify_url']}"
            available_for_title = 300 - len(url_part)
            truncated_title = rec['title'][:available_for_title - 3] + "..."
            base_text = f"{truncated_title}\nBuy here: {rec['shopify_url']}"

        with open(rec['local_path'], 'rb') as f:
            img = Image(f, alt_text=rec['title'])
            post = Post(base_text, with_attachments=[img])
            result = self.bsky.post(post)
        return f"https://bsky.app/profile/{BLUESKY_HANDLE}/post/{result['uri'].split('/')[-1]}"

    # def post_to_bluesky(self, rec):
    #     with open(rec['local_path'], 'rb') as f:
    #         img = Image(f, alt_text=rec['title'])
    #         post = Post(f"{rec['title']}\nBuy here: {rec['shopify_url']}", with_attachments=[img])
    #         result = self.bsky.post(post)
    #     return f"https://bsky.app/profile/{BLUESKY_HANDLE}/post/{result['uri'].split('/')[-1]}"

    def post_to_reddit(self, rec):
        reddit = praw.Reddit(
            client_id=REDDIT_CLIENT_ID,
            client_secret=REDDIT_CLIENT_SECRET,
            user_agent=REDDIT_USER_AGENT,
            username=REDDIT_USERNAME,
            password=REDDIT_PASSWORD
        )

        subreddit = reddit.subreddit("MemesOnTShirts")

        # Try clickable title (some Markdown formatting may work only in comments)

        title = f"{rec['title']}"

        try:
            submission = subreddit.submit_image(title=title, image_path=rec['local_path'])
            print(f"Posted image to Reddit: {submission.url}")

            # Add comment with link to buy
            comment_text = f"[Buy this shirt here]({rec['shopify_url']})"
            submission.reply(comment_text)
            print(f"Commented with Shopify link: {rec['shopify_url']}")
            return submission.url
        except Exception as e:
            print(f"Reddit post failed for {rec['id']}: {e}")
            return None


    def run(self):
        records = self.load_records()
        updated = False
        for rec in records:
            if not rec.get('printify_product_id'):
                continue

            if not rec.get('bluesky_url'):
                url = self.try_with_retries(self.post_to_bluesky, args=(rec,), id=rec['id'], platform="Bluesky")
                if url:
                    rec['bluesky_url'] = url
                    print(f"Bluesky {rec['id']} → {url}")
                    updated = True

            if not rec.get('twitter_url'):
                url = self.try_with_retries(self.post_to_twitter, args=(rec,), id=rec['id'], platform="Twitter")
                if url:
                    rec['twitter_url'] = url
                    print(f"Tweeted {rec['id']} → {url}")
                    updated = True

            # Only delete after both platforms have been attempted
            if (rec.get('twitter_url') or rec.get('bluesky_url')) and os.path.exists(rec['local_path']):
                try:
                    os.remove(rec['local_path'])
                    print(f"🗑️ Deleted {rec['local_path']}")
                except Exception as e:
                    print(f"Image deletion error for {rec['id']}: {e}")

        if updated:
            self.save_records(records)
            print("✅ All new posts processed and JSONL updated.")
        # At the very end of your run() function
        with open('meme-tshirts-shop/reddit_images.jsonl', 'w', encoding='utf-8') as fp:
            pass  # This clears the file
        print("✅ All done. JSONL file emptied.")

    #
    # def run(self):
    #     records = self.load_records()
    #     updated = False
    #     for rec in records:
    #         if not rec.get('printify_product_id'):
    #             continue
    #
    #         if not rec.get('bluesky_url'):
    #             url = self.try_with_retries(self.post_to_bluesky, args=(rec,), id=rec['id'], platform="Bluesky")
    #             if url:
    #                 rec['bluesky_url'] = url
    #                 print(f"Bluesky {rec['id']} → {url}")
    #                 updated = True
    #
    #         if not rec.get('twitter_url'):
    #             url = self.try_with_retries(self.post_to_twitter, args=(rec,), id=rec['id'], platform="Twitter")
    #             if url:
    #                 rec['twitter_url'] = url
    #                 print(f"Tweeted {rec['id']} → {url}")
    #                 updated = True
    #
    #
    #
    #
    #         if rec.get('twitter_url') and rec.get('bluesky_url'):
    #             try:
    #                 os.remove(rec['local_path'])
    #                 print(f"🗑️ Deleted {rec['local_path']}")
    #             except Exception as e:
    #                 print(f"Image deletion error for {rec['id']}: {e}")
    #
    #     if updated:
    #         self.save_records(records)
    #         print("✅ All new posts processed and JSONL updated.")
    #     # At the very end of your run() function
    #     with open('meme-tshirts-shop/reddit_images.jsonl', 'w', encoding='utf-8') as fp:
    #         pass  # This clears the file
    #     print("✅ All done. JSONL file emptied.")

# class SocialMediaPoster:
#     def __init__(self, jsonl_path='printify_upload.jsonl'):
#         self.jsonl_path = jsonl_path
#         # initialize twitter v1 API
#         auth = tweepy.OAuth1UserHandler(
#             TW_OAUTH_KEY, TW_OAUTH_SECRET,
#             TW_ACCESS_TOKEN, TW_ACCESS_SECRET
#         )
#         self.tw_api_v1 = tweepy.API(auth)
#         # twitter v2 client
#         self.tw_client_v2 = tweepy.Client(
#             bearer_token=TW_BEARER_TOKEN,
#             consumer_key=TW_OAUTH_KEY,
#             consumer_secret=TW_OAUTH_SECRET,
#             access_token=TW_ACCESS_TOKEN,
#             access_token_secret=TW_ACCESS_SECRET
#         )
#         # bluesky client
#         self.bsky = Client()
#         self.bsky.authenticate(BLUESKY_HANDLE, BLUESKY_APP_PASSWORD)
#
#     def load_records(self):
#         records = []
#         with open(self.jsonl_path, encoding='utf-8') as fp:
#             for line in fp:
#                 if line.strip():
#                     records.append(json.loads(line))
#         return records
#
#     def save_records(self, records, out_path=None):
#         path = out_path or self.jsonl_path
#         with open(path, 'w', encoding='utf-8') as fp:
#             for rec in records:
#                 fp.write(json.dumps(rec, ensure_ascii=False) + '\n')
#
#     def post_to_twitter(self, rec):
#         # upload image
#         media = self.tw_api_v1.media_upload(rec['local_path'])
#         # compose tweet text
#         text = f"{rec['title']}\nBuy now: {rec['shopify_url']}"
#         # post tweet
#         tweet = self.tw_client_v2.create_tweet(text=text, media_ids=[media.media_id_string], user_auth=True)
#         # build url
#         tw_url = f"https://twitter.com/i/web/status/{tweet.data['id']}"
#         return tw_url
#
#
#     def post_to_bluesky(self, rec):
#         with open(rec['local_path'], 'rb') as f:
#             img = Image(f, alt_text=rec['title'])  # pass file object directly
#             post = Post(f"{rec['title']}\nBuy here: {rec['shopify_url']}", with_attachments=[img])
#             result = self.bsky.post(post)
#
#         bl_url = f"https://bsky.app/profile/{BLUESKY_HANDLE}/post/{result['uri'].split('/')[-1]}"
#         return bl_url
#
#     def run(self):
#         records = self.load_records()
#         updated = False
#         for rec in records:
#             if not rec.get('printify_product_id'):
#                 continue
#             # post to twitter if not yet
#             if not rec.get('twitter_url'):
#                 try:
#                     rec['twitter_url'] = self.post_to_twitter(rec)
#                     print(f"Tweeted {rec['id']} → {rec['twitter_url']}")
#                     updated = True
#                 except Exception as e:
#                     print(f"Twitter error for {rec['id']}: {e}")
#             # post to bluesky if not yet
#             if not rec.get('bluesky_url'):
#                 try:
#                     rec['bluesky_url'] = self.post_to_bluesky(rec)
#                     print(f"Bluesky {rec['id']} → {rec['bluesky_url']}")
#                     updated = True
#                 except Exception as e:
#                     print(f"Bluesky error for {rec['id']}: {e}")
#
#             # Delete image if both posts succeeded
#             if rec.get('twitter_url') and rec.get('bluesky_url'):
#                 try:
#                     os.remove(rec['local_path'])
#                     print(f"🗑️ Deleted {rec['local_path']}")
#                 except Exception as e:
#                     print(f"Image deletion error for {rec['id']}: {e}")
#         if updated:
#             self.save_records(records)
#             print("✅ All new posts processed and JSONL updated.")

# if __name__ == '__main__':
#     poster = SocialMediaPoster()
#     poster.run()
