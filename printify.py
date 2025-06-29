import os
import json
import base64
import requests
import re
from datetime import datetime, timedelta
from dotenv import load_dotenv
load_dotenv()

class PrintifyUploader:
    def __init__(
        self,
        access_token,
        shop_id,
        shopify_domain,
        shopify_access_token,
        default_blueprint=5,
        default_provider=99,
        default_price=1999
    ):
        self.access_token = access_token
        self.shop_id = shop_id
        self.shopify_domain = shopify_domain.rstrip('/')  # e.g. "yourstore.myshopify.com"
        self.shopify_access_token = shopify_access_token
        self.base_url = 'https://api.printify.com/v1'
        self.headers = {"Authorization": f"Bearer {self.access_token}", "Content-Type": "application/json"}
        self.default_blueprint = default_blueprint
        self.default_provider = default_provider
        self.default_price = default_price
        self.full_blurb = (
            "Printed on demand by Printify. Ships from the US or UK depending on location." +
            "\n\n" +
            "This shirt is made from responsibly sourced materials and printed using sustainable practices. " +
            "To care for your shirt, machine wash cold inside-out with like colors and tumble dry low. " +
            "Do not iron directly on the print." +
            "\n"
        )
        self.variant_ids = [17643]

    def upload_image(self, path, fname):
        url = f"{self.base_url}/uploads/images.json"
        with open(path, 'rb') as f:
            data = base64.b64encode(f.read()).decode()
        r = requests.post(url, headers=self.headers, json={"file_name": fname, "contents": data})
        r.raise_for_status()
        return r.json()["id"]

    def create_product(self, image_id, title, desc, tags, price):
        url = f"{self.base_url}/shops/{self.shop_id}/products.json"
        payload = {
            "title": title,
            "description": desc,
            "tags": tags,
            "blueprint_id": self.default_blueprint,
            "print_provider_id": self.default_provider,
            "variants": [{"id": vid, "price": price, "is_enabled": True} for vid in self.variant_ids],
            "print_areas": [{
                "variant_ids": self.variant_ids,
                "placeholders": [{"position": "front", "images": [{"id": image_id, "x": 0.5, "y": 0.5, "scale": 1.0, "angle": 0}]}]
            }]
        }
        r = requests.post(url, headers=self.headers, json=payload)
        r.raise_for_status()
        return r.json()

    def publish_product(self, pid):
        url = f"{self.base_url}/shops/{self.shop_id}/products/{pid}/publish.json"
        payload = {key: True for key in ["title", "description", "images", "variants", "tags", "keyFeatures", "shipping_template"]}
        payload["sales_channel"] = "shopify"
        r = requests.post(url, headers=self.headers, json=payload)
        r.raise_for_status()
        return r.json()

    def get_shopify_url(self, pid, title=None):
        r = requests.get(f"{self.base_url}/shops/{self.shop_id}/products/{pid}.json", headers=self.headers)
        r.raise_for_status()
        handle = r.json().get("external", {}).get("handle")
        if handle:
            return f"https://{self.shopify_domain}/products/{handle}"
        if title:
            slug = title.lower()
            slug = re.sub(r"[^a-z0-9]+", "-", slug).strip("-")
            return f"https://{self.shopify_domain}/products/{slug}"
        return ""

    def get_shopify_sales_count(self, shopify_product_id, days_back=60):
        """
        Fetch total quantity sold for a given Shopify product in the last `days_back` days.
        Requires `read_orders` scope on the Shopify access token.
        """
        if not shopify_product_id:
            return 0

        # Shopify Admin API: extract numeric ID from gid or string
        # e.g. gid://shopify/Product/1234567890 or "1234567890"
        m = re.search(r"(\d+)$", shopify_product_id)
        if not m:
            return 0
        pid = m.group(1)

        since = (datetime.utcnow() - timedelta(days=days_back)).strftime('%Y-%m-%dT%H:%M:%SZ')
        url = f"https://{self.shopify_domain}/admin/api/2023-10/orders.json"
        headers = {"X-Shopify-Access-Token": self.shopify_access_token}
        params = {
            "status": "any",
            "created_at_min": since,
            "limit": 250,
            "fields": "line_items"
        }

        total = 0
        while True:
            resp = requests.get(url, headers=headers, params=params)
            resp.raise_for_status()
            orders = resp.json().get('orders', [])
            for order in orders:
                for item in order.get('line_items', []):
                    if str(item.get('product_id')) == pid:
                        total += int(item.get('quantity', 0))
            # pagination: look for next page link
            link = resp.headers.get('Link', '')
            if 'rel="next"' not in link:
                break
            # parse next page URL
            next_url = re.search(r'<([^>]+)>; rel="next"', link)
            if not next_url:
                break
            url = next_url.group(1)

        return total

    def delete_printify_product(self, product_id):
        url = f"{self.base_url}/shops/{self.shop_id}/products/{product_id}.json"
        r = requests.delete(url, headers=self.headers)
        r.raise_for_status()
        return r.status_code == 204

    def process_jsonl(self, in_path='reddit_images.jsonl', out_path='printify_upload.jsonl'):
        # load existing records
        with open(in_path, encoding='utf-8') as f:
            records = [json.loads(l) for l in f if l.strip()]

        for rec in records:
            if rec.get('printify_product_id'):
                continue
            img_id = self.upload_image(rec['local_path'], rec['file_name'])
            title = rec['title']
            desc = f"{rec.get('description','')}<br><br>{self.full_blurb.replace(chr(10), '<br>')}"

            prod = self.create_product(img_id, title, desc, rec.get('tags', []), self.default_price)
            self.publish_product(prod['id'])

            shop_url = self.get_shopify_url(prod['id'], title)
            shopify_id = prod.get("external", {}).get("id")

            rec.update({
                'printify_product_id': prod['id'],
                'shopify_product_id': shopify_id,
                'retail_price': self.default_price / 100,
                'shopify_url': shop_url,
                'created_at': datetime.utcnow().strftime('%Y-%m-%d')
            })
            print(f"Published {rec['id']} → {shop_url}")

        # save updated JSONL
        os.makedirs(os.path.dirname(out_path) or '.', exist_ok=True)
        with open(out_path, 'w', encoding='utf-8') as fp:
            for rec in records:
                fp.write(json.dumps(rec, ensure_ascii=False) + '\n')
        print(f"Done → {out_path}")

    def delete_old_unsold_products(self, jsonl_path='printify_upload.jsonl', min_sales=3, max_age_days=20):
        if not os.path.exists(jsonl_path):
            print("No JSONL file found.")
            return

        with open(jsonl_path, encoding='utf-8') as f:
            records = [json.loads(l) for l in f if l.strip()]

        cutoff = datetime.utcnow() - timedelta(days=max_age_days)
        survivors = []

        for rec in records:
            created = rec.get('created_at')
            pid = rec.get('shopify_product_id')
            if not created or not pid:
                survivors.append(rec)
                continue

            created_date = datetime.strptime(created, '%Y-%m-%d')
            if created_date > cutoff:
                survivors.append(rec)
                continue

            sales = self.get_shopify_sales_count(pid)
            if sales < min_sales:
                try:
                    self.delete_printify_product(rec['printify_product_id'])
                    print(f"❌ Deleted {rec['printify_product_id']} (Age: {(datetime.utcnow()-created_date).days}d, Sales: {sales})")
                    continue
                except Exception as e:
                    print(f"Deletion error for {rec['printify_product_id']}: {e}")
            survivors.append(rec)

        with open(jsonl_path, 'w', encoding='utf-8') as f:
            for rec in survivors:
                f.write(json.dumps(rec, ensure_ascii=False) + '\n')
        print("🧹 Cleanup complete.")


