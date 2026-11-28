"""Tests for safe request validation in URL-based market-data adapters."""

from __future__ import annotations

import pytest
from market_data.adapters.giarevn import GiarevnAstroAdapter
from market_data.adapters.lazada import LazadaDirectPdpAdapter
from market_data.adapters.retail_html import RetailHtmlAdapter


@pytest.mark.parametrize(
    ("adapter", "kwargs"),
    [
        (LazadaDirectPdpAdapter(min_delay=0, max_delay=0), {"url": "https://lazada.vn.evil.example/pdp"}),
        (LazadaDirectPdpAdapter(min_delay=0, max_delay=0), {"url": "http://www.lazada.vn/pdp"}),
        (RetailHtmlAdapter(min_delay=0, max_delay=0), {"url": "http://cellphones.com.vn/product"}),
        (RetailHtmlAdapter(min_delay=0, max_delay=0), {"url": "https://cellphones.com.vn:8443/product"}),
        (GiarevnAstroAdapter(min_delay=0, max_delay=0), {"product_url": "https://giarevn.com.evil.example/product"}),
    ],
)
def test_url_adapters_reject_unapproved_targets(adapter, kwargs) -> None:
    with pytest.raises(ValueError):
        adapter.fetch(**kwargs)
    adapter.session.close()


def test_url_adapters_do_not_follow_product_page_redirects(monkeypatch) -> None:
    class RedirectResponse:
        is_redirect = True

    adapter = RetailHtmlAdapter(min_delay=0, max_delay=0)
    monkeypatch.setattr(adapter, "request", lambda *args, **kwargs: RedirectResponse())
    try:
        with pytest.raises(ValueError, match="chuyển hướng"):
            adapter.fetch(url="https://cellphones.com.vn/product")
    finally:
        adapter.session.close()
