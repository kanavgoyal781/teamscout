"""Country/hiring-region: location=HQ only; description=regions; hq_mismatch needs foreign HQ."""
from __future__ import annotations
import re
_ALIASES = {"us":"US","usa":"US","u.s.":"US","u.s.a.":"US","united states":"US","united states of america":"US","uk":"GB","u.k.":"GB","united kingdom":"GB","great britain":"GB","england":"GB","canada":"CA","ca":"CA","india":"IN","in":"IN","germany":"DE","de":"DE","france":"FR","fr":"FR","netherlands":"NL","nl":"NL","australia":"AU","au":"AU","singapore":"SG","sg":"SG","ireland":"IE","ie":"IE","israel":"IL","il":"IL","brazil":"BR","br":"BR","mexico":"MX","mx":"MX","spain":"ES","es":"ES","italy":"IT","it":"IT","japan":"JP","jp":"JP","south korea":"KR","korea":"KR","kr":"KR","sweden":"SE","switzerland":"CH","poland":"PL","portugal":"PT","gb":"GB"}
_US_ST = frozenset("AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY DC".split())
_US_HINT = re.compile(r"(?i)\b(new york|san francisco|seattle|austin|boston|chicago|denver|atlanta|los angeles|bay area|silicon valley|remote us|us remote)\b")
_US_STATE = re.compile(r",\s*(AL|AK|AZ|AR|CA|CO|CT|DE|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|MD|MA|MI|MN|MS|MO|MT|NE|NV|NH|NJ|NM|NY|NC|ND|OH|OK|OR|PA|RI|SC|SD|TN|TX|UT|VT|VA|WA|WV|WI|WY|DC)\b")
_IN_HINT = re.compile(r"(?i)\b(india|bangalore|bengaluru|hyderabad|gurugram|gurgaon|noida|pune|chennai|mumbai|delhi|kolkata)\b")
_WW = re.compile(r"(?i)\b(worldwide|global(?:ly)?|anywhere|work\s+from\s+anywhere|wfa)\b")
_REGIONS = [(re.compile(r"(?i)\b(northern\s+america|north\s+america|americas?|latam|latin\s+america|us\s+time\s*zones?)\b"), frozenset({"US","CA","MX","BR"})), (re.compile(r"(?i)\b(emea|europe(?:an)?|eu\b)\b"), frozenset({"GB","DE","FR","NL","IE","ES","IT","SE","CH","PL","PT"})), (re.compile(r"(?i)\b(apac|asia[-\s]?pacific)\b"), frozenset({"IN","SG","JP","KR","AU"}))]
_CTRY = re.compile(r"(?i)\b(united\s+states|usa|u\.s\.a\.|u\.s\.|united\s+kingdom|great\s+britain|canada|india|germany|france|netherlands|australia|singapore|ireland|israel|brazil|mexico|spain|italy|japan|south\s+korea|korea|sweden|switzerland|poland|portugal)\b")
_ISO_T = r"US|USA|UK|U\.K\.|GB|CA|IN|DE|FR|NL|AU|SG|IE|IL|BR|MX|ES|IT|JP|KR|SE|CH|PL|PT"
_ISO_LIST = re.compile(rf"\b((?:{_ISO_T})(?:\s*[,/;|&]\s*(?:and\s+)?(?:{_ISO_T}))+)\b")
_ISO_SAFE = re.compile(r"\b(US|USA|UK|U\.K\.|GB|FR|NL|AU|SG|BR|MX|ES|JP|KR|SE|CH|PL|PT)\b")
_ISO_TOK = re.compile(rf"(?:{_ISO_T})")
def _alias(k: str) -> str | None:
    k = k.lower().replace(".", ""); return _ALIASES.get(k) or _ALIASES.get(k.replace(" ", ""))
def parse_country(text: str | None) -> str | None:
    raw = (text or "").strip()
    if not raw: return None
    low = re.sub(r"\s+", " ", raw.lower())
    if low in _ALIASES: return _ALIASES[low]
    if _US_STATE.search(raw) or _US_HINT.search(low): return "US"
    if _IN_HINT.search(low): return "IN"
    for part in re.split(r"[,/;|]+", low):
        p = part.strip()
        if p and not (len(p) == 2 and p.upper() in _US_ST) and p in _ALIASES: return _ALIASES[p]
    m = _CTRY.search(low)
    return _alias(m.group(1)) if m else None
def is_worldwide(text: str) -> bool:
    return bool(_WW.search(text or ""))
def region_countries(text: str) -> set[str]:
    blob = text or ""
    if is_worldwide(blob): return {"*"}
    found: set[str] = set()
    for pat, codes in _REGIONS:
        if pat.search(blob): found |= set(codes)
    for m in _CTRY.finditer(blob):
        c = _alias(m.group(1))
        if c: found.add(c)
    for m in _ISO_LIST.finditer(blob):
        for tok in _ISO_TOK.findall(m.group(0)):
            c = _alias(tok)
            if c: found.add(c)
    for m in _ISO_SAFE.finditer(blob):
        c = _alias(m.group(1))
        if c: found.add(c)
    return found
def job_geo_match(*, user_country: str | None, job_location: str, job_description: str, remote_mode: str | None, include_worldwide: bool = True) -> str:
    # Decision table: hq_mismatch only when parse_country(location) is foreign HQ.
    # regions from description only; regions∌user + no HQ → unknown (keep under Require).
    if not user_country: return "skip"
    loc, desc = job_location or "", (job_description or "")[:2500]
    if is_worldwide(loc) or is_worldwide(desc): return "worldwide" if include_worldwide else "hq_mismatch"
    regions = region_countries(desc)
    if "*" in regions: return "worldwide" if include_worldwide else "hq_mismatch"
    if user_country in regions: return "match"
    job_country = parse_country(loc)
    if job_country == user_country: return "match"
    if job_country and job_country != user_country: return "hq_mismatch"
    return "unknown"