# import os
# import json
# import base64
# import requests
# from reddit_downloads import RedditContent  # if needed
#
# class PrintifyUploader:
#     def __init__(self, access_token, shop_id, shopify_domain,
#                  default_blueprint=5, default_provider=99, default_price=1999):
#         self.access_token=access_token
#         self.shop_id=shop_id
#         self.shopify_domain=shopify_domain
#         self.base_url='https://api.printify.com/v1'
#         self.headers={"Authorization":f"Bearer {self.access_token}","Content-Type":"application/json"}
#         self.default_blueprint=default_blueprint
#         self.default_provider=default_provider
#         self.default_price=default_price
#         self.full_blurb = (
#             "Printed on demand by Printify. Ships from the US or UK depending on location.\n\n"
#             "This shirt is made from responsibly sourced materials and printed using sustainable practices. "
#             "To care for your shirt, machine wash cold inside-out with like colors and tumble dry low. "
#             "Do not iron directly on the print.\n"
#         )
#
#     def upload_image(self, path, fname):
#         url=f"{self.base_url}/uploads/images.json"
#         with open(path,'rb') as f: data=base64.b64encode(f.read()).decode()
#         r=requests.post(url, headers=self.headers, json={"file_name":fname,"contents":data})
#         r.raise_for_status(); return r.json()["id"]
#
#     def create_product(self, image_id, title, desc, tags, prices):
#         url=f"{self.base_url}/shops/{self.shop_id}/products.json"
#         payload={
#             "title":title,
#             "description":desc,
#             "tags":tags,
#             "blueprint_id":self.default_blueprint,
#             "print_provider_id":self.default_provider,
#             "variants":[{"id":v,"price":prices,"is_enabled":True} for v in [17643]],
#             "print_areas":[{"variant_ids":[17643],"placeholders":[{"position":"front","images":[{"id":image_id,"x":0.5,"y":0.5,"scale":1.0,"angle":0}]}]}]
#         }
#         r=requests.post(url, headers=self.headers, json=payload)
#         r.raise_for_status(); return r.json()
#
#     def publish_product(self, pid):
#         url=f"{self.base_url}/shops/{self.shop_id}/products/{pid}/publish.json"
#         r=requests.post(url, headers=self.headers, json={k:True for k in ["title","description","images","variants","tags","keyFeatures","shipping_template"]}); r.raise_for_status()
#
#
#     def get_shopify_url(self, pid):
#         r=requests.get(f"{self.base_url}/shops/{self.shop_id}/products/{pid}.json",headers=self.headers); r.raise_for_status()
#         h=r.json().get("external",{}).get("handle"); return f"https://{self.shopify_domain}/products/{h}" if h else ""
#
#     def process_jsonl(self, in_path='reddit_images.jsonl', out_path='printify_upload.jsonl'):
#         # load
#         records=[json.loads(l) for l in open(in_path,encoding='utf-8') if l.strip()]
#         # update
#         for rec in records:
#             if rec.get('printify_product_id'): continue
#             img_id=self.upload_image(rec['local_path'],rec['file_name'])
#             title=rec['title']
#             desc=f"{rec['description']}\n\n{self.full_blurb}"
#             prod=self.create_product(img_id,title,desc,rec['tags'],self.default_price)
#             self.publish_product(prod['id'])
#             shop_url=self.get_shopify_url(prod['id'])
#             rec.update({
#                 'printify_product_id':prod['id'],
#                 'retail_price':self.default_price/100,
#                 'shopify_url':shop_url
#             })
#             print(f"Published {rec['id']} → {shop_url}")
#         # write
#         with open(out_path,'w',encoding='utf-8') as fp:
#             for rec in records:
#                 fp.write(json.dumps(rec,ensure_ascii=False)+'\n')
#         print(f"Done → {out_path}")


    # def get_shopify_url(self, pid):
    #     r=requests.get(f"{self.base_url}/shops/{self.shop_id}/products/{pid}.json",headers=self.headers); r.raise_for_status()
    #     h=r.json().get("external",{}).get("handle"); return f"https://{self.shopify_domain}/products/{h}" if h else ""
    #
    # def process_jsonl(self, in_path='reddit_images.jsonl', out_path='printify_upload.jsonl'):
    #     # load
    #     records=[json.loads(l) for l in open(in_path,encoding='utf-8') if l.strip()]
    #     # update
    #     for rec in records:
    #         if rec.get('printify_product_id'): continue
    #         img_id=self.upload_image(rec['local_path'],rec['file_name'])
    #         title=rec['title']
    #         desc=f"{rec['description']}\n\n{self.full_blurb}"
    #         prod=self.create_product(img_id,title,desc,rec['tags'],self.default_price)
    #         self.publish_product(prod['id'])
    #         shop_url=self.get_shopify_url(prod['id'])
    #         rec.update({
    #             'printify_product_id':prod['id'],
    #             'retail_price':self.default_price/100,
    #             'shopify_url':shop_url
    #         })
    #         print(f"Published {rec['id']} → {shop_url}")
    #     # write
    #     with open(out_path,'w',encoding='utf-8') as fp:
    #         for rec in records:
    #             fp.write(json.dumps(rec,ensure_ascii=False)+'\n')
    #     print(f"Done → {out_path}")



