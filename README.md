# Meme T-Shirt Bot – Fully Automated Print-on-Demand Store

www.tshirtmemes.org

This project is a self-sustaining, end-to-end pipeline that scrapes fresh memes from Reddit, turns them into t-shirt designs, publishes them to a Shopify storefront using Printify, and promotes them on social media—all without human intervention.

---

![tshirt page](https://github.com/user-attachments/assets/74409b3c-56ed-4aca-956e-7c7b9a700177)

---

# Key Technologies

    Python: Core automation logic

    Reddit API (PRAW): Fetches high-engagement meme images from selected subreddits

    Printify API: Creates new product listings with meme images on t-shirts

    Shopify API: Publishes products to a live Shopify store

    Twitter API (v2) & Bluesky (ATProto): Posts each meme + product link to social media

    JSONL-based pipeline: Tracks image history and publication status

# Automation Flow

    Collect Memes: Use Reddit API to find high-quality meme posts with suitable image formats.

    Generate Products: Format images, create print products via Printify, and sync to Shopify.

    Promote: Post links to Twitter and Bluesky using a retry system with rate-limit handling.

    Track Progress: Update JSONL files for state persistence and cleanup posted images.

# Challenges & Lessons

    Seamlessly integrating multiple third-party APIs with different data models and auth systems.

    Handling rate-limiting (especially Twitter) and gracefully retrying failed posts.

    Building a resilient, re-runnable process that maintains state and avoids duplication.

# Why I Built It

I’ve long been fascinated by automation and the idea of software that works for you. This project is a playful but technically complete experiment in building a "set-and-forget" digital product business. It demonstrates the power of combining APIs into a creative workflow that would otherwise require a human operator.

---

![front_page](https://github.com/user-attachments/assets/617e8f4a-aaed-42e6-b86a-b8a8a3c95a93)

---

![twitter_tshirt](https://github.com/user-attachments/assets/fd140be2-34a5-4938-b93f-fd7c1808478a)

---

![bluesky_tshirt](https://github.com/user-attachments/assets/6a41fe34-1b5e-4a6d-8387-e0b2099acea8)


