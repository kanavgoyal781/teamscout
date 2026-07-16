from __future__ import annotations
import re
from app.services.ranking.config import DEFAULT_TOURNAMENT_THRESHOLD
from app.services.ranking.math import cosine_similarity
SKILL_MATCH_BONUS = 0.15
NEAR_DUP_COSINE_THRESHOLD = 0.95
TOURNAMENT_GAP = DEFAULT_TOURNAMENT_THRESHOLD
TOURNAMENT_TOP_K = 5
DEFAULT_EVIDENCE_FLOOR = 0.55
DEFAULT_HIT_THRESHOLD = 1e-9
SKILL_EXACT_SCORE = 1.0
SKILL_ALIAS_SCORE = 0.9
SKILL_SEMANTIC_CAP = 0.6
NO_CLEAR_EVIDENCE = "No clear evidence"
MAX_UNIT_CITATIONS = 3
BORDA_DECISIVE = 1.0
BORDA_SLIGHT = 0.5
def _alias_map(groups: list[set[str]]) -> dict[str, frozenset[str]]:
    out: dict[str, frozenset[str]] = {}
    for g in groups:
        fs = frozenset(g)
        for t in g:
            out[t] = fs
    return out
_SKILL_ALIASES = _alias_map(
    [
        {"go", "golang"}, {"js", "javascript"}, {"ts", "typescript"},
        {"postgres", "postgresql"}, {"c++", "cpp"}, {"c#", "csharp"},
        {"node", "nodejs", "node.js"}, {"react", "reactjs", "react.js"},
    ]
)
_SINGLE_CHAR_SKILLS = frozenset({"c", "r"})
_SKILL_STOPWORDS = frozenset({
    "strong", "skills", "skill", "experience", "proficient", "proficiency", "knowledge",
    "working", "with", "using", "and", "or", "the", "a", "an", "required", "preferred",
    "solid", "excellent", "good", "advanced", "basic", "intermediate", "expert", "years",
    "year", "plus", "of", "in", "ability", "to", "demonstrated", "hands", "on",
    "familiarity", "deep", "proven", "track", "record", "must", "have", "nice", "for",
    "etc", "including", "such", "as", "well", "highly", "very", "extensive", "prior",
})
_SECTION_RANK = {"experience": 0, "summary": 1, "skills": 2, "title": 3}
def tokenize_tech(text: str) -> list[str]:
    if not text: return []
    return re.findall(
        r"c\+\+|c#|node\.js|react\.js|[a-z0-9]+(?:\.[a-z0-9]+)*|\bc\b|\br\b", text.lower()
    )
def _canonical_forms(token: str) -> frozenset[str]:
    t = token.strip().lower()
    if not t: return frozenset()
    return _SKILL_ALIASES[t] if t in _SKILL_ALIASES else frozenset({t})
def tokens_match(req_token: str, hay_token: str) -> bool:
    a, b = req_token.strip().lower(), hay_token.strip().lower()
    if not a or not b: return False
    return a == b or bool(_canonical_forms(a) & _canonical_forms(b))
def phrase_in_text(phrase: str, text: str) -> bool:
    req, hay = (phrase or "").strip().lower(), (text or "").strip().lower()
    if not req or not hay or (len(req) < 2 and req not in _SINGLE_CHAR_SKILLS): return False
    req_tokens, hay_tokens = tokenize_tech(req), tokenize_tech(hay)
    if not req_tokens or not hay_tokens: return False
    if len(req_tokens) == 1:
        rt = req_tokens[0]
        if len(rt) < 2 and rt not in _SINGLE_CHAR_SKILLS: return False
        return any(tokens_match(rt, ht) for ht in hay_tokens)
    n, m = len(req_tokens), len(hay_tokens)
    return any(all(tokens_match(req_tokens[j], hay_tokens[i + j]) for j in range(n)) for i in range(m - n + 1))
def skill_tokens_from_requirement(requirement_text: str) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for tok in tokenize_tech(requirement_text):
        if tok in _SKILL_STOPWORDS or (len(tok) < 2 and tok not in _SINGLE_CHAR_SKILLS) or tok in seen:
            continue
        seen.add(tok)
        out.append(tok)
    return out
def _phrase_level_in_tokens(needle: list[str], hay: list[str]) -> str | None:
    if not needle or not hay or len(needle) > len(hay): return None
    best: str | None = None
    n = len(needle)
    for i in range(len(hay) - n + 1):
        window = hay[i : i + n]
        if all(a == b for a, b in zip(needle, window, strict=True)): return "exact"
        if all(tokens_match(a, b) for a, b in zip(needle, window, strict=True)): best = "alias"
    return best
def skill_phrase_level(skill: str, text: str) -> str | None:
    return _phrase_level_in_tokens(tokenize_tech(skill), tokenize_tech(text))