# import math
# import requests
# import base64
# import pandas as pd
# import os
# import ast
# import json
#
# class PrintifyUploader:
#     def __init__(
#         self,
#         access_token,
#         shop_id,
#         shopify_domain,
#         default_blueprint=5,
#         default_provider=99,
#         default_variant=17887,
#         default_price=1999
#     ):
#         self.access_token = access_token
#         self.shop_id = shop_id
#         self.shopify_domain = shopify_domain
#         self.base_url = "https://api.printify.com/v1"
#         self.headers = {
#             "Authorization": f"Bearer {self.access_token}",
#             "Content-Type": "application/json"
#         }
#         self.default_blueprint = default_blueprint
#         self.default_provider = default_provider
#         self.default_variant = default_variant
#         self.default_price = default_price
#
#     def upload_image(self, image_path, file_name):
#         url = f"{self.base_url}/uploads/images.json"
#         with open(image_path, "rb") as img_file:
#             b64_image = base64.b64encode(img_file.read()).decode('utf-8')
#         response = requests.post(
#             url, headers=self.headers, json={"file_name": file_name, "contents": b64_image}
#         )
#         response.raise_for_status()
#         return response.json()["id"]
#
#     def get_variant_cost(self, blueprint_id, provider_id, variant_id):
#         url = (
#             f"{self.base_url}/catalog/blueprints/{blueprint_id}"
#             f"/print_providers/{provider_id}/variants.json"
#         )
#         res = requests.get(url, headers=self.headers)
#         if res.status_code == 404:
#             return 0
#         res.raise_for_status()
#         for variant in res.json().get("variants", []):
#             if variant.get("id") == variant_id:
#                 base_price = variant.get("price", 0) or 0
#                 print_price = sum(
#                     ph.get("price", 0) or 0
#                     for area in variant.get("print_areas", [])
#                     for ph in area.get("placeholders", [])
#                     if ph.get("position") == "front"
#                 )
#                 return base_price + print_price
#         return 0
#
#     def clean_floats(self, obj):
#         if isinstance(obj, float):
#             if math.isinf(obj) or math.isnan(obj):
#                 return None
#             return obj
#         elif isinstance(obj, dict):
#             return {k: self.clean_floats(v) for k, v in obj.items()}
#         elif isinstance(obj, list):
#             return [self.clean_floats(v) for v in obj]
#         return obj
#
#     def create_product(
#         self,
#         image_id,
#         title,
#         description,
#         tags,
#         variant_ids,
#         price,
#         blueprint_id=None,
#         print_provider_id=None
#     ):
#         url = f"{self.base_url}/shops/{self.shop_id}/products.json"
#         # ensure description is a string
#         description = description if isinstance(description, str) else str(description or "")
#         payload = {
#             "title": title,
#             "description": description,
#             "tags": tags,
#             "blueprint_id": blueprint_id or self.default_blueprint,
#             "print_provider_id": print_provider_id or self.default_provider,
#             "variants": [{"id": vid, "price": price, "is_enabled": True} for vid in variant_ids],
#             "print_areas": [{
#                 "variant_ids": variant_ids,
#                 "placeholders": [{
#                     "position": "front",
#                     "images": [{"id": image_id, "x": 0.5, "y": 0.5, "scale": 1.0, "angle": 0}]
#                 }]
#             }]
#         }
#         clean_payload = self.clean_floats(payload)
#         response = requests.post(url, headers=self.headers, json=clean_payload)
#         if not response.ok:
#             print("❌ Product creation failed:")
#             print(json.dumps(clean_payload, indent=2))
#             print(f"❌ Response: {response.status_code} {response.text}")
#         response.raise_for_status()
#         return response.json()
#
#     def publish_product(self, product_id, publish_to_store=True):
#         url = f"{self.base_url}/shops/{self.shop_id}/products/{product_id}/publish.json"
#         payload = {key: True for key in ["title", "description", "images", "variants", "tags", "keyFeatures", "shipping_template"]}
#         if not publish_to_store:
#             payload["sales_channel"] = "printify"
#         clean_payload = self.clean_floats(payload)
#         res = requests.post(url, headers=self.headers, json=clean_payload)
#         res.raise_for_status()
#         return res.json()
#
#     def get_shopify_url(self, product_id):
#         url = f"{self.base_url}/shops/{self.shop_id}/products/{product_id}.json"
#         res = requests.get(url, headers=self.headers)
#         res.raise_for_status()
#         handle = res.json().get("external", {}).get("handle")
#         return f"https://{self.shopify_domain}/products/{handle}" if handle else ""
#
#
#     def process_jsonl(self, in_path='reddit_images.jsonl', out_path='printify_upload.jsonl'):
#         # read all records
#         records = []
#         with open(in_path, 'r', encoding='utf-8') as fp:
#             for line in fp:
#                 rec = json.loads(line)
#                 records.append(rec)
#
#         # process un‐uploaded ones
#         for rec in records:
#             if rec.get('printify_product_id'):
#                 continue  # already done
#
#             # upload image
#             img_id = self.upload_image(rec['local_path'], rec['file_name'])
#
#             full_blurb = (
#                 "Printed on demand by Printify. Ships from the US or UK depending on location.\n\n"
#                 "This shirt is made from responsibly sourced materials and printed using sustainable practices. "
#                 "To care for your shirt, machine wash cold inside-out with like colors and tumble dry low. "
#                 "Do not iron directly on the print.\n"
#             )
#             # build title/description from rec
#             title = rec['title']
#             desc = rec['description'] + "\n\n" + full_blurb
#
#             # call Printify
#             prod = self.create_product(
#                 image_id=img_id,
#                 title=title,
#                 description=desc,
#                 tags=rec['tags'],
#                 variant_ids=self.variant_ids,
#                 price=self.default_price
#             )
#             self.publish_product(prod['id'])
#             shop_url = self.get_shopify_url(prod['id'])
#
#             # update our record
#             rec.update({
#                 "printify_product_id": prod['id'],
#                 "retail_price": self.default_price/100,
#                 "base_cost_pence": self.default_price,
#                 "profit_estimate": 0,
#                 "shopify_url": shop_url,
#                 "error": None
#             })
#             print(f"[✅] Uploaded record {rec['id']} → {shop_url}")
#
#         # write out processed JSONL
#         with open(out_path, 'w', encoding='utf-8') as fp:
#             for rec in records:
#                 fp.write(json.dumps(rec, ensure_ascii=False) + "\n")
#
#         print(f"✅ All done: {out_path}")
#



    # def process_csv(
    #     self,
    #     csv_path,
    #     image_dir,
    #     variant_ids=None,
    #     provider_id=None,
    #     blueprint_id=None
    # ):
    #     df = pd.read_csv(csv_path)
    #     # ensure error column exists
    #     df['error'] = df.get('error', '').astype(str)
    #     variant_ids = variant_ids or [17643, 17644, 17645, 17646, 17647]
    #     provider_id = provider_id or self.default_provider
    #     blueprint_id = blueprint_id or self.default_blueprint
    #
    #     # iterate with row_num for logging
    #     for row_num, (idx, row) in enumerate(df.iterrows(), start=1):
    #         try:
    #             img_path = os.path.join(image_dir, row['local_path'])
    #             if not os.path.isfile(img_path):
    #                 raise FileNotFoundError(f"Image not found: {img_path}")
    #             img_id = self.upload_image(img_path, row['file_name'])
    #
    #             # parse tags
    #             tags = []
    #             try:
    #                 parsed = ast.literal_eval(row.get('tags', '[]'))
    #                 tags = parsed if isinstance(parsed, list) else []
    #             except Exception:
    #                 pass
    #
    #             # calculate costs
    #             costs = []
    #             for vid in variant_ids:
    #                 cost = self.get_variant_cost(blueprint_id, provider_id, vid)
    #                 if cost > 0:
    #                     costs.append(cost)
    #             if costs:
    #                 max_cost = max(costs)
    #                 retail = max(round(max_cost * 1.6), self.default_price)
    #             else:
    #                 max_cost = 0
    #                 retail = self.default_price
    #                 print(f"[⚠️] No cost data. Fallback retail = {retail}p")
    #
    #             # ensure description string
    #             description = row['description'] if pd.notna(row['description']) else ""
    #
    #             product = self.create_product(
    #                 image_id=img_id,
    #                 title=row['title'],
    #                 description=description,
    #                 tags=tags,
    #                 variant_ids=variant_ids,
    #                 price=retail,
    #                 blueprint_id=blueprint_id,
    #                 print_provider_id=provider_id
    #             )
    #             self.publish_product(product['id'])
    #             shop_url = self.get_shopify_url(product['id'])
    #
    #             # update df
    #             df.at[idx, 'printify_product_id'] = product['id']
    #             df.at[idx, 'retail_price'] = retail / 100
    #             df.at[idx, 'base_cost_pence'] = max_cost
    #             df.at[idx, 'profit_estimate'] = (retail - max_cost) / 100
    #             df.at[idx, 'shopify_url'] = shop_url
    #             df.at[idx, 'twitter_url'] = ''
    #             df.at[idx, 'bluesky_url'] = ''
    #             df.at[idx, 'instagram_url'] = ''
    #             df.at[idx, 'error'] = ''
    #             print(f"[✅] Row {row_num}: Created & published → {shop_url}")
    #
    #         except Exception as e:
    #             df.at[idx, 'error'] = repr(e)
    #             print(f"[❌] Row {row_num}: {e}")
    #
    #     df.to_csv(csv_path, index=False)
    #     print(f"✅ CSV updated → {csv_path}")





