"""One-page connectivity probe for the Bangladesh e-GP portal.

Makes exactly three HTTP requests:
  1. GET  the public tender search page  (establishes the JSESSIONID cookie)
  2. POST TenderDetailsServlet, page 1, 200 rows
  3. POST SearchNoaServlet,     page 1, 200 rows

Prints row counts and total pages. Exits non-zero if either endpoint
returns no rows, so a GitHub Actions run fails visibly when the runner's
network is blocked by the portal.
"""
import http.cookiejar
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://www.eprocure.gov.bd"
UA = "Mozilla/5.0 (X11; Linux x86_64) egp-intel-probe/0.1 (+https://github.com/AhmedFahim13/egp-intel)"
TIMEOUT = 60


def build_opener():
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    opener.addheaders = [("User-Agent", UA), ("X-Requested-With", "XMLHttpRequest")]
    return opener, jar


def post(opener, path, params, label):
    t0 = time.time()
    try:
        resp = opener.open(BASE + path, data=urllib.parse.urlencode(params).encode(), timeout=TIMEOUT)
        body = resp.read().decode("utf-8", "ignore")
        status = resp.status
    except urllib.error.HTTPError as e:
        body, status = e.read().decode("utf-8", "ignore"), e.code
    except Exception as e:  # network-level failure
        print(f"[{label}] ERROR {type(e).__name__}: {e}")
        return 0, None
    rows = len(re.findall(r"<tr class='bgColor", body))
    total = re.search(r'id="totalPages" value="(\d+)"', body)
    total_pages = int(total.group(1)) if total else None
    print(f"[{label}] HTTP {status}  {len(body):,} bytes  {time.time() - t0:.1f}s  rows={rows}  totalPages={total_pages}")
    if rows == 0:
        print(f"[{label}] first 300 chars of body: {body[:300]!r}")
    return rows, total_pages


def main():
    opener, jar = build_opener()
    t0 = time.time()
    try:
        resp = opener.open(BASE + "/resources/common/StdTenderSearch.jsp?h=t", timeout=TIMEOUT)
        resp.read()
        print(f"[session] HTTP {resp.status}  {time.time() - t0:.1f}s  cookies={[c.name for c in jar]}")
    except Exception as e:
        print(f"[session] ERROR {type(e).__name__}: {e}")
        sys.exit(2)

    tender_rows, tender_pages = post(
        opener,
        "/TenderDetailsServlet",
        dict(funName="AllTenders", keyword="", pageNo=1, size=200, homeWSearch="homeWSearch", approve="false", h="t"),
        "tenders",
    )
    noa_rows, noa_pages = post(
        opener,
        "/SearchNoaServlet",
        dict(keyword="", pageNo=1, size=200),
        "contracts",
    )

    ok = tender_rows > 0 and noa_rows > 0
    print()
    print("RESULT:", "OK - portal reachable from this runner" if ok else "FAIL - portal did not return rows from this runner")
    if ok:
        print(f"  tenders:   {tender_rows} rows/page, {tender_pages:,} pages  (~{tender_rows * tender_pages:,} notices)")
        print(f"  contracts: {noa_rows} rows/page, {noa_pages:,} pages  (~{noa_rows * noa_pages:,} awards)")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
