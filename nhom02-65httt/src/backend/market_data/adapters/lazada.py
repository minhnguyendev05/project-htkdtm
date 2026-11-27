from __future__ import annotations

import json
from urllib.parse import urlparse

import pandas as pd
from bs4 import BeautifulSoup

from .base import CompetitorSourceAdapter


class LazadaDirectPdpAdapter(CompetitorSourceAdapter):
    marketplace = "LAZADA"

    def fetch(self, url: str, **kwargs) -> pd.DataFrame:
        parsed_url = urlparse(url or "")
        host = (parsed_url.hostname or "").lower()
        if (
            parsed_url.scheme != "https"
            or not (host == "lazada.vn" or host.endswith(".lazada.vn"))
            or parsed_url.port not in (None, 443)
            or parsed_url.username
            or parsed_url.password
        ):
            raise ValueError("Chỉ chấp nhận URL PDP thuộc Lazada")
        response = self.request(url, allow_redirects=False)
        if response.is_redirect:
            raise ValueError("URL Lazada chuyển hướng; hãy cung cấp URL PDP chính tắc.")
        html = response.text
        soup = BeautifulSoup(html, "html.parser")
        rows = []
        # Prefer structured JSON-LD Product/Offer; page-specific embedded state is volatile.
        for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
            try: obj = json.loads(script.string or script.get_text())
            except (json.JSONDecodeError, TypeError): continue
            objs = obj if isinstance(obj, list) else [obj]
            for p in objs:
                if not isinstance(p, dict) or "Product" not in str(p.get("@type", "")): continue
                offer = p.get("offers", {})
                if isinstance(offer, list): offer = offer[0] if offer else {}
                if not isinstance(offer, dict) or not offer.get("price"): continue
                rows.append(self.record(marketplace="LAZADA", category="", product_id=str(p.get("sku") or p.get("mpn") or url),
                    title=p.get("name", ""), brand=(p.get("brand", {}) or {}).get("name", "") if isinstance(p.get("brand"), dict) else p.get("brand", ""),
                    price_vnd=float(offer["price"]), original_price_vnd=None, url=p.get("url", url), confidence=0.7))
        return pd.DataFrame(rows)
