from bidefy.crawler.session import EgpSession, RateLimiter, SessionExpired


class Clock:
    def __init__(self):
        self.t = 1000.0
        self.slept = []

    def now(self):
        return self.t

    def sleep(self, s):
        self.slept.append(s)
        self.t += s


def test_rate_limiter_spaces_calls():
    clock = Clock()
    rl = RateLimiter(min_interval=1.0, now=clock.now, sleep=clock.sleep)
    rl.wait()          # first call: no sleep
    clock.t += 0.3
    rl.wait()          # 0.7 left
    assert clock.slept == [0.7]
    clock.t += 2.0
    rl.wait()          # long gap: no sleep
    assert clock.slept == [0.7]


def _transport(log):
    def send(method, url, data, headers):
        log.append((method, url, data))
        if url.endswith("StdTenderSearch.jsp?h=t"):
            return 200, "<html>shell</html>"
        if url.endswith("/TenderDetailsServlet"):
            return 200, "<tr class='bgColor-white'><td>1</td></tr>"
        if url.endswith("/SearchNoaServlet"):
            return 200, "<tr class='bgColor-white'><td>1</td></tr>"
        if url.endswith("/ViewTender.jsp"):
            return 200, "<html>detail</html>"
        return 404, ""
    return send


def test_list_page_posts_expected_params():
    log = []
    s = EgpSession(transport=_transport(log), min_interval=0)
    body = s.list_page("tenders", page=3, size=200)
    assert "bgColor" in body
    assert log[0][0] == "GET"                       # session warm-up first
    method, url, data = log[1]
    assert method == "POST" and url.endswith("/TenderDetailsServlet")
    assert data["funName"] == "AllTenders" and data["pageNo"] == "3" and data["size"] == "200"
    s.list_page("contracts", page=1)
    assert log[2][1].endswith("/SearchNoaServlet") and log[2][2] == {"keyword": "", "pageNo": "1", "size": "200"}


def test_detail_posts_id():
    log = []
    s = EgpSession(transport=_transport(log), min_interval=0)
    assert "detail" in s.detail("1329525")
    assert log[-1][2] == {"id": "1329525", "h": "t"}


def test_session_expired_raises():
    def send(method, url, data, headers):
        return 200, "<title>Session Expired</title> Your session has been expired"
    s = EgpSession(transport=send, min_interval=0)
    try:
        s.list_page("tenders", page=1)
        assert False, "expected SessionExpired"
    except SessionExpired:
        pass