def skill_match_level_atomic(req_atom: str, skill: str) -> str | None:
    req_t, skill_t = tokenize_tech(req_atom), tokenize_tech(skill)
    if not req_t or not skill_t or len(req_t) != len(skill_t): return None
    if all(a == b for a, b in zip(req_t, skill_t, strict=True)): return "exact"
    if all(tokens_match(a, b) for a, b in zip(req_t, skill_t, strict=True)): return "alias"
    return None
def skill_match_level(req: str, skill: str) -> str | None:
    """Atomic/alias equality, or skill contained in phrased req ('SQL' ⊂ 'Strong SQL skills')."""
    req_t, skill_t = tokenize_tech(req), tokenize_tech(skill)
    if not req_t or not skill_t: return None
    if len(req_t) == len(skill_t):
        level = skill_match_level_atomic(req, skill)
        if level is not None: return level
    contained = skill_phrase_level(skill, req)
    if contained is not None: return contained
    for atom in skill_tokens_from_requirement(req):
        level = skill_match_level_atomic(atom, skill)
        if level is not None: return level
    return None
def skill_equals(req: str, skill: str) -> bool:
    return skill_match_level(req, skill) is not None
def apply_evidence_floor(raw: float, *, floor: float = DEFAULT_EVIDENCE_FLOOR) -> float:
    e = float(raw)
    if floor >= 1.0: return 1.0 if e >= 1.0 else 0.0
    if e < floor: return 0.0
    return max(0.0, min(1.0, (e - floor) / (1.0 - floor)))
def is_hard_skill_match(raw: float) -> bool:
    return float(raw) + 1e-12 >= SKILL_ALIAS_SCORE
def evidence_strength(score: float) -> str:
    s = float(score)
    if s < DEFAULT_HIT_THRESHOLD: return "none"
    if s < 0.35: return "weak"
    if s < 0.70: return "solid"
    return "strong"
def skill_requirement_score(
    requirement_text: str, *, skills: list[str], unit_texts: list[str], semantic_score: float
) -> float:
    """Exact 1.0 / alias 0.9 short-circuit before semantic cap (floor applied only for semantic)."""
    best = 0.0
    for skill in skills:
        level = skill_match_level(requirement_text, skill)
        if level == "exact": return SKILL_EXACT_SCORE
        if level == "alias": best = max(best, SKILL_ALIAS_SCORE)
    atoms = skill_tokens_from_requirement(requirement_text)
    for ut in unit_texts:
        if not ut: continue
        if phrase_in_text(requirement_text, ut):
            if _phrase_level_in_tokens(tokenize_tech(requirement_text), tokenize_tech(ut)) == "exact":
                return SKILL_EXACT_SCORE
            best = max(best, SKILL_ALIAS_SCORE)
            continue
        for atom in atoms:
            level = skill_phrase_level(atom, ut)
            if level == "exact": return SKILL_EXACT_SCORE
            if level == "alias": best = max(best, SKILL_ALIAS_SCORE)
    if best >= SKILL_ALIAS_SCORE: return best
    return min(float(semantic_score), SKILL_SEMANTIC_CAP)
def section_rank(section: str | None) -> int:
    return _SECTION_RANK.get((section or "").strip().lower(), 9)
def unit_evidence_score(
    requirement_emb: list[float], unit_emb: list[float], *, requirement_text: str, unit_text: str,
    skills: list[str] | None = None, skill_bonus: float = SKILL_MATCH_BONUS, lexical_hit: float = 1.0,
) -> float:
    _ = skills, skill_bonus
    score = float(cosine_similarity(requirement_emb, unit_emb))
    if phrase_in_text(requirement_text, unit_text):
        score = max(score, lexical_hit)
    return max(0.0, min(1.0, score))
def _better_unit(score, section, text, best_score, best_section, best_text) -> bool:
    if score > best_score + 1e-12: return True
    if score < best_score - 1e-12:
        return False
    sr, br = section_rank(section), section_rank(best_section)
    return sr < br if sr != br else len(text or "") > len(best_text or "")
