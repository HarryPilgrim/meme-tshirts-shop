import json
import os
import requests
import praw
import csv
from urllib.parse import urlparse
from dotenv import load_dotenv
load_dotenv()

# Ensure directory exists
import os


def ensure_dir(path):
    """
    Create parent directories for the given file path if they don't exist.
    """
    parent = os.path.dirname(path)
    if parent and not os.path.exists(parent):
        os.makedirs(parent, exist_ok=True)


class RedditContent:
    def __init__(self, subreddits, CLIENT_ID, CLIENT_SECRET, USER_AGENT, output_dir='reddit_photos',
                 csv_path='reddit_images.csv'):
        load_dotenv()
        self.CLIENT_ID = CLIENT_ID
        self.CLIENT_SECRET = CLIENT_SECRET
        self.USER_AGENT = USER_AGENT

        if not all([self.CLIENT_ID, self.CLIENT_SECRET, self.USER_AGENT]):
            raise ValueError('Missing one or more Reddit API credentials.')

        self.reddit = praw.Reddit(
            client_id=self.CLIENT_ID,
            client_secret=self.CLIENT_SECRET,
            user_agent=self.USER_AGENT
        )

        self.subreddits = subreddits
        # strip whitespace/newlines and trailing slash
        self.output_dir = output_dir.strip().rstrip('/')
        self.csv_path = csv_path
        # Initialize a simple counter for CSV 'id' column
        self._next_id = 1

    def download_posts(self, limit=10, sort='hot'):
        out_path = self.csv_path.replace('.csv', '.jsonl')
        downloaded = 0

        with open(out_path, 'a', encoding='utf-8') as fp:
            for name in self.subreddits:
                subreddit = self.reddit.subreddit(name)
                posts = getattr(subreddit, sort)(limit=limit * 3)

                for post in posts:
                    if downloaded >= limit:
                        return

                    # collect image URLs...
                    urls, gallery_id = [], ''
                    if getattr(post, 'is_gallery', False):
                        gallery_id = post.id
                        for item in post.gallery_data['items']:
                            ext = post.media_metadata[item['media_id']]['m'].split('/')[-1]
                            if ext != 'gif':
                                urls.append(
                                    post.media_metadata[item['media_id']]['s']['u'].split('?')[0]
                                )
                    elif any(post.url.lower().endswith(ext) for ext in ('.jpg','.jpeg','.png')):
                        urls = [post.url]

                    for img_url in urls:
                        if downloaded >= limit:
                            return

                        # download image to disk (unchanged)
                        filename = os.path.basename(urlparse(img_url).path)
                        local_path = f"{self.output_dir}/{filename}"
                        ensure_dir(local_path)
                        r = requests.get(img_url, stream=True); r.raise_for_status()
                        with open(local_path, 'wb') as f:
                            for chunk in r.iter_content(1024):
                                f.write(chunk)

                        # build the record
                        rec = {
                            "id": downloaded + 1,
                            "post_id": post.id,
                            "gallery_id": gallery_id,
                            "local_path": local_path,
                            "file_name": filename,
                            "title": f"{post.title.strip()} - meme on a T-shirt",
                            "description": self._build_description(post.id),
                            "tags": [],
                            "printify_address": f"https://www.reddit.com{post.permalink}",
                            # Printify fields empty for now:
                            "printify_product_id": None,
                            "retail_price": None,
                            "base_cost_pence": None,
                            "profit_estimate": None,
                            "shopify_url": None,
                            "twitter_url": None,
                            "bluesky_url": None,
                            "instagram_url": None,
                            "error": None
                        }

                        # append JSONL line
                        fp.write(json.dumps(rec, ensure_ascii=False) + "\n")
                        downloaded += 1
                        print(f"[✅] Saved JSON record #{downloaded}")

    def _build_description(self, post_id):
        try:
            sub = self.reddit.submission(id=post_id)
            sub.comment_sort = 'top'
            sub.comments.replace_more(limit=0)
            top3 = [c.body.replace('"','').replace("'",'').replace('\n',' ').strip()
                    for c in sub.comments[:3] if len(c.body.strip())>10]
            return '<br><br>'.join(top3)
        except:
            return ''
    def _save_and_record(self, post_id, gallery_id, img_url, title, description, tags, writer, post_permalink=''):
        parsed = urlparse(img_url)
        filename = os.path.basename(parsed.path)
        # use forward slash to avoid backslashes/newlines in CSV
        local_path = f"{self.output_dir}/{filename}"
        ensure_dir(local_path)

        if os.path.exists(local_path):
            return False

        try:
            resp = requests.get(img_url, stream=True)
            resp.raise_for_status()
            with open(local_path, 'wb') as f:
                for chunk in resp.iter_content(1024):
                    f.write(chunk)

            # Compose CSV row with sequential id and cleaned fields
            writer.writerow({
                'id': self._next_id,
                'gallery_id': gallery_id,
                'local_path': local_path,
                'file_name': filename,
                'title': f"{title.strip()} - meme on a T-shirt",
                'description': self._build_description(post_id, ''),
                'tags': ','.join(tags),
                'printify_address': 'none',
                'post_url': f"https://www.reddit.com{post_permalink}",
                'printify_product_id': '',
                'retail_price': '',
                'base_cost_pence': '',
                'profit_estimate': '',
                'shopify_url': '',
                'twitter_url': '',
                'bluesky_url': '',
                'instagram_url': '',
                'error': ''
            })

            self._next_id += 1
            print(f"[✅] Saved: {filename}")
            return True
        except Exception as e:
            print(f"[❌] Error downloading {img_url}: {e}")
            return False

