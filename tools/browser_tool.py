import re
import webbrowser
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import quote_plus, urlparse
from urllib.request import Request, urlopen

from result_contract import build_result, make_artifact


BASE = Path(__file__).resolve().parent.parent
LOGS = BASE / "logs"
LOG_FILE = LOGS / "brain.log"

SITE_ALIASES = {
    "google": "https://www.google.com",
    "youtube": "https://www.youtube.com",
    "github": "https://github.com",
    "wikipedia": "https://www.wikipedia.org",
}


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self._parts = []

    def handle_data(self, data):
        cleaned = " ".join(data.split())
        if cleaned:
            self._parts.append(cleaned)

    def get_text(self):
        return " ".join(self._parts)


def _log_action(action, success, details):
    try:
        LOGS.mkdir(parents=True, exist_ok=True)
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{now}] browser_tool action={action} success={success} details={details}\n")
    except Exception:
        pass


def _structured_result(success, action, result="", error=None, observed=None, artifacts=None, warnings=None, errors=None, **extra):
    payload = build_result(
        success=success,
        action=action,
        result=result,
        error=error,
        observed=observed,
        artifacts=artifacts,
        warnings=warnings,
        errors=errors,
        **extra,
    )
    return payload


def normalize_url(url):
    raw = str(url).strip()
    if not raw:
        return None
    lowered = raw.lower()
    if lowered in SITE_ALIASES:
        return SITE_ALIASES[lowered]
    if lowered.startswith(("http://", "https://")):
        return raw
    if re.match(r"^[a-z0-9.-]+\.[a-z]{2,}(/.*)?$", lowered):
        return f"https://{raw}"
    return None


def open_url(url):
    action = "open_url"
    try:
        normalized = normalize_url(url)
        if not normalized:
            result = _structured_result(False, action, error=f"Malformed or unsupported URL: {url}")
            _log_action(action, False, result["error"])
            return result
        webbrowser.open(normalized)
        result = _structured_result(
            True,
            action,
            result=f"Browser open request sent for URL: {normalized}",
            observed=[f"A browser open request was issued without an immediate exception: {normalized}"],
            artifacts=[make_artifact("url", path=normalized, description="Requested URL", verified=False)],
            warnings=["I cannot confirm that the browser tab became visible."],
            url=normalized,
        )
        _log_action(action, True, result["result"])
        return result
    except Exception as e:
        result = _structured_result(False, action, error=str(e))
        _log_action(action, False, result["error"])
        return result


def web_search(query, engine="google"):
    action = "web_search"
    cleaned = str(query).strip()
    if not cleaned:
        result = _structured_result(False, action, error="Search query is required.")
        _log_action(action, False, result["error"])
        return result
    if engine == "youtube":
        url = f"https://www.youtube.com/results?search_query={quote_plus(cleaned)}"
    else:
        url = f"https://www.google.com/search?q={quote_plus(cleaned)}"
    result = _structured_result(
        True,
        action,
        result=f"Prepared {engine} search: {cleaned}",
        observed=[f"Constructed {engine} search URL for query: {cleaned}"],
        artifacts=[make_artifact("url", path=url, description="Search URL", verified=False)],
        url=url,
        query=cleaned,
        engine=engine,
    )
    _log_action(action, True, result["result"])
    return result


def open_search(query, engine="google"):
    action = "open_search"
    prepared = web_search(query, engine=engine)
    if not prepared["success"]:
        return _structured_result(False, action, error=prepared["error"])
    opened = open_url(prepared["url"])
    if not opened["success"]:
        return _structured_result(False, action, error=opened["error"])
    result = _structured_result(
        True,
        action,
        result=f"Browser search open request sent for: {prepared['query']}",
        observed=[
            f"Constructed {engine} search URL for query: {prepared['query']}",
            f"A browser open request was issued without an immediate exception: {prepared['url']}",
        ],
        artifacts=[make_artifact("url", path=prepared["url"], description="Search URL", verified=False)],
        warnings=["I cannot confirm that the browser search page became visible."],
        url=prepared["url"],
        query=prepared["query"],
        engine=engine,
    )
    _log_action(action, True, result["result"])
    return result


def extract_page_text(url):
    action = "extract_page_text"
    try:
        normalized = normalize_url(url)
        if not normalized:
            result = _structured_result(False, action, error=f"Malformed or unsupported URL: {url}")
            _log_action(action, False, result["error"])
            return result
        parsed = urlparse(normalized)
        if parsed.scheme not in {"http", "https"}:
            result = _structured_result(False, action, error="Only HTTP/HTTPS pages are supported.")
            _log_action(action, False, result["error"])
            return result

        request = Request(normalized, headers={"User-Agent": "RogueAI/1.0"})
        with urlopen(request, timeout=10) as response:
            content_type = response.headers.get("Content-Type", "")
            if "text/html" not in content_type:
                result = _structured_result(False, action, error=f"Unsupported content type: {content_type}")
                _log_action(action, False, result["error"])
                return result
            html = response.read().decode("utf-8", errors="ignore")

        parser = _TextExtractor()
        parser.feed(html)
        text = parser.get_text()[:4000]
        observed = [f"Fetched HTML content from: {normalized}", f"Extracted {len(text)} characters of readable text."]
        if not text:
            observed.append("No readable text was extracted from the page body.")
        result = _structured_result(
            True,
            action,
            result=text or "No readable text extracted.",
            observed=observed,
            artifacts=[make_artifact("url", path=normalized, description="Fetched page URL", verified=False)],
            url=normalized,
        )
        _log_action(action, True, f"Extracted text from {normalized}")
        return result
    except Exception as e:
        result = _structured_result(False, action, error=str(e))
        _log_action(action, False, result["error"])
        return result
