import hashlib
import json
import re
from datetime import date, datetime, timedelta
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from app.config import TAVILY_API_KEY

_TAVILY_URL = "https://api.tavily.com/search"
_MAX_RESULTS = 10
_DATE_RE = re.compile(
    r"(?<!\d)(?P<year>\d{3,4})[-/.年]"
    r"(?P<month>\d{1,2})[-/.月](?P<day>\d{1,2})日?"
)
_TAIPEI = ZoneInfo("Asia/Taipei")


class WelfareSearchError(Exception):
    """A safe-to-report failure from the configured web search provider."""

    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.status_code = status_code


def _date_from_parts(year: str, month: str, day: str) -> date | None:
    parsed_year = int(year)
    if len(year) == 3:
        parsed_year += 1911
    try:
        return date(parsed_year, int(month), int(day))
    except ValueError:
        return None


def _event_date(text: str) -> str | None:
    candidates = []
    today = datetime.now(_TAIPEI).date()
    for match in _DATE_RE.finditer(text):
        parsed = _date_from_parts(
            match.group("year"), match.group("month"), match.group("day")
        )
        if parsed and parsed >= today:
            candidates.append(parsed)
    return min(candidates).isoformat() if candidates else None


def _published_date(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value[:10]).isoformat()
    except ValueError:
        return None


def _source(url: str) -> str:
    return urlsplit(url).hostname or ""


def _search(query: str) -> dict:
    if not TAVILY_API_KEY:
        raise WelfareSearchError(
            "福利／活動搜尋尚未設定 TAVILY_API_KEY。", status_code=503
        )
    payload = {
        "api_key": TAVILY_API_KEY,
        "query": query,
        "search_depth": "advanced",
        "max_results": _MAX_RESULTS,
        "include_domains": ["gov.tw", "org.tw"],
        "include_answer": "advanced",
    }
    request = Request(
        _TAVILY_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=20) as response:
            data = json.loads(response.read())
    except HTTPError as exc:
        raise WelfareSearchError(
            f"福利／活動搜尋服務回傳 HTTP {exc.code}。"
        ) from exc
    except (URLError, TimeoutError) as exc:
        raise WelfareSearchError("福利／活動搜尋服務目前無法連線。") from exc
    except json.JSONDecodeError as exc:
        raise WelfareSearchError("福利／活動搜尋服務回傳無法解析的資料。") from exc
    if not isinstance(data, dict) or not isinstance(data.get("results"), list):
        raise WelfareSearchError("福利／活動搜尋服務回傳格式不正確。")
    return data


def _clip(text: str, limit: int = 120) -> str:
    clean = re.sub(r"\s+", " ", text or "").strip(" ：:；;。")
    clean = re.split(r"\s*(?:Read more|\.\.\.|\[\.\.\.\])\s*", clean, maxsplit=1, flags=re.I)[0]
    clean = clean.strip(" ：:；;。")
    return clean[:limit] + ("…" if len(clean) > limit else "")


def _snippet(text: str, limit: int = 220) -> str:
    return _clip(text, limit)


_CONDITION_LABELS = (
    "申請條件", "服務對象", "補助對象", "申請資格", "補助資格",
    "資格條件", "適用對象", "申請對象",
)
_BENEFIT_LABELS = (
    "補助金額", "補助額度", "補助項目", "補助內容",
    "服務內容", "服務項目", "給付標準", "福利內容",
)
_CONDITION_PATTERNS = (
    r"設籍[^。；;]{8,180}", r"年滿[^。；;]{8,180}",
    r"居住[^。；;]{2,120}?(?:長者|老人|市民|民眾)",
    r"符合[^。；;]{8,180}條件", r"年齡[^。；;]{4,100}",
)
_BENEFIT_PATTERNS = (
    r"(?:最高|每人|每月|每年)[^。；;]{2,100}(?:元|萬元)",
    r"(?:新臺幣|補助|津貼|禮金)[^。；;]{2,100}(?:元|萬元)",
    r"可(?:申請|獲得|領取)[^。；;]{4,140}",
    r"(?:提供|補助|津貼|服務|禮金)[^。；;]{4,120}",
)
_NOISE_RE = re.compile(r"網頁連結|展開選單|收合選單|回上頁|登入|註冊|字級|:::|Facebook")
_BAD_HEADLINE_RE = re.compile(r"擬定計畫|服務流程|申請服務|評估等級|個管員|轉介|來電")


def _labeled(text: str, labels: tuple[str, ...]) -> str:
    for label in labels:
        match = re.search(
            re.escape(label) + r"\s*[：:]?\s*(.{4,200}?)(?:[。；;]|$)", text
        )
        if match:
            value = _clip(match.group(1))
            if len(value) >= 4:
                return value
    return ""


def _extract(text: str, labels: tuple[str, ...], patterns: tuple[str, ...]) -> str:
    value = _labeled(text, labels)
    if value:
        return value
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            value = _clip(match.group(0))
            if len(value) >= 4:
                return value
    return ""


def _headline(title: str, conditions: str, benefits: str) -> str:
    if benefits and not _BAD_HEADLINE_RE.search(benefits):
        return _clip(benefits, 80)
    return _clip(conditions or title, 80)


def search_welfare(
    *,
    event_type: str | None = None,
    target: str | None = None,
    time: str | None = None,
    region: str | None = None,
) -> dict:
    terms = [
        term.strip()
        for term in (region, target, event_type)
        if isinstance(term, str) and term.strip()
    ]
    region = region.strip() if region else None
    query = " ".join(terms + ["福利 補助 活動 申請資格 申請方式 服務對象"])
    if time not in {None, "today", "week", "month", "all"}:
        raise ValueError("time 必須是 today、week、month 或 all。")
    data = _search(query)
    results = []
    seen = set()
    for item in data["results"]:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        url = str(item.get("url") or "").strip()
        content = str(item.get("content") or "").strip()
        source = _source(url)
        if not (title and url.startswith(("http://", "https://")) and source):
            continue
        if url in seen or len(_NOISE_RE.findall(content)) >= 3:
            continue
        seen.add(url)
        event_date = _event_date(f"{title}\n{content}")
        if event_date and not _matches_time(date.fromisoformat(event_date), time):
            continue
        clean_content = re.sub(r"\s+", " ", content)
        conditions = _extract(clean_content, _CONDITION_LABELS, _CONDITION_PATTERNS)
        benefits = _extract(clean_content, _BENEFIT_LABELS, _BENEFIT_PATTERNS)
        results.append(
            {
                "id": hashlib.sha256(url.encode("utf-8")).hexdigest()[:16],
                "title": title,
                "headline": _headline(title, conditions, benefits),
                "conditions": conditions,
                "benefits": benefits,
                "source": source,
                "snippet": _snippet(clean_content),
                "publishedAt": _published_date(item.get("published_date")),
                "eventDate": event_date,
                "url": url,
            }
        )
    if region:
        results.sort(
            key=lambda item: (
                0 if region in f"{item['title']} {item['snippet']}" else 1,
            )
        )
    answer = data.get("answer")
    return {
        "answer": answer.strip() if isinstance(answer, str) else "",
        "results": results,
        "partial": False,
        "failedSources": [],
    }


def _matches_time(event_date: date, time: str | None) -> bool:
    if time in {None, "all"}:
        return True
    today = datetime.now(_TAIPEI).date()
    if time == "today":
        return event_date == today
    if time == "week":
        start = today - timedelta(days=today.weekday())
        end = start + timedelta(days=7)
        return start <= event_date < end
    if time == "month":
        return (event_date.year, event_date.month) == (today.year, today.month)
    return True