# import requests
# import base64
# import pandas as pd
# import os
# import ast
#
# class PrintifyUploader:
#     def __init__(self, access_token, shop_id, shopify_domain,
#                  default_blueprint=9, default_provider=5, default_variant=17887, default_price=1999):
#         self.access_token = access_token
#         self.shop_id = shop_id
#         self.shopify_domain = shopify_domain  # e.g., yourstore.myshopify.com
#         self.base_url = "https://api.printify.com/v1"
#         self.headers = {
#             "Authorization": f"Bearer {self.access_token}",
#             "Content-Type": "application/json"
#         }
#         self.default_blueprint = default_blueprint
#         self.default_provider = default_provider
#         self.default_variant = default_variant
#         self.default_price = default_price
#
#     def upload_image(self, image_path, file_name):
#         upload_url = f"{self.base_url}/uploads/images.json"
#         with open(image_path, "rb") as img_file:
#             img_b64 = base64.b64encode(img_file.read()).decode('utf-8')
#         payload = {"file_name": file_name, "contents": img_b64}
#         res = requests.post(upload_url, headers=self.headers, json=payload)
#         res.raise_for_status()
#         return res.json()["id"]
#
#     def get_total_variant_cost(self, blueprint_id, provider_id, variant_id):
#         url = f"{self.base_url}/catalog/blueprints/{blueprint_id}/print_providers/{provider_id}/variants.json"
#         res = requests.get(url, headers=self.headers)
#         res.raise_for_status()
#         data = res.json()
#         variants = data.get("variants", [])
#         for v in variants:
#             if v.get("id") == variant_id:
#                 base_price = v.get("price", 0)
#                 print_price = 0
#                 for area in v.get("print_areas", []):
#                     for ph in area.get("placeholders", []):
#                         if ph.get("position") == "front":
#                             print_price += ph.get("price", 0)
#                 return base_price + print_price
#         return 0
#
#     def create_product(self, image_id, title, description, tags, variant_ids, price,
#                        blueprint_id=None, print_provider_id=None):
#         blueprint_id = blueprint_id or self.default_blueprint
#         print_provider_id = print_provider_id or self.default_provider
#         url = f"{self.base_url}/shops/{self.shop_id}/products.json"
#
#         image_placement = {"id": image_id, "x": 0.5, "y": 0.5, "scale": 1.0, "angle": 0}
#         payload = {
#             "title": title,
#             "description": description,
#             "tags": tags,
#             "blueprint_id": blueprint_id,
#             "print_provider_id": print_provider_id,
#             "variants": [{"id": vid, "price": price, "is_enabled": True} for vid in variant_ids],
#             "print_areas": [{
#                 "variant_ids": variant_ids,
#                 "placeholders": [{"position": "front", "images": [image_placement]}]
#             }]
#         }
#
#         response = requests.post(url, headers=self.headers, json=payload)
#         if not response.ok:
#             import json
#             print("❌ create_product payload:")
#             print(json.dumps(payload, indent=2))
#             print(f"❌ create_product response: {response.status_code} {response.text}")
#         response.raise_for_status()
#         return response.json()
#
#     def publish_product(self, product_id, publish_to_store=True):
#         url = f"{self.base_url}/shops/{self.shop_id}/products/{product_id}/publish.json"
#         payload = {
#             "title": True,
#             "description": True,
#             "images": True,
#             "variants": True,
#             "tags": True,
#             "keyFeatures": True,
#             "shipping_template": True
#         }
#         if not publish_to_store:
#             payload["sales_channel"] = "printify"
#         res = requests.post(url, headers=self.headers, json=payload)
#         res.raise_for_status()
#         return res.json()
#
#     def get_shopify_url(self, product_id):
#         url = f"{self.base_url}/shops/{self.shop_id}/products/{product_id}.json"
#         res = requests.get(url, headers=self.headers)
#         res.raise_for_status()
#         data = res.json()
#         if not isinstance(data, dict):
#             return ""
#         handle = data.get("external", {}).get("handle")
#         return f"https://{self.shopify_domain}/products/{handle}" if handle else ""
#
#     def process_csv(self, csv_path, image_dir):
#         df = pd.read_csv(csv_path)
#         for idx, row in df[:3].iterrows():
#             try:
#                 # upload image
#                 img_path = os.path.join(image_dir, row['local_path'])
#                 if not os.path.exists(img_path):
#                     raise FileNotFoundError(f"Image not found: {img_path}")
#                 img_id = self.upload_image(img_path, row['file_name'])
#
#                 # parse tags
#                 try:
#                     tags = ast.literal_eval(row.get('tags', '[]'))
#                     if not isinstance(tags, list):
#                         tags = []
#                 except Exception:
#                     tags = []
#
#                 # define variant IDs
#                 variants = [17643, 17644, 17645, 17646, 17647]
#
#                 # get cost and set price with fallback
#                 costs = []
#                 for vid in variants:
#                     try:
#                         cost = self.get_total_variant_cost(5, 99, vid)
#                         if cost > 0:
#                             costs.append(cost)
#                     except Exception as e:
#                         print(f"[⚠️] Variant {vid} cost error: {e}")
#                 if costs:
#                     max_cost = max(costs)
#                     retail = max(int(max_cost * 1.6), self.default_price)
#                 else:
#                     max_cost = 0
#                     retail = self.default_price
#                     print(f"[⚠️] No valid cost data. Fallback to retail = {retail}p")
#
#                 # create & publish
#                 prod = self.create_product(
#                     image_id=img_id,
#                     title=row.get('title', 'T-Shirt'),
#                     description=row.get('description', ''),
#                     tags=tags,
#                     variant_ids=variants,
#                     price=retail,
#                     blueprint_id=5,
#                     print_provider_id=99
#                 )
#                 self.publish_product(prod['id'])
#                 shop_url = self.get_shopify_url(prod['id'])
#
#                 # update DataFrame
#                 df.at[idx, 'printify_product_id'] = prod['id']
#                 df.at[idx, 'retail_price'] = retail / 100
#                 df.at[idx, 'base_cost_pence'] = max_cost
#                 df.at[idx, 'profit_estimate'] = (retail - max_cost) / 100
#                 df.at[idx, 'shopify_url'] = shop_url
#                 df.at[idx, 'twitter_url'] = ''
#                 df.at[idx, 'bluesky_url'] = ''
#                 df.at[idx, 'instagram_url'] = ''
#                 df.at[idx, 'error'] = ''
#                 print(f"[✅] Row {idx + 1}: Created & published ({shop_url})")
#
#             except Exception as e:
#                 df.at[idx, 'error'] = str(e)
#                 print(f"[❌] Row {idx + 1}: {e}")
#
#         df.to_csv(csv_path, index=False)
#         print(f"✅ CSV updated: {csv_path}")








