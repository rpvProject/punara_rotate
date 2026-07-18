"""Transports.

Synthetic transports page the raw_records the seeder already landed — the
REAL SyncRunner and mappers run unmodified over them, so swapping in a live
HTTP transport later changes nothing downstream.

Http*Transport classes show the live wiring (auth headers, endpoints, cursor
params). They are UNTESTED-against-live: v0 never dials out (127.0.0.1 only).
"""

from __future__ import annotations

from typing import Mapping
from urllib.parse import parse_qs, urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import RawRecord
from . import gorgias, interakt, judgeme, klaviyo, shopify


class _SyntheticTransport:
    """Serves raw_records pages ordered by row id; cursor = last served row id."""

    resource_source: Mapping[str, str] = {}

    def __init__(self, session: Session, tenant_id: int, page_size: int = 500) -> None:
        self._session = session
        self._tenant_id = tenant_id
        self._page_size = page_size

    def fetch_page(self, resource: str, cursor: str | None) -> tuple[list[dict], str | None]:
        after = int(cursor) if cursor else 0
        rows = self._session.execute(
            select(RawRecord.id, RawRecord.payload)
            .where(
                RawRecord.tenant_id == self._tenant_id,
                RawRecord.source == self.resource_source[resource],
                RawRecord.resource == resource,
                RawRecord.id > after,
            )
            .order_by(RawRecord.id)
            .limit(self._page_size)
        ).all()
        if not rows:
            return [], cursor
        return [payload for _id, payload in rows], str(rows[-1][0])


class SyntheticShopifyTransport(_SyntheticTransport):
    resource_source = shopify.RESOURCE_SOURCE


class SyntheticKlaviyoTransport(_SyntheticTransport):
    resource_source = klaviyo.RESOURCE_SOURCE


class SyntheticInteraktTransport(_SyntheticTransport):
    resource_source = interakt.RESOURCE_SOURCE


class SyntheticGorgiasTransport(_SyntheticTransport):
    resource_source = gorgias.RESOURCE_SOURCE


class SyntheticJudgemeTransport(_SyntheticTransport):
    resource_source = judgeme.RESOURCE_SOURCE


TRANSPORTS: dict[str, type[_SyntheticTransport]] = {
    "shopify": SyntheticShopifyTransport,
    "klaviyo": SyntheticKlaviyoTransport,
    "interakt": SyntheticInteraktTransport,
    "gorgias": SyntheticGorgiasTransport,
    "judgeme": SyntheticJudgemeTransport,
}


class HttpShopifyTransport:
    """Shopify Admin REST transport — UNTESTED-against-live (v0 never dials out).

    Auth: ``X-Shopify-Access-Token`` header (Admin API access token).
    Endpoints: ``GET https://{shop}/admin/api/{ver}/{resource}.json?limit=250``.
    Cursor: ``page_info`` from the ``Link rel="next"`` response header. Shopify
    forbids combining ``page_info`` with other filters, so a live incremental
    sync would seed the FIRST page with ``updated_at_min`` from sync_state and
    then follow page_info links (not implemented here).

    ``payments``/``shipments`` are Razorpay/Shiprocket resources, not Shopify —
    live ingestion needs their own transports (Phase 2).
    """

    API_VERSION = "2024-10"
    _PATHS = {"customers": "/customers.json", "products": "/products.json", "orders": "/orders.json"}

    def __init__(self, shop_domain: str, access_token: str, page_size: int = 250) -> None:
        import httpx

        self._page_size = page_size
        self._client = httpx.Client(
            base_url=f"https://{shop_domain}/admin/api/{self.API_VERSION}",
            headers={"X-Shopify-Access-Token": access_token, "Accept": "application/json"},
        )

    def fetch_page(self, resource: str, cursor: str | None) -> tuple[list[dict], str | None]:
        if resource not in self._PATHS:
            raise NotImplementedError(
                f"{resource!r} is not a Shopify resource; Razorpay/Shiprocket HTTP "
                "transports are Phase 2"
            )
        params: dict = {"limit": self._page_size}
        if cursor:
            params["page_info"] = cursor
        elif resource == "orders":
            params["status"] = "any"  # only legal on the first (filterable) page
        response = self._client.get(self._PATHS[resource], params=params)
        response.raise_for_status()
        records = response.json().get(resource, [])
        next_url = (response.links.get("next") or {}).get("url")
        next_cursor = (
            parse_qs(urlparse(next_url).query).get("page_info", [None])[0] if next_url else None
        )
        return records, next_cursor


