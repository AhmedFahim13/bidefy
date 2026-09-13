"""Capture one page of each e-GP endpoint as test fixtures. Makes four requests."""
import http.cookiejar
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

BASE = "https://www.eprocure.gov.bd"
UA = "Mozilla/5.0 bidefy-fixtures/0.1 (+https://github.com/AhmedFahim13/bidefy)"
OUT = Path(__file__).resolve().parents[1] / "tests" / "fixtures"

NETWORK_ERRORS = (urllib.error.URLError, urllib.error.HTTPError, TimeoutError)


def main() -> None:
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    opener.addheaders = [("User-Agent", UA), ("X-Requested-With", "XMLHttpRequest")]

    try:
        opener.open(BASE + "/resources/common/StdTenderSearch.jsp?h=t", timeout=60).read()
    except NETWORK_ERRORS as exc:
        sys.exit(f"network error during warm-up request: {exc}")

    def post(step: str, path: str, params: dict) -> str:
        data = urllib.parse.urlencode(params).encode()
        try:
            return opener.open(BASE + path, data=data, timeout=60).read().decode("utf-8", "ignore")
        except NETWORK_ERRORS as exc:
            sys.exit(f"network error during {step}: {exc}")

    tenders = post(
        "tenders request",
        "/TenderDetailsServlet",
        dict(funName="AllTenders", keyword="", pageNo=1, size=200, homeWSearch="homeWSearch", approve="false", h="t"),
    )
    contracts = post("contracts request", "/SearchNoaServlet", dict(keyword="", pageNo=1, size=200))
    first_id = re.search(r'name="id" value="(\d+)"', tenders)
    if not first_id:
        sys.exit("no tender id found in tenders page")
    detail = post("detail request", "/resources/common/ViewTender.jsp", dict(id=first_id.group(1), h="t"))

    checks = [
        ("tenders", tenders, "bgColor" in tenders and 'id="totalPages"' in tenders),
        ("contracts", contracts, "bgColor" in contracts and 'id="totalPages"' in contracts),
        ("detail", detail, "Procuring Entity Name" in detail),
    ]
    for name, body, ok in checks:
        if not ok:
            sys.exit(f"{name} fixture looked wrong, first 200 chars: {body[:200]!r}")

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "tenders_page.html").write_text(tenders, encoding="utf-8")
    (OUT / "contracts_page.html").write_text(contracts, encoding="utf-8")
    (OUT / "detail_page.html").write_text(detail, encoding="utf-8")
    print("saved", len(tenders), len(contracts), len(detail), "bytes; detail id", first_id.group(1))


if __name__ == "__main__":
    main()