# import requests
# import base64
# import pandas as pd
# import os
# import ast
#
# class PrintifyUploader:
#     def __init__(self, access_token, shop_id, shopify_domain,
#                  default_blueprint=9, default_provider=5, default_variant=17887, default_price=1999):
#         self.access_token = access_token
#         self.shop_id = shop_id
#         self.shopify_domain = shopify_domain  # e.g., yourstore.myshopify.com
#         self.base_url = "https://api.printify.com/v1"
#         self.headers = {
#             "Authorization": f"Bearer {self.access_token}",
#             "Content-Type": "application/json"
#         }
#         self.default_blueprint = default_blueprint
#         self.default_provider = default_provider
#         self.default_variant = default_variant
#         self.default_price = default_price
#
#     def upload_image(self, image_path, file_name):
#         upload_url = f"{self.base_url}/uploads/images.json"
#         with open(image_path, "rb") as img_file:
#             img_b64 = base64.b64encode(img_file.read()).decode('utf-8')
#         payload = {"file_name": file_name, "contents": img_b64}
#         res = requests.post(upload_url, headers=self.headers, json=payload)
#         res.raise_for_status()
#         return res.json()["id"]
#
#     def get_total_variant_cost(self, blueprint_id, provider_id, variant_id):
#         url = f"{self.base_url}/catalog/blueprints/{blueprint_id}/print_providers/{provider_id}/variants.json"
#         res = requests.get(url, headers=self.headers)
#         res.raise_for_status()
#         data = res.json()
#         variants = data.get("variants", [])  # correct extraction
#         for v in variants:
#             if v.get("id") == variant_id:
#                 base_price = v.get("price", 0)
#                 print_price = 0
#                 for area in v.get("print_areas", []):
#                     for ph in area.get("placeholders", []):
#                         if ph.get("position") == "front":
#                             print_price += ph.get("price", 0)
#                 return base_price + print_price
#         return 0
#
#     def create_product(self, image_id, title, description, tags, variant_ids, price,
#                        blueprint_id=None, print_provider_id=None):
#         blueprint_id = blueprint_id or self.default_blueprint
#         print_provider_id = print_provider_id or self.default_provider
#         url = f"{self.base_url}/shops/{self.shop_id}/products.json"
#
#         image_placement = {
#             "id": image_id,
#             "x": 0.5,
#             "y": 0.5,
#             "scale": 1.0,
#             "angle": 0
#         }
#
#         payload = {
#             "title": title,
#             "description": description,
#             "tags": tags,
#             "blueprint_id": blueprint_id,
#             "print_provider_id": print_provider_id,
#             "variants": [{"id": vid, "price": price, "is_enabled": True} for vid in variant_ids],
#             "print_areas": [
#                 {
#                     "variant_ids": variant_ids,
#                     "placeholders": [
#                         {
#                             "position": "front",
#                             "images": [image_placement]
#                         }
#                     ]
#                 }
#             ]
#         }
#
#         response = requests.post(url, headers=self.headers, json=payload)
#         if not response.ok:
#             # Debug logging on failure
#             import json
#             print("❌ create_product payload:")
#             print(json.dumps(payload, indent=2))
#             print(f"❌ create_product response: {response.status_code} {response.text}")
#         response.raise_for_status()
#         return response.json()
#
#
#     def publish_product(self, product_id, publish_to_store=True):
#         url = f"{self.base_url}/shops/{self.shop_id}/products/{product_id}/publish.json"
#         payload = {
#             "title": True, "description": True, "images": True,
#             "variants": True, "tags": True, "keyFeatures": True,
#             "shipping_template": True
#         }
#         if not publish_to_store:
#             payload["sales_channel"] = "printify"
#         res = requests.post(url, headers=self.headers, json=payload)
#         res.raise_for_status()
#         return res.json()
#
#     def get_shopify_url(self, product_id):
#         url = f"{self.base_url}/shops/{self.shop_id}/products/{product_id}.json"
#         res = requests.get(url, headers=self.headers)
#         res.raise_for_status()
#         data = res.json()
#         if not isinstance(data, dict):
#             return ""
#         handle = data.get("external", {}).get("handle")
#         return f"https://{self.shopify_domain}/products/{handle}" if handle else ""
#
#     def process_csv(self, csv_path, image_dir):
#         df = pd.read_csv(csv_path)
#         for idx, row in df.iterrows():
#             try:
#                 # upload image
#                 img_path = os.path.join(image_dir, row['local_path'])
#                 if not os.path.exists(img_path):
#                     raise FileNotFoundError(f"Image not found: {img_path}")
#                 img_id = self.upload_image(img_path, row['file_name'])
#
#                 # parse tags
#                 try:
#                     tags = ast.literal_eval(row.get('tags', '[]'))
#                     if not isinstance(tags, list):
#                         tags = []
#                 except Exception:
#                     tags = []
#
#                 # define variant IDs
#                 variants = [17643, 17644, 17645, 17646, 17647]  # White Gildan Softstyle S–2XL
#
#                 # get cost and set price
#                 costs = []
#                 for vid in variants:
#                     try:
#                         cost = self.get_total_variant_cost(5, 99, vid)
#                         if cost > 0:
#                             costs.append(cost)
#                     except Exception as e:
#                         print(f"[⚠️] Variant {vid} cost error: {e}")
#                 if costs:
#                     max_cost = max(costs)
#                     retail = max(int(max_cost * 1.6), 1999)
#                 else:
#                     max_cost = 0
#                     retail = self.default_price
#                     print(f"[⚠️] No valid cost data. Fallback to retail = {retail}p")
#
#                 # create & publish
#                 prod = self.create_product(
#                     image_id=img_id,
#                     title=row.get('title', 'T-Shirt'),
#                     description=row.get('description', ''),
#                     tags=tags,
#                     variant_ids=variants,
#                     price=retail,
#                     blueprint_id=5,
#                     print_provider_id=99
#                 )
#                 self.publish_product(prod['id'])
#                 shop_url = self.get_shopify_url(prod['id'])
#
#                 # update DataFrame
#                 df.at[idx, 'printify_product_id'] = prod['id']
#                 df.at[idx, 'retail_price'] = retail / 100
#                 df.at[idx, 'base_cost_pence'] = max_cost
#                 df.at[idx, 'profit_estimate'] = (retail - max_cost) / 100
#                 df.at[idx, 'shopify_url'] = shop_url
#                 df.at[idx, 'twitter_url'] = ''
#                 df.at[idx, 'bluesky_url'] = ''
#                 df.at[idx, 'instagram_url'] = ''
#                 df.at[idx, 'error'] = ''
#                 print(f"[✅] Row {idx + 1}: Created & published ({shop_url})")
#
#             except Exception as e:
#                 df.at[idx, 'error'] = str(e)
#                 print(f"[❌] Row {idx + 1}: {e}")
#
#         df.to_csv(csv_path, index=False)
#         print(f"✅ CSV updated: {csv_path}")