class HttpKlaviyoTransport:
    """Klaviyo API transport — UNTESTED-against-live (v0 never dials out).

    Auth: ``Authorization: Klaviyo-API-Key {private_key}`` plus the pinned
    ``revision`` header. Endpoints: ``GET https://a.klaviyo.com/api/campaigns``,
    ``/profiles`` (consent), ``/events`` (message engagement).
    Cursor: ``page[cursor]`` query param; the next cursor comes from
    ``body.links.next``.

    NOTE: live payloads are JSON:API-shaped, NOT the flattened v0 shapes the
    klaviyo mappers consume — going live requires a reshaping layer between
    this transport and the mappers (Phase 2).
    """

    REVISION = "2024-10-15"
    _PATHS = {"campaigns": "/campaigns", "consent": "/profiles", "messages": "/events"}

    def __init__(self, api_key: str, page_size: int = 100) -> None:
        import httpx

        self._page_size = page_size
        self._client = httpx.Client(
            base_url="https://a.klaviyo.com/api",
            headers={
                "Authorization": f"Klaviyo-API-Key {api_key}",
                "revision": self.REVISION,
                "Accept": "application/json",
            },
        )

    def fetch_page(self, resource: str, cursor: str | None) -> tuple[list[dict], str | None]:
        params: dict = {"page[size]": self._page_size}
        if cursor:
            params["page[cursor]"] = cursor
        response = self._client.get(self._PATHS[resource], params=params)
        response.raise_for_status()
        body = response.json()
        next_url = (body.get("links") or {}).get("next")
        next_cursor = (
            parse_qs(urlparse(next_url).query).get("page[cursor]", [None])[0] if next_url else None
        )
        return body.get("data", []), next_cursor


class HttpInteraktTransport:
    """Interakt public API transport — UNTESTED-against-live (never dials out here).

    Auth: ``Authorization: Basic {api_key}`` — Interakt issues the API key
    already base64-encoded; it goes in the Basic scheme verbatim (NOT
    user:pass). Base: ``https://api.interakt.ai/v1/public``. Cursor: integer
    offset (``offset``/``limit`` params).

    NOTE: live payloads (campaign objects, message logs, user opt-in
    attributes) are NOT the flattened v2 shapes the interakt mappers consume —
    going live needs a reshaping layer between this transport and the mappers
    (same caveat as HttpKlaviyoTransport).
    """

    _PATHS = {"campaigns": "/campaigns/", "messages": "/message-logs/", "consent": "/users/"}

    def __init__(self, api_key: str, page_size: int = 100) -> None:
        import httpx

        self._page_size = page_size
        self._client = httpx.Client(
            base_url="https://api.interakt.ai/v1/public",
            headers={"Authorization": f"Basic {api_key}", "Accept": "application/json"},
        )

    def fetch_page(self, resource: str, cursor: str | None) -> tuple[list[dict], str | None]:
        offset = int(cursor) if cursor else 0
        response = self._client.get(
            self._PATHS[resource], params={"offset": offset, "limit": self._page_size}
        )
        response.raise_for_status()
        records = response.json().get("results", [])
        next_cursor = str(offset + len(records)) if len(records) == self._page_size else None
        return records, next_cursor


class HttpGorgiasTransport:
    """Gorgias REST transport — UNTESTED-against-live (never dials out here).

    Auth: HTTP Basic — account email as username, REST API key as password.
    Endpoint: ``GET https://{subdomain}.gorgias.com/api/tickets?limit=100``.
    Cursor: ``cursor`` query param; the next cursor comes from
    ``body.meta.next_cursor`` (null on the last page).

    NOTE: live ticket objects need reshaping to the flattened v2 shape
    (e.g. ``created_datetime``/``closed_datetime`` are dual-read by the
    mapper, but customer/satisfaction blocks differ).
    """

    def __init__(self, subdomain: str, email: str, api_key: str, page_size: int = 100) -> None:
        import httpx

        self._page_size = page_size
        self._client = httpx.Client(
            base_url=f"https://{subdomain}.gorgias.com/api",
            auth=(email, api_key),
            headers={"Accept": "application/json"},
        )

    def fetch_page(self, resource: str, cursor: str | None) -> tuple[list[dict], str | None]:
        params: dict = {"limit": self._page_size}
        if cursor:
            params["cursor"] = cursor
        response = self._client.get("/tickets", params=params)
        response.raise_for_status()
        body = response.json()
        return body.get("data", []), (body.get("meta") or {}).get("next_cursor")


class HttpJudgemeTransport:
    """Judge.me REST transport — UNTESTED-against-live (never dials out here).

    Auth: private token as the ``api_token`` query param plus ``shop_domain``.
    Endpoint: ``GET https://judge.me/api/v1/reviews?page=N&per_page=100``.
    Cursor: 1-based page number (Judge.me has no opaque cursor).

    NOTE: live review objects need reshaping (``reviewer`` block differs,
    ``verified`` is a string — the mapper already dual-reads that).
    """

    def __init__(self, shop_domain: str, api_token: str, page_size: int = 100) -> None:
        import httpx

        self._shop_domain = shop_domain
        self._api_token = api_token
        self._page_size = page_size
        self._client = httpx.Client(
            base_url="https://judge.me/api/v1", headers={"Accept": "application/json"}
        )

    def fetch_page(self, resource: str, cursor: str | None) -> tuple[list[dict], str | None]:
        page = int(cursor) if cursor else 1
        response = self._client.get(
            "/reviews",
            params={
                "api_token": self._api_token,
                "shop_domain": self._shop_domain,
                "page": page,
                "per_page": self._page_size,
            },
        )
        response.raise_for_status()
        records = response.json().get("reviews", [])
        next_cursor = str(page + 1) if len(records) == self._page_size else None
        return records, next_cursor
