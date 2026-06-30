"""
bluesky_client.py
-----------------
All Bluesky API interactions: login, posting, replying, searching, following.
"""

import os
import requests
import time
from datetime import datetime, timezone

BLUESKY_HANDLE = os.environ.get("BLUESKY_HANDLE", "")
BLUESKY_PASSWORD = os.environ.get("BLUESKY_APP_PASSWORD", "")
BASE_URL = "https://bsky.social/xrpc"


class BlueskyClient:

    def __init__(self):
        self.token = None
        self.did = None
        self.logged_in = False

    def login(self) -> bool:
        try:
            resp = requests.post(
                f"{BASE_URL}/com.atproto.server.createSession",
                json={"identifier": BLUESKY_HANDLE, "password": BLUESKY_PASSWORD},
                timeout=15,
            )
            if resp.status_code == 200:
                data = resp.json()
                self.token = data["accessJwt"]
                self.did = data["did"]
                self.logged_in = True
                print("Logged in to Bluesky")
                return True
            print(f"Bluesky login failed: {resp.status_code} {resp.text}")
        except Exception as e:
            print(f"Bluesky login error: {e}")
        return False

    def _headers(self):
        return {"Authorization": f"Bearer {self.token}"}

    def post(self, text: str):
        if not self.logged_in:
            return None
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        record = {"$type": "app.bsky.feed.post", "text": text[:300], "createdAt": now}
        try:
            resp = requests.post(
                f"{BASE_URL}/com.atproto.repo.createRecord",
                headers=self._headers(),
                json={"repo": self.did, "collection": "app.bsky.feed.post", "record": record},
                timeout=15,
            )
            if resp.status_code == 200:
                print(f"Posted: {text[:70]}...")
                return resp.json()
            print(f"Post failed: {resp.status_code} {resp.text}")
        except Exception as e:
            print(f"Post error: {e}")
        return None

    def reply(self, text: str, parent_uri: str, parent_cid: str, root_uri=None, root_cid=None):
        if not self.logged_in:
            return None
        root_uri = root_uri or parent_uri
        root_cid = root_cid or parent_cid
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        record = {
            "$type": "app.bsky.feed.post",
            "text": text[:300],
            "createdAt": now,
            "reply": {
                "root": {"uri": root_uri, "cid": root_cid},
                "parent": {"uri": parent_uri, "cid": parent_cid},
            },
        }
        try:
            resp = requests.post(
                f"{BASE_URL}/com.atproto.repo.createRecord",
                headers=self._headers(),
                json={"repo": self.did, "collection": "app.bsky.feed.post", "record": record},
                timeout=15,
            )
            if resp.status_code == 200:
                print(f"Replied: {text[:70]}...")
                return resp.json()
            print(f"Reply failed: {resp.status_code} {resp.text}")
        except Exception as e:
            print(f"Reply error: {e}")
        return None

    def search_posts(self, query: str, limit: int = 25):
        try:
            resp = requests.get(
                f"{BASE_URL}/app.bsky.feed.searchPosts",
                headers=self._headers(),
                params={"q": query, "limit": limit},
                timeout=15,
            )
            if resp.status_code == 200:
                return resp.json().get("posts", [])
            print(f"Search failed: {resp.status_code}")
        except Exception as e:
            print(f"Search error: {e}")
        return []

    def get_trending_posts(self, limit: int = 15):
        queries = ["semiconductor geopolitics", "tech war China", "supply chain trade"]
        all_posts = []
        for q in queries:
            posts = self.search_posts(q, limit=8)
            all_posts.extend(posts)
            time.sleep(0.5)

        seen = set()
        unique = []
        for p in all_posts:
            uri = p.get("uri", "")
            if uri not in seen:
                seen.add(uri)
                unique.append(p)
        return unique[:limit]

    def follow(self, subject_did: str) -> bool:
        if not self.logged_in:
            return False
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        try:
            resp = requests.post(
                f"{BASE_URL}/com.atproto.repo.createRecord",
                headers=self._headers(),
                json={
                    "repo": self.did,
                    "collection": "app.bsky.graph.follow",
                    "record": {"$type": "app.bsky.graph.follow", "subject": subject_did, "createdAt": now},
                },
                timeout=15,
            )
            return resp.status_code == 200
        except Exception as e:
            print(f"Follow error: {e}")
        return False

    def already_following(self, subject_did: str) -> bool:
        try:
            resp = requests.get(
                f"{BASE_URL}/app.bsky.graph.getRelationships",
                headers=self._headers(),
                params={"actor": self.did, "others": [subject_did]},
                timeout=10,
            )
            if resp.status_code == 200:
                rels = resp.json().get("relationships", [])
                for r in rels:
                    if r.get("did") == subject_did:
                        return bool(r.get("following"))
        except Exception:
            pass
        return False

    def find_and_follow_relevant_accounts(self, posts, max_follows: int = 3) -> int:
        followed = 0
        seen_dids = set()
        for post in posts:
            if followed >= max_follows:
                break
            author = post.get("author", {})
            author_did = author.get("did", "")
            text = post.get("record", {}).get("text", "")
            if not author_did or author_did in seen_dids or author_did == self.did:
                continue
            seen_dids.add(author_did)
            if len(text) < 80:
                continue
            if not self.already_following(author_did):
                if self.follow(author_did):
                    handle = author.get("handle", author_did)
                    print(f"Followed @{handle}")
                    followed += 1
                    time.sleep(1)
        return followed