# import requests
# import base64
# import pandas as pd
# import os
#
# class PrintifyUploader:
#     def __init__(self, access_token, shop_id, default_blueprint=9, default_provider=5, default_variant=17887, default_price=1999):
#         self.access_token = access_token
#         self.shop_id = shop_id
#         self.base_url = "https://api.printify.com/v1"
#         self.headers = {
#             "Authorization": f"Bearer {self.access_token}",
#             "Content-Type": "application/json"
#         }
#         self.default_blueprint = default_blueprint
#         self.default_provider = default_provider
#         self.default_variant = default_variant
#         self.default_price = default_price
#
#     def upload_image(self, image_path, file_name):
#         """Upload an image to Printify and return its ID."""
#         upload_url = f"{self.base_url}/uploads/images.json"
#         with open(image_path, "rb") as img_file:
#             img_b64 = base64.b64encode(img_file.read()).decode('utf-8')
#         payload = {
#             "file_name": file_name,
#             "contents": img_b64
#         }
#         response = requests.post(upload_url, headers=self.headers, json=payload)
#         response.raise_for_status()
#         return response.json()["id"]
#
#     def create_product(self, image_id, title, description, tags, variant_ids, price, blueprint_id=None,
#                        print_provider_id=None):
#         blueprint_id = blueprint_id or self.default_blueprint
#         print_provider_id = print_provider_id or self.default_provider
#
#         product_url = f"{self.base_url}/shops/{self.shop_id}/products.json"
#
#         # Shared image placement parameters
#         image_placement = {
#             "id": image_id,
#             "x": 0.5,  # centered horizontally
#             "y": 0.5,  # centered vertically
#             "scale": 1.0,  # full scale
#             "angle": 0
#         }
#
#         payload = {
#             "title": title,
#             "description": description,
#             "tags": tags,
#             "blueprint_id": blueprint_id,
#             "print_provider_id": print_provider_id,
#             "variants": [
#                 {"id": vid, "price": price, "is_enabled": True} for vid in variant_ids
#             ],
#             "print_areas": [
#                 {
#                     "variant_ids": variant_ids,
#                     "placeholders": [
#                         {
#                             "position": "front",
#                             "images": [image_placement]
#                         }
#                     ]
#                 }
#             ]
#         }
#
#         try:
#             response = requests.post(product_url, headers=self.headers, json=payload)
#             response.raise_for_status()
#             return response.json()
#         except requests.exceptions.HTTPError as e:
#             print("Printify API response:", response.text)
#             raise e
#
#     def publish_product(self, product_id, publish_to_store=True):
#         """Publish a product to Printify storefront or Shopify."""
#         url = f"{self.base_url}/shops/{self.shop_id}/products/{product_id}/publish.json"
#         payload = {
#             "title": True,
#             "description": True,
#             "images": True,
#             "variants": True,
#             "tags": True,
#             "keyFeatures": True,
#             "shipping_template": True
#         }
#
#         if not publish_to_store:
#             payload["sales_channel"] = "printify"
#
#         res = requests.post(url, headers=self.headers, json=payload)
#         res.raise_for_status()
#         return res.json()
#
#
#     def process_csv(self, csv_path, image_dir):
#         """Process a CSV file and create Printify products from it."""
#         df = pd.read_csv(csv_path)
#         for idx, row in df.iterrows():
#             try:
#                 # Build absolute image path
#                 image_path = os.path.join(image_dir, row['local_path'])
#                 if not os.path.exists(image_path):
#                     raise FileNotFoundError(f"Image not found: {image_path}")
#
#                 image_id = self.upload_image(image_path, row['file_name'])
#
#                 # Optional fields with defaults
#                 tags = row['tags'].split(',') if isinstance(row['tags'], str) else []
#                 price = int(row['price']) if 'price' in row and pd.notna(row['price']) else self.default_price
#                 variant_id = int(row['variant_id']) if 'variant_id' in row and pd.notna(row['variant_id']) else self.default_variant
#                 blueprint_id = int(row['blueprint_id']) if 'blueprint_id' in row and pd.notna(row['blueprint_id']) else self.default_blueprint
#
#                 product = self.create_product(
#                     image_id=image_id,
#                     title="Test Shirt",
#                     description="Centered design, full scale.",
#                     tags=["custom", "white", "tshirt"],
#                     variant_ids=[17643, 17644, 17645, 17646, 17647],  # S, M, L, XL, 2XL
#                     price=1999,
#                     blueprint_id=5,
#                     print_provider_id=99
#                 )
#
#                 # ⬇️ Publish it to Shopify
#                 self.publish_product(product["id"])
#                 # product = self.create_product(
#                 #     image_id=image_id,
#                 #     title=row['title'],
#                 #     description=row['description'],
#                 #     tags=tags,
#                 #     variant_id=variant_id,
#                 #     price=price,
#                 #     blueprint_id=blueprint_id
#                 # )
#
#                 print(f"[✅] Row {idx + 1}: Product created (ID: {product.get('id')})")
#
#             except Exception as e:
#                 print(f"[❌] Row {idx + 1}: Failed to create product - {e}")
#
