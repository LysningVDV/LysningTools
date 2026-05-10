from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlencode

import requests

from .io_utils import ensure_dir, utc_now_iso


@dataclass
class FetchResult:
    url: str
    status_code: int
    from_cache: bool
    retrieved_at: str
    path_text: Path
    path_meta: Path


def _sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _canonical_cache_key(url: str, method: str, params: Optional[Dict[str, Any]], data: Optional[Dict[str, Any]]) -> str:
    """
    Build a deterministic cache key based on:
      - HTTP method
      - URL
      - sorted params
      - sorted body (data)
    """
    parts = [method.upper(), url]
    if params:
        parts.append("PARAMS:" + urlencode(sorted((str(k), str(v)) for k, v in params.items())))
    if data:
        parts.append("DATA:" + urlencode(sorted((str(k), str(v)) for k, v in data.items())))
    return " | ".join(parts)


class HTTPCache:
    """
    Tiny filesystem cache for polite, resumable scraping.

    Stores:
      cache/<sha>.txt   (response text)
      cache/<sha>.json  (metadata)
    """

    def __init__(
        self,
        cache_dir: Path,
        user_agent: str = "LysningCASPublicIngest/0.1 (+contact: you@example.com)",
        timeout_s: int = 30,
        sleep_s: float = 1.0,
        retries: int = 3,
    ) -> None:
        self.cache_dir = ensure_dir(cache_dir)
        self.timeout_s = timeout_s
        self.sleep_s = sleep_s
        self.retries = retries
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": user_agent,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en;q=0.9",
            }
        )

    def _paths_for_key(self, key: str) -> Tuple[Path, Path]:
        h = _sha256(key)
        return self.cache_dir / f"{h}.txt", self.cache_dir / f"{h}.json"

    def request(
        self,
        method: str,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
        force: bool = False,
        headers: Optional[Dict[str, str]] = None,
    ) -> FetchResult:
        key = _canonical_cache_key(url, method=method, params=params, data=data)
        p_text, p_meta = self._paths_for_key(key)

        if (not force) and p_text.exists() and p_meta.exists():
            meta = json.loads(p_meta.read_text(encoding="utf-8"))
            return FetchResult(
                url=url,
                status_code=int(meta.get("status_code", 200)),
                from_cache=True,
                retrieved_at=str(meta.get("retrieved_at", "")),
                path_text=p_text,
                path_meta=p_meta,
            )

        last_exc: Optional[Exception] = None
        for attempt in range(1, self.retries + 1):
            try:
                req_headers = {}
                if headers:
                    req_headers.update(headers)

                r = self.session.request(
                    method=method.upper(),
                    url=url,
                    params=params,
                    data=data,
                    headers=req_headers if req_headers else None,
                    timeout=self.timeout_s,
                )
                retrieved_at = utc_now_iso()
                p_text.write_text(r.text, encoding="utf-8")
                p_meta.write_text(
                    json.dumps(
                        {
                            "cache_key": key,
                            "method": method.upper(),
                            "url": url,
                            "params": params or {},
                            "data": data or {},
                            "status_code": r.status_code,
                            "retrieved_at": retrieved_at,
                            "final_url": str(r.url),
                        },
                        ensure_ascii=False,
                        indent=2,
                    ),
                    encoding="utf-8",
                )
                time.sleep(self.sleep_s)
                return FetchResult(
                    url=url,
                    status_code=r.status_code,
                    from_cache=False,
                    retrieved_at=retrieved_at,
                    path_text=p_text,
                    path_meta=p_meta,
                )
            except Exception as e:
                last_exc = e
                time.sleep(self.sleep_s * attempt)

        raise RuntimeError(f"Failed {method.upper()} {url} after {self.retries} retries: {last_exc!r}")

    def get(self, url: str, params: Optional[Dict[str, Any]] = None, force: bool = False) -> FetchResult:
        return self.request("GET", url, params=params, force=force)

    def post(self, url: str, data: Optional[Dict[str, Any]] = None, force: bool = False, headers: Optional[Dict[str, str]] = None) -> FetchResult:
        return self.request("POST", url, data=data, force=force, headers=headers)