def maxsim_best_unit_index(
    requirement_emb: list[float], unit_embs: list[list[float]], *, requirement_text: str = "",
    unit_texts: list[str] | None = None, unit_sections: list[str] | None = None,
    skills: list[str] | None = None, skill_bonus: float = SKILL_MATCH_BONUS,
) -> tuple[int | None, float]:
    if not unit_embs: return None, 0.0
    texts = unit_texts if unit_texts is not None else [""] * len(unit_embs)
    sections = unit_sections if unit_sections is not None else [""] * len(unit_embs)
    best_i, best_s = 0, unit_evidence_score(
        requirement_emb, unit_embs[0], requirement_text=requirement_text, unit_text=texts[0] if texts else ""
    )
    best_sec, best_text = (sections[0] if sections else ""), (texts[0] if texts else "")
    for i in range(1, len(unit_embs)):
        text_i, sec_i = (texts[i] if i < len(texts) else ""), (sections[i] if i < len(sections) else "")
        s = unit_evidence_score(requirement_emb, unit_embs[i], requirement_text=requirement_text, unit_text=text_i)
        if _better_unit(s, sec_i, text_i, best_s, best_sec, best_text):
            best_s, best_i, best_sec, best_text = s, i, sec_i, text_i
    if resume_has_skill(requirement_text, skills or []):
        best_s = min(1.0, best_s + skill_bonus)
    return best_i, float(best_s)
def maxsim_evidence(
    requirement_emb: list[float], unit_embs: list[list[float]], *, requirement_text: str = "",
    unit_texts: list[str] | None = None, unit_sections: list[str] | None = None,
    skills: list[str] | None = None, skill_bonus: float = SKILL_MATCH_BONUS,
) -> float:
    return maxsim_best_unit_index(
        requirement_emb, unit_embs, requirement_text=requirement_text, unit_texts=unit_texts,
        unit_sections=unit_sections, skills=skills, skill_bonus=skill_bonus,
    )[1]
def coverage_from_evidence(weights: list[float], evidences: list[float]) -> float:
    if not weights or not evidences: return 0.0
    if len(weights) != len(evidences): raise ValueError("weights and evidences length mismatch")
    total_w = sum(float(w) for w in weights)
    if total_w <= 0: return 0.0
    return max(0.0, min(1.0, sum(float(w) * float(e) for w, e in zip(weights, evidences, strict=True)) / total_w))
def resume_has_skill(requirement_text: str, skills: list[str]) -> bool:
    req = (requirement_text or "").strip()
    if not req or (len(req) < 2 and req.lower() not in _SINGLE_CHAR_SKILLS): return False
    return any(skill and skill_equals(req, skill) for skill in skills)
def skill_match_bonus_applies(requirement_text: str, *, unit_text: str | None, skills: list[str] | None = None) -> bool:
    _ = skills
    req = (requirement_text or "").strip()
    ut = unit_text or ""
    return len(req) >= 2 and bool(ut) and phrase_in_text(req, ut)
def align_resume(
    requirement_embs: list[list[float]], requirement_texts: list[str], weights: list[float],
    unit_embs: list[list[float]], unit_texts: list[str], skills: list[str], *,
    unit_sections: list[str] | None = None, skill_bonus: float = SKILL_MATCH_BONUS,
    hit_threshold: float = DEFAULT_HIT_THRESHOLD, evidence_floor: float = DEFAULT_EVIDENCE_FLOOR,
    categories: list[str] | None = None,
) -> tuple[float, list[dict]]:
    if len(requirement_embs) != len(weights) or len(requirement_embs) != len(requirement_texts): raise ValueError("requirement arrays length mismatch")
    if len(unit_embs) != len(unit_texts):
        raise ValueError("unit arrays length mismatch")
    if unit_sections is not None and len(unit_sections) != len(unit_texts): raise ValueError("unit_sections length mismatch")
    if categories is not None and len(categories) != len(requirement_texts):
        raise ValueError("categories length mismatch")
    evidences: list[float] = []
    rows: list[dict] = []
    for i, (req_emb, req_text, weight) in enumerate(zip(requirement_embs, requirement_texts, weights, strict=True)):
        category = (categories[i] if categories is not None else "skill") or "skill"
        is_skill = category == "skill"
        best_i, semantic = maxsim_best_unit_index(
            req_emb, unit_embs, requirement_text=req_text, unit_texts=unit_texts,
            unit_sections=unit_sections, skills=None if is_skill else skills,
            skill_bonus=0.0 if is_skill else skill_bonus,
        )
        unit_text = unit_texts[best_i] if best_i is not None else None
        if is_skill:
            raw = skill_requirement_score(
                req_text, skills=skills, unit_texts=unit_texts, semantic_score=semantic
            )
            atoms = skill_tokens_from_requirement(req_text)
            best_u, best_sec, best_txt = None, None, ""
            for j, ut in enumerate(unit_texts):
                hit = phrase_in_text(req_text, ut) or any(phrase_in_text(a, ut) for a in atoms)
                if not hit: continue
                sec = unit_sections[j] if unit_sections is not None and j < len(unit_sections) else ""
                if best_u is None or _better_unit(1.0, sec, ut, 1.0, best_sec, best_txt):
                    best_u, best_sec, best_txt = ut, sec, ut
            if best_u is not None: unit_text = best_u
            elif is_hard_skill_match(raw):
                for s in skills:
                    if skill_match_level(req_text, s) is not None:
                        unit_text = s
                        break
            # Hard exact/alias: no floor; semantic path only is rescaled
            evidence = float(raw) if is_hard_skill_match(raw) else apply_evidence_floor(raw, floor=evidence_floor)
        else:
            raw = float(semantic)
            evidence = apply_evidence_floor(raw, floor=evidence_floor)
        status = "miss" if evidence < hit_threshold else "hit"
        rows.append({
            "requirement": req_text, "weight": float(weight),
            "evidence_unit": NO_CLEAR_EVIDENCE if status == "miss" else unit_text,
            "evidence_score": round(evidence, 4), "raw_evidence_score": round(float(raw), 4),
            "status": status, "category": category, "strength": evidence_strength(evidence),
        })
        evidences.append(evidence)
    return coverage_from_evidence(weights, evidences), rows