# import os
# import requests
# import praw
# import csv
# from urllib.parse import urlparse
# from dotenv import load_dotenv
#
# def ensure_dir(path):
#     os.makedirs(os.path.dirname(path), exist_ok=True)
#
# class RedditContent:
#     def __init__(self, subreddits, CLIENT_ID, CLIENT_SECRET, USER_AGENT, output_dir='reddit_photos', csv_path='reddit_images.csv'):
#         load_dotenv()
#         self.CLIENT_ID = CLIENT_ID
#         self.CLIENT_SECRET = CLIENT_SECRET
#         self.USER_AGENT = USER_AGENT
#
#         if not all([self.CLIENT_ID, self.CLIENT_SECRET, self.USER_AGENT]):
#             raise ValueError('Missing one or more Reddit API credentials.')
#
#         self.reddit = praw.Reddit(
#             client_id=self.CLIENT_ID,
#             client_secret=self.CLIENT_SECRET,
#             user_agent=self.USER_AGENT
#         )
#
#         self.subreddits = subreddits
#         self.output_dir = output_dir.rstrip('/')
#         self.csv_path = csv_path
#
#     def download_posts(self, limit=10, sort='hot'):
#         fieldnames = [
#             'id', 'gallery_id', 'local_path', 'file_name',
#             'title', 'description', 'tags', 'printify_address', 'post_url',
#             'printify_product_id', 'retail_price', 'base_cost_pence', 'profit_estimate',
#             'shopify_url', 'twitter_url', 'bluesky_url', 'instagram_url', 'error'
#         ]
#
#         write_header = not os.path.exists(self.csv_path)
#         downloaded = 0
#
#         with open(self.csv_path, 'a', newline='', encoding='utf-8') as csvfile:
#             writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
#             if write_header:
#                 writer.writeheader()
#
#             for name in self.subreddits:
#                 subreddit = self.reddit.subreddit(name)
#                 posts = getattr(subreddit, sort)(limit=limit * 3)  # over-fetch in case of skips
#
#                 for post in posts:
#                     if downloaded >= limit:
#                         return
#
#                     if getattr(post, 'is_gallery', False):
#                         gallery = post.gallery_data['items']
#                         gallery_id = post.id
#                         for item in gallery:
#                             if downloaded >= limit:
#                                 return
#                             media_id = item['media_id']
#                             meta = post.media_metadata[media_id]
#                             ext = meta['m'].split('/')[-1]
#                             if ext == 'gif':
#                                 continue
#                             img_url = meta['s']['u'].split('?')[0]
#                             if self._save_and_record(
#                                 post_id=post.id,
#                                 gallery_id=gallery_id,
#                                 img_url=img_url,
#                                 title=post.title,
#                                 description=post.selftext or '',
#                                 tags=[],
#                                 writer=writer,
#                                 post_permalink=post.permalink
#                             ):
#                                 downloaded += 1
#                     else:
#                         url = post.url
#                         if not any(url.lower().endswith(ext) for ext in ['.jpg', '.jpeg', '.png']):
#                             continue
#                         if self._save_and_record(
#                             post_id=post.id,
#                             gallery_id='',
#                             img_url=url,
#                             title=post.title,
#                             description=post.selftext or '',
#                             tags=[],
#                             writer=writer,
#                             post_permalink=post.permalink
#                         ):
#                             downloaded += 1
#
#     def _build_description(self, post_id, original_description):
#         try:
#             submission = self.reddit.submission(id=post_id)
#             submission.comment_sort = 'top'
#             submission.comments.replace_more(limit=0)
#
#             top_comments = []
#             for comment in submission.comments[:3]:
#                 body = comment.body.strip()
#                 if len(body) > 10:
#                     clean_body = body.replace('"', '').replace("'", "").replace('\n', ' ').strip()
#                     top_comments.append(clean_body)
#
#             comment_block = "\n".join(top_comments)
#             return f"{comment_block}\n\n{original_description.strip()}" if comment_block else original_description
#         except Exception as e:
#             print(f"Error fetching comments for post {post_id}: {e}")
#             return original_description
#
#     def _save_and_record(self, post_id, gallery_id, img_url, title, description, tags, writer, post_permalink=''):
#         parsed = urlparse(img_url)
#         filename = os.path.basename(parsed.path)
#         local_path = os.path.join(self.output_dir, filename)
#         ensure_dir(local_path)
#
#         # Skip if already exists (avoid redownloading)
#         if os.path.exists(local_path):
#             print(f"[⏩] Skipped (already exists): {filename}")
#             return False
#
#         try:
#             resp = requests.get(img_url, stream=True)
#             if resp.status_code == 200:
#                 with open(local_path, 'wb') as f:
#                     for chunk in resp.iter_content(1024):
#                         f.write(chunk)
#             else:
#                 print(f"[❌] Failed to download: {img_url}")
#                 return False
#
#             writer.writerow({
#                 'id': post_id,
#                 'gallery_id': gallery_id,
#                 'local_path': local_path,
#                 'file_name': filename,
#                 'title': f"{title.strip()} - meme on a T-shirt",
#                 'description': self._build_description(post_id, ""),
#                 'tags': ','.join(tags),
#                 'printify_address': 'none',
#                 'post_url': f"https://www.reddit.com{post_permalink}",
#                 'printify_product_id': '',
#                 'retail_price': '',
#                 'base_cost_pence': '',
#                 'profit_estimate': '',
#                 'shopify_url': '',
#                 'twitter_url': '',
#                 'bluesky_url': '',
#                 'instagram_url': '',
#                 'error': ''
#             })
#             print(f"[✅] Saved: {filename}")
#             return True
#         except Exception as e:
#             print(f"[❌] Error downloading {img_url}: {e}")
#             return False
#


