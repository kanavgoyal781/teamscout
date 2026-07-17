"""Generic JobMetadata extraction — no source-specific fields or defaults that invent content."""
from __future__ import annotations
import re
from typing import Any, Literal
from pydantic import BaseModel, Field, field_validator, model_validator
FieldConfidence = Literal["high", "medium", "low"]
RemoteModeMeta = Literal["remote", "hybrid", "onsite"]
CONF_FIELDS = (
    "title",
    "company",
    "location",
    "remote_mode",
    "salary_min",
    "salary_max",
    "salary_currency",
    "seniority",
    "department",
)
_CURRENCY_SYMBOLS = {"$": "USD", "£": "GBP", "€": "EUR", "¥": "JPY", "₹": "INR", "C$": "CAD", "A$": "AUD"}
_ISO = re.compile(r"^[A-Z]{3}$")
_TRAIL_PUNCT = re.compile(r"[\s,;:.\-–—|/]+$")
_LEAD_PUNCT = re.compile(r"^[\s,;:.\-–—|/]+")
_NUM = re.compile(
    r"(?P<cur>[$£€¥₹]|USD|GBP|EUR|CAD|AUD|INR)?\s*"
    r"(?P<num>\d{1,3}(?:,\d{3})*(?:\.\d+)?|\d+(?:\.\d+)?)\s*"
    r"(?P<suf>[kKmMbB])?",
)
def _strip_name(value: str | None) -> str | None:
    if value is None:
        return None
    s = _LEAD_PUNCT.sub("", _TRAIL_PUNCT.sub("", str(value).strip()))
    return s or None
def parse_salary_token(raw: str | int | float | None) -> int | None:
    """Normalize salary tokens. Hourly ( /hr, /hour, per hour) → None (no annualization)."""
    if raw is None:
        return None
    if isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        n = int(raw)
        return n if n > 0 else None
    text = str(raw).strip()
    if not text:
        return None
    low = text.lower()
    if any(x in low for x in ("/hr", "/hour", "per hour", "hourly", "/h ")):
        return None  # do not invent annual figures
    m = _NUM.search(text.replace(" ", ""))
    if not m:
        m = _NUM.search(text)
    if not m:
        return None
    num_s = m.group("num").replace(",", "")
    try:
        base = float(num_s)
    except ValueError:
        return None
    suf = (m.group("suf") or "").lower()
    if suf == "k":
        base *= 1_000
    elif suf == "m":
        base *= 1_000_000
    elif suf == "b":
        base *= 1_000_000_000
    n = int(round(base))
    return n if n > 0 else None
def detect_currency(text: str | None) -> str | None:
    if not text:
        return None
    s = str(text).strip()
    for sym, code in _CURRENCY_SYMBOLS.items():
        if sym in s:
            return code
    m = re.search(r"\b([A-Za-z]{3})\b", s)
    if m:
        code = m.group(1).upper()
        if _ISO.match(code) and code not in {"THE", "AND", "FOR", "PER", "ANN", "YEA"}:
            return code
    return None
def parse_salary_range(text: str | None) -> tuple[int | None, int | None, str | None]:
    """Parse free-text ranges: '$230K', 'up to $300K', '£60-70k', '$120,000 – $150,000'."""
    if text is None:
        return None, None, None
    if isinstance(text, (int, float)) and not isinstance(text, bool):
        n = parse_salary_token(text)
        return n, n, None
    s = str(text).strip()
    if not s:
        return None, None, None
    if any(x in s.lower() for x in ("/hr", "/hour", "per hour", "hourly")):
        return None, None, detect_currency(s)
    cur = detect_currency(s)
    low = s.lower()
    if re.search(r"\b(up to|upto|maximum|max\.?|capped at)\b", low):
        mx = parse_salary_token(s)
        return None, mx, cur
    shared_suf = ""
    m_suf = re.search(r"([kKmMbB])\s*$", s.replace(" ", ""))
    if m_suf:
        shared_suf = m_suf.group(1)
    parts = re.split(r"\s*(?:–|—|-|to|through|~)\s*", s, maxsplit=1)
    if len(parts) == 2:
        left, right = parts[0], parts[1]
        if shared_suf and not re.search(r"[kKmMbB]", left):
            left = left + shared_suf
        if shared_suf and not re.search(r"[kKmMbB]", right):
            right = right + shared_suf
        a, b = parse_salary_token(left), parse_salary_token(right)
        if a is not None and b is not None and a > b:
            a, b = b, a
        return a, b, cur
    n = parse_salary_token(s)
    return n, n, cur
class JobMetadata(BaseModel):
    title: str | None = None
    company: str | None = None
    location: str | None = None
    remote_mode: RemoteModeMeta | None = None
    salary_min: int | None = None
    salary_max: int | None = None
    salary_currency: str | None = None
    seniority: str | None = None
    department: str | None = None
    confidence: dict[str, FieldConfidence] = Field(default_factory=dict)
    @field_validator("title", "company", "location", "seniority", "department", mode="before")
    @classmethod
    def _clean_text(cls, v: Any) -> str | None:
        if v is None:
            return None
        if not isinstance(v, str):
            v = str(v)
        return _strip_name(v)
    @field_validator("salary_currency", mode="before")
    @classmethod
    def _currency_upper(cls, v: Any) -> str | None:
        if v is None or v == "":
            return None
        s = str(v).strip().upper()
        if s in _CURRENCY_SYMBOLS:
            return _CURRENCY_SYMBOLS[s]
        for sym, code in _CURRENCY_SYMBOLS.items():
            if s == sym:
                return code
        if len(s) == 3 and s.isalpha():
            return s
        return detect_currency(s)
    @field_validator("salary_min", "salary_max", mode="before")
    @classmethod
    def _salary_num(cls, v: Any) -> int | None:
        if v is None or v == "":
            return None
        if isinstance(v, str) and any(x in v.lower() for x in ("/hr", "hour", "hourly")):
            return None
        return parse_salary_token(v)
    @field_validator("remote_mode", mode="before")
    @classmethod
    def _remote(cls, v: Any) -> str | None:
        if v is None or v == "":
            return None
        s = str(v).strip().lower()
        if s in {"remote", "hybrid", "onsite", "on-site", "on site"}:
            return "onsite" if s.startswith("on") else s
        if "hybrid" in s:
            return "hybrid"
        if "remote" in s:
            return "remote"
        if "onsite" in s or "on-site" in s or "office" in s:
            return "onsite"
        return None
    @model_validator(mode="after")
    def _normalize_confidence_and_order(self) -> JobMetadata:
        conf: dict[str, FieldConfidence] = {}
        raw = self.confidence or {}
        for key in CONF_FIELDS:
            c = raw.get(key)
            if c in ("high", "medium", "low"):
                conf[key] = c  # type: ignore[assignment]
            elif getattr(self, key) is not None:
                conf[key] = "medium"
        if self.salary_min is not None and self.salary_max is not None and self.salary_min > self.salary_max:
            self.salary_min, self.salary_max = self.salary_max, self.salary_min
        self.confidence = conf
        return self
class ExtractMetadataRequest(BaseModel):
    description: str = Field(min_length=1)
class ExtractMetadataResponse(BaseModel):
    metadata: JobMetadata
    cache_hit: bool = False
    content_hash: str