def single_linkage_clusters(
    ids: list[str], embeddings: list[list[float]], *, threshold: float = NEAR_DUP_COSINE_THRESHOLD,
) -> dict[str, str]:
    if len(ids) != len(embeddings): raise ValueError("ids and embeddings length mismatch")
    n = len(ids)
    if n == 0: return {}
    parent = list(range(n))
    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb if ra < rb else ra] = ra if ra < rb else rb
    for i in range(n):
        for j in range(i + 1, n):
            if cosine_similarity(embeddings[i], embeddings[j]) >= threshold:
                union(i, j)
    components: dict[int, list[str]] = {}
    for i, item_id in enumerate(ids):
        components.setdefault(find(i), []).append(item_id)
    return {m: min(members) for members in components.values() for m in members}
def cluster_variant_label(resume_id: str, cluster_id: str, members_sorted: list[str]) -> str:
    try:
        idx = members_sorted.index(resume_id) + 1
    except ValueError:
        idx = 1
    return f"variant {idx} of base version {cluster_id[:8] if cluster_id else '?'}"
def borda_points_for_margin(margin: str | None) -> float:
    return BORDA_SLIGHT if (margin or "").strip().lower() == "slight" else BORDA_DECISIVE
def borda_order(
    contested_ids: list[str], pairwise_wins: dict[tuple[str, str], str], *,
    coverage_tiebreak: dict[str, float] | None = None,
    pairwise_margins: dict[tuple[str, str], str] | None = None,
    pairwise_points: dict[tuple[str, str], float] | None = None,
) -> list[str]:
    scores: dict[str, float] = {i: 0.0 for i in contested_ids}
    for (a, b), winner in pairwise_wins.items():
        if a in scores and b in scores and winner in scores:
            key = (a, b) if a <= b else (b, a)
            if pairwise_points is not None and key in pairwise_points:
                pts = float(pairwise_points[key])
            elif pairwise_margins is not None:
                pts = borda_points_for_margin(pairwise_margins.get(key))
            else:
                pts = BORDA_DECISIVE
            scores[winner] += pts
    tb = coverage_tiebreak or {}
    return sorted(contested_ids, key=lambda i: (-scores.get(i, 0.0), -tb.get(i, 0.0), i))
def under_segmented_units(rows: list[dict], *, max_citations: int = MAX_UNIT_CITATIONS) -> list[str]:
    counts: dict[str, int] = {}
    for row in rows:
        unit = row.get("evidence_unit")
        if unit and unit != NO_CLEAR_EVIDENCE and row.get("status") == "hit":
            counts[str(unit)] = counts.get(str(unit), 0) + 1
    return [u for u, n in counts.items() if n > max_citations]
def close_call_band(
    ordered_by_coverage: list[tuple[str, float]], *, gap: float = TOURNAMENT_GAP, top_k: int = TOURNAMENT_TOP_K,
) -> list[str]:
    if len(ordered_by_coverage) < 2: return []
    head = ordered_by_coverage[: min(top_k, len(ordered_by_coverage))]
    leader_cov = head[0][1]
    if leader_cov - head[1][1] >= gap: return []
    return [rid for rid, cov in head if leader_cov - cov < gap]
def merge_tournament_order(full_ids_by_coverage: list[str], contested_ordered: list[str]) -> list[str]:
    contested = set(contested_ordered)
    if not contested: return list(full_ids_by_coverage)
    prefix_len = 0
    for rid in full_ids_by_coverage:
        if rid in contested:
            prefix_len += 1
        else:
            break
    if prefix_len == len(contested): return list(contested_ordered) + full_ids_by_coverage[prefix_len:]
    t_iter = iter(contested_ordered)
    return [next(t_iter) if rid in contested else rid for rid in full_ids_by_coverage]
def order_normalized_pair(hash_a: str, hash_b: str) -> tuple[str, str]:
    return (hash_a, hash_b) if hash_a <= hash_b else (hash_b, hash_a)