# import os
# import requests
# import praw
# import csv
# from urllib.parse import urlparse
# from dotenv import load_dotenv
#
# def ensure_dir(path):
#     os.makedirs(os.path.dirname(path), exist_ok=True)
#
# class RedditContent:
#     """
#     A class to fetch images from Reddit and save them locally,
#     along with generating a CSV metadata file.
#     """
#     def __init__(self, subreddits, CLIENT_ID, CLIENT_SECRET, USER_AGENT, output_dir='reddit_photos', csv_path='reddit_images.csv'):
#         # Load credentials from .env
#         load_dotenv()
#         # self.CLIENT_ID = os.getenv('REDDIT_CLIENT_ID')
#         # self.CLIENT_SECRET = os.getenv('REDDIT_CLIENT_SECRET')
#         # self.USER_AGENT = os.getenv('REDDIT_USER_AGENT')
#         self.CLIENT_ID = CLIENT_ID
#         self.CLIENT_SECRET = CLIENT_SECRET
#         self.USER_AGENT = USER_AGENT
#
#
#         if not all([self.CLIENT_ID, self.CLIENT_SECRET, self.USER_AGENT]):
#             raise ValueError('Missing one or more Reddit API credentials in environment variables.')
#
#         self.reddit = praw.Reddit(
#             client_id=self.CLIENT_ID,
#             client_secret=self.CLIENT_SECRET,
#             user_agent=self.USER_AGENT
#         )
#
#         self.subreddits = subreddits
#         self.output_dir = output_dir.rstrip('/')
#         self.csv_path = csv_path
#
#     def download_posts(self, limit=10, sort='hot'):
#         """
#         Fetches posts from the configured subreddits and downloads images.
#         Creates (or appends to) a CSV of metadata.
#         """
#         fieldnames = [
#             'id', 'gallery_id', 'local_path', 'file_name',
#             'title', 'description', 'tags', 'printify_address', 'post_url'
#         ]
#
#         # Open CSV for writing
#         write_header = not os.path.exists(self.csv_path)
#         with open(self.csv_path, 'a', newline='', encoding='utf-8') as csvfile:
#             writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
#             if write_header:
#                 writer.writeheader()
#
#             for name in self.subreddits:
#                 subreddit = self.reddit.subreddit(name)
#                 posts = getattr(subreddit, sort)(limit=limit)
#
#                 for post in posts:
#                     # Determine if post has an image or gallery
#                     if getattr(post, 'is_gallery', False):
#                         # reddit gallery
#                         gallery = post.gallery_data['items']
#                         gallery_id = post.id
#                         for item in gallery:
#                             media_id = item['media_id']
#                             meta = post.media_metadata[media_id]
#                             ext = meta['m'].split('/')[-1]
#                             img_url = meta['s']['u'].split('?')[0]
#                             self._save_and_record(
#                                 post_id=post.id,
#                                 gallery_id=gallery_id,
#                                 img_url=img_url,
#                                 title=post.title,
#                                 description=post.selftext or '',
#                                 tags=[],
#                                 writer=writer
#                             )
#                     else:
#                         # single image or link
#                         url = post.url
#                         # skip non-image links
#                         if not any(url.lower().endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.gif']):
#                             continue
#                         self._save_and_record(
#                             post_id=post.id,
#                             gallery_id='',
#                             img_url=url,
#                             title=post.title,
#                             description=post.selftext or '',
#                             tags=[],
#                             writer=writer,
#                             post_permalink=post.permalink
#                         )
#
#     def _build_description(self, post_id, original_description):
#         try:
#             submission = self.reddit.submission(id=post_id)
#             submission.comment_sort = 'top'
#             submission.comments.replace_more(limit=0)
#
#             top_comments = []
#             for comment in submission.comments[:3]:
#                 body = comment.body.strip()
#                 if len(body) > 10:
#                     # Remove internal quotes and line breaks for clean CSV
#                     clean_body = body.replace('"', '').replace("'", "").replace('\n', ' ').strip()
#                     top_comments.append(clean_body)
#
#             comment_block = "\n".join(top_comments)
#             return f"{comment_block}\n\n{original_description.strip()}" if comment_block else original_description
#         except Exception as e:
#             print(f"Error fetching comments for post {post_id}: {e}")
#             return original_description
#
#     def _save_and_record(self, post_id, gallery_id, img_url,
#                          title, description, tags, writer, post_permalink=''):
#         # Determine filename and path
#         parsed = urlparse(img_url)
#         filename = os.path.basename(parsed.path)
#         local_subdir = os.path.join(self.output_dir)
#         local_path = os.path.join(local_subdir, filename)
#
#         # Ensure directory exists
#         ensure_dir(local_path)
#
#         # Download image
#         resp = requests.get(img_url, stream=True)
#         if resp.status_code == 200:
#             with open(local_path, 'wb') as f:
#                 for chunk in resp.iter_content(1024):
#                     f.write(chunk)
#         else:
#             print(f"Failed to download {img_url}")
#             return
#
#         # Write CSV row
#         writer.writerow({
#             'id': post_id,
#             'gallery_id': gallery_id,
#             'local_path': local_path,
#             'file_name': filename,
#             'title': f"{title.strip()} - meme on a T-shirt",
#             'description': self._build_description(post_id, description),
#             'tags': tags,
#             'printify_address': 'none',
#             'post_url': f"https://www.reddit.com{post_permalink}"
#         })

# if __name__ == '__main__':
#     # Example usage
#     subreddits = [
#         'dankmemes', 'HistoryMemes', 'PoliticalMemes',
#         'TrumpMemes', 'Memes_Of_The_Dank', 'PoliticalCompassMemes'
#     ]
#     scraper = RedditContent(subreddits)
#     scraper.download_posts(limit=50, sort='hot')
#     print('Download complete.')
