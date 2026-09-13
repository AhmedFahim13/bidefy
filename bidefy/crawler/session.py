"""HTTP session against eprocure.gov.bd with a cookie, a rate limiter and an injectable transport."""
from __future__ import annotations

import http.cookiejar
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Callable

BASE = "https://www.eprocure.gov.bd"
UA = "Mozilla/5.0 bidefy-crawler/0.1 (+https://github.com/AhmedFahim13/bidefy; polite, 1 req/s)"
WARMUP_PATH = "/resources/common/StdTenderSearch.jsp?h=t"
ENDPOINTS = {
    "tenders": ("/TenderDetailsServlet", lambda page, size: {
        "funName": "AllTenders", "keyword": "", "pageNo": str(page), "size": str(size),
        "homeWSearch": "homeWSearch", "approve": "false", "h": "t"}),
    "contracts": ("/SearchNoaServlet", lambda page, size: {
        "keyword": "", "pageNo": str(page), "size": str(size)}),
}
DETAIL_PATH = "/resources/common/ViewTender.jsp"

Transport = Callable[[str, str, dict | None, dict], tuple[int, str]]


class SessionExpired(RuntimeError):
    pass


class HttpFailure(RuntimeError):
    pass


class RateLimiter:
    def __init__(self, min_interval: float = 1.0, now=time.monotonic, sleep=time.sleep) -> None:
        self.min_interval = min_interval
        self._now = now
        self._sleep = sleep
        self._last: float | None = None

    def wait(self) -> None:
        if self._last is not None:
            remaining = self.min_interval - (self._now() - self._last)
            if remaining > 0:
                self._sleep(round(remaining, 6))
        self._last = self._now()


def urllib_transport(timeout: float = 60.0) -> Transport:
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))

    def send(method: str, url: str, data: dict | None, headers: dict) -> tuple[int, str]:
        body = urllib.parse.urlencode(data).encode() if data is not None else None
        req = urllib.request.Request(url, data=body, method=method, headers=headers)
        try:
            with opener.open(req, timeout=timeout) as resp:
                return resp.status, resp.read().decode("utf-8", "ignore")
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode("utf-8", "ignore")
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise HttpFailure(str(e)) from e

    return send


class EgpSession:
    def __init__(self, transport: Transport | None = None, min_interval: float = 1.0) -> None:
        self._send = transport or urllib_transport()
        self._limiter = RateLimiter(min_interval)
        self._warm = False
        self._headers = {"User-Agent": UA, "X-Requested-With": "XMLHttpRequest"}

    def _request(self, method: str, path: str, data: dict | None = None) -> str:
        self._limiter.wait()
        status, body = self._send(method, BASE + path, data, self._headers)
        if status != 200:
            raise HttpFailure(f"{method} {path} -> HTTP {status}")
        if "session has been expired" in body or "<title>Session Expired</title>" in body:
            self._warm = False
            raise SessionExpired(path)
        return body

    def warm_up(self) -> None:
        self._request("GET", WARMUP_PATH)
        self._warm = True

    def list_page(self, endpoint: str, page: int, size: int = 200) -> str:
        if not self._warm:
            self.warm_up()
        path, params = ENDPOINTS[endpoint]
        return self._request("POST", path, params(page, size))

    def detail(self, tender_id: str) -> str:
        if not self._warm:
            self.warm_up()
        return self._request("POST", DETAIL_PATH, {"id": str(tender_id), "h": "t"})
