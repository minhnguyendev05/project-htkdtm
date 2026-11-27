"""Competitor-price and crawler API schemas."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from urllib.parse import urlparse
from uuid import UUID

from pydantic import ConfigDict, Field, field_validator, model_validator

from app.schemas.common import ApiModel

AdapterName = Literal["giarevn", "lazada", "price_history", "retail_html", "tiki"]

_RETAIL_HOSTS = {
    "websosanh.vn",
    "www.websosanh.vn",
    "cellphones.com.vn",
    "www.cellphones.com.vn",
    "memoryzone.com.vn",
    "www.memoryzone.com.vn",
}


def _validate_https_host(value: str, allowed_host: str) -> str:
    parsed = urlparse(value)
    if (
        parsed.scheme != "https"
        or parsed.hostname != allowed_host
        or parsed.port not in (None, 443)
    ):
        raise ValueError(f"URL phải dùng HTTPS và thuộc {allowed_host}.")
    if parsed.username or parsed.password:
        raise ValueError("URL không được chứa thông tin xác thực.")
    return value


def _validate_allowed_url(value: str, hosts: set[str]) -> str:
    parsed = urlparse(value)
    host = (parsed.hostname or "").lower()
    if (
        parsed.scheme != "https"
        or host not in hosts
        or parsed.port not in (None, 443)
        or parsed.username
        or parsed.password
    ):
        raise ValueError("URL phải dùng HTTPS và thuộc một domain crawler được cho phép.")
    return value


class CrawlerRunCreate(ApiModel):
    """Validated request for an allow-listed market-data adapter."""

    model_config = ConfigDict(extra="forbid")

    adapter_name: AdapterName
    keyword: str | None = Field(default=None, min_length=1, max_length=120)
    limit: int = Field(default=20, ge=1, le=100)
    url: str | None = Field(default=None, max_length=500)
    product_url: str | None = Field(default=None, max_length=500)
    product_id: str | None = Field(default=None, min_length=1, max_length=120)
    sku_code: str | None = Field(default=None, min_length=1, max_length=64)

    @field_validator("keyword", "product_id", "sku_code")
    @classmethod
    def _strip_non_empty_values(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Giá trị không được để trống.")
        return cleaned

    @model_validator(mode="after")
    def _validate_adapter_arguments(self) -> CrawlerRunCreate:
        if self.adapter_name == "tiki":
            if not self.keyword or self.url or self.product_url or self.product_id:
                raise ValueError("Adapter Tiki yêu cầu keyword và không nhận URL/productId.")
        elif self.adapter_name == "lazada":
            if not self.url or self.keyword or self.product_url or self.product_id:
                raise ValueError("Adapter Lazada yêu cầu url PDP và không nhận keyword/productId.")
            _validate_allowed_url(self.url, {"lazada.vn", "www.lazada.vn"})
        elif self.adapter_name == "retail_html":
            if not self.url or self.keyword or self.product_url or self.product_id:
                raise ValueError("Adapter retail_html yêu cầu url và không nhận keyword/productId.")
            _validate_allowed_url(self.url, _RETAIL_HOSTS)
        elif self.adapter_name == "giarevn":
            if not self.product_url or self.url or self.keyword or self.product_id:
                raise ValueError(
                    "Adapter Giarevn yêu cầu productUrl; không nhận url/keyword/productId."
                )
            _validate_https_host(self.product_url, "giarevn.com")
        elif self.adapter_name == "price_history" and (
            not self.product_id or self.url or self.product_url or self.keyword
        ):
            raise ValueError(
                "Adapter price_history yêu cầu productId; không nhận url/keyword."
            )
        return self

    def fetch_kwargs(self) -> dict[str, str | int]:
        if self.adapter_name == "tiki":
            return {"keyword": self.keyword or "", "limit": self.limit}
        if self.adapter_name in {"lazada", "retail_html"}:
            return {"url": self.url or ""}
        if self.adapter_name == "giarevn":
            return {"product_url": self.product_url or ""}
        return {"product_id": self.product_id or ""}


class CrawlerRunRead(ApiModel):
    """Acknowledgement for a queued background crawler task."""

    task_id: str
    adapter_name: AdapterName
    status: Literal["QUEUED"] = "QUEUED"


class CompetitorPriceRead(ApiModel):
    """Canonical competitor listing from the shared 18-table schema."""

    id: UUID
    product_id: UUID | None
    sku_code: str | None
    product_name: str
    competitor_name: str
    marketplace_code: str
    source_type: str
    source_name: str
    source_url: str | None
    external_item_id: str | None
    raw_title: str | None
    extracted_model_code: str | None
    listed_price: Decimal
    effective_price: Decimal | None
    sold_count: int | None
    rating: Decimal | None
    confidence: Decimal
    match_status: str
    verdict: str | None
    fake_sale_warning: bool
    is_outlier: bool
    observed_at: datetime


class CompetitorPriceHistoryRead(ApiModel):
    """Daily price observation related to a canonical competitor listing."""

    id: UUID
    competitor_price_id: UUID
    recorded_date: date
    price: Decimal
    created_at: datetime
