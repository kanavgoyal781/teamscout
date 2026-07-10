"""Pure MaxSim, coverage, clustering, Borda (no I/O). L2-cos; MaxSim=max; token-aware lexical floor."""
from __future__ import annotations
import re
from app.services.ranking_config import DEFAULT_TOURNAMENT_THRESHOLD
from app.services.ranking_math import cosine_similarity
SKILL_MATCH_BONUS = 0.15
NEAR_DUP_COSINE_THRESHOLD = 0.95
TOURNAMENT_GAP = DEFAULT_TOURNAMENT_THRESHOLD
TOURNAMENT_TOP_K = 5
def _alias_map(groups: list[set[str]]) -> dict[str, frozenset[str]]:
    out: dict[str, frozenset[str]] = {}
    for g in groups:
        fs = frozenset(g)
        for t in g:
            out[t] = fs
    return out
_SKILL_ALIASES = _alias_map(
    [
        {"go", "golang"},
        {"js", "javascript"},
        {"ts", "typescript"},
        {"postgres", "postgresql"},
        {"c++", "cpp"},
        {"c#", "csharp"},
        {"node", "nodejs", "node.js"},
        {"react", "reactjs", "react.js"},
    ]
)
def tokenize_tech(text: str) -> list[str]:
    if not text:
        return []
    return re.findall(
        r"c\+\+|c#|node\.js|react\.js|[a-z0-9]+(?:\.[a-z0-9]+)*|\bc\b|\br\b",
        text.lower(),
    )
def _canonical_forms(token: str) -> frozenset[str]:
    t = token.strip().lower()
    if not t:
        return frozenset()
    if t in _SKILL_ALIASES:
        return _SKILL_ALIASES[t]
    return frozenset({t})
def tokens_match(req_token: str, hay_token: str) -> bool:
    """Whole-token equality with explicit aliases only (java ≠ javascript)."""
    a, b = req_token.strip().lower(), hay_token.strip().lower()
    if not a or not b:
        return False
    if a == b:
        return True
    return bool(_canonical_forms(a) & _canonical_forms(b))
_SINGLE_CHAR_SKILLS = frozenset({"c", "r"})
def phrase_in_text(phrase: str, text: str) -> bool:
    """Whole-token phrase match; single-char only for C/R allowlist."""
    req = (phrase or "").strip().lower()
    hay = (text or "").strip().lower()
    if not req or not hay:
        return False
    if len(req) < 2 and req not in _SINGLE_CHAR_SKILLS:
        return False
    req_tokens = tokenize_tech(req)
    hay_tokens = tokenize_tech(hay)
    if not req_tokens or not hay_tokens:
        return False
    if len(req_tokens) == 1:
        rt = req_tokens[0]
        if len(rt) < 2 and rt not in _SINGLE_CHAR_SKILLS:
            return False
        return any(tokens_match(rt, ht) for ht in hay_tokens)
    n, m = len(req_tokens), len(hay_tokens)
    for i in range(m - n + 1):
        if all(tokens_match(req_tokens[j], hay_tokens[i + j]) for j in range(n)):
            return True
    return False
def skill_equals(req: str, skill: str) -> bool:
    """Whole skill equality (aliases allowed)."""
    req_t = tokenize_tech(req)
    skill_t = tokenize_tech(skill)
    if not req_t or not skill_t:
        return False
    if len(req_t) == 1 and len(skill_t) == 1:
        return tokens_match(req_t[0], skill_t[0])
    if len(req_t) != len(skill_t):
        return False
    return all(tokens_match(a, b) for a, b in zip(req_t, skill_t, strict=True))
_SECTION_RANK = {"experience": 0, "summary": 1, "skills": 2, "title": 3}
def section_rank(section: str | None) -> int:
    return _SECTION_RANK.get((section or "").strip().lower(), 9)
def unit_evidence_score(
    requirement_emb: list[float],
    unit_emb: list[float],
    *,
    requirement_text: str,
    unit_text: str,
    skills: list[str] | None = None,
    skill_bonus: float = SKILL_MATCH_BONUS,
    lexical_hit: float = 1.0,
) -> float:
    _ = skills, skill_bonus
    score = float(cosine_similarity(requirement_emb, unit_emb))
    if phrase_in_text(requirement_text, unit_text):
        score = max(score, lexical_hit)
    return max(0.0, min(1.0, score))
def _better_unit(
    score: float,
    section: str | None,
    text: str,
    best_score: float,
    best_section: str | None,
    best_text: str,
) -> bool:
    if score > best_score + 1e-12:
        return True
    if score < best_score - 1e-12:
        return False
    sr, br = section_rank(section), section_rank(best_section)
    if sr != br:
        return sr < br
    return len(text or "") > len(best_text or "")
def maxsim_best_unit_index(
    requirement_emb: list[float],
    unit_embs: list[list[float]],
    *,
    requirement_text: str = "",
    unit_texts: list[str] | None = None,
    unit_sections: list[str] | None = None,
    skills: list[str] | None = None,
    skill_bonus: float = SKILL_MATCH_BONUS,
) -> tuple[int | None, float]:
    if not unit_embs:
        return None, 0.0
    texts = unit_texts if unit_texts is not None else [""] * len(unit_embs)
    sections = unit_sections if unit_sections is not None else [""] * len(unit_embs)
    best_i = 0
    best_s = unit_evidence_score(
        requirement_emb,
        unit_embs[0],
        requirement_text=requirement_text,
        unit_text=texts[0] if texts else "",
    )
    best_sec = sections[0] if sections else ""
    best_text = texts[0] if texts else ""
    for i in range(1, len(unit_embs)):
        text_i = texts[i] if i < len(texts) else ""
        sec_i = sections[i] if i < len(sections) else ""
        s = unit_evidence_score(
            requirement_emb,
            unit_embs[i],
            requirement_text=requirement_text,
            unit_text=text_i,
        )
        if _better_unit(s, sec_i, text_i, best_s, best_sec, best_text):
            best_s, best_i, best_sec, best_text = s, i, sec_i, text_i
    if resume_has_skill(requirement_text, skills or []):
        best_s = min(1.0, best_s + skill_bonus)
    return best_i, float(best_s)
def maxsim_evidence(
    requirement_emb: list[float],
    unit_embs: list[list[float]],
    *,
    requirement_text: str = "",
    unit_texts: list[str] | None = None,
    unit_sections: list[str] | None = None,
    skills: list[str] | None = None,
    skill_bonus: float = SKILL_MATCH_BONUS,
) -> float:
    """MaxSim over units with the same formula as production alignment."""
    _idx, score = maxsim_best_unit_index(
        requirement_emb,
        unit_embs,
        requirement_text=requirement_text,
        unit_texts=unit_texts,
        unit_sections=unit_sections,
        skills=skills,
        skill_bonus=skill_bonus,
    )
    return score
def coverage_from_evidence(weights: list[float], evidences: list[float]) -> float:
    """Weighted mean of per-requirement evidence scores in [0, 1]."""
    if not weights or not evidences:
        return 0.0
    if len(weights) != len(evidences):
        raise ValueError("weights and evidences length mismatch")
    total_w = sum(float(w) for w in weights)
    if total_w <= 0:
        return 0.0
    num = sum(float(w) * float(e) for w, e in zip(weights, evidences, strict=True))
    score = num / total_w
    return max(0.0, min(1.0, score))
def resume_has_skill(requirement_text: str, skills: list[str]) -> bool:
    """True when requirement matches a listed profile skill (token-aware)."""
    req = (requirement_text or "").strip()
    if not req:
        return False
    if len(req) < 2 and req.lower() not in _SINGLE_CHAR_SKILLS:
        return False
    return any(skill and skill_equals(req, skill) for skill in skills)
def skill_match_bonus_applies(
    requirement_text: str,
    *,
    unit_text: str | None,
    skills: list[str] | None = None,
) -> bool:
    """Unit-local phrase match only (resume-level skill list is applied once after MaxSim)."""
    _ = skills
    req = (requirement_text or "").strip()
    if len(req) < 2 or not unit_text:
        return False
    return phrase_in_text(req, unit_text)
def align_resume(
    requirement_embs: list[list[float]],
    requirement_texts: list[str],
    weights: list[float],
    unit_embs: list[list[float]],
    unit_texts: list[str],
    skills: list[str],
    *,
    unit_sections: list[str] | None = None,
    skill_bonus: float = SKILL_MATCH_BONUS,
    hit_threshold: float = 0.45,
) -> tuple[float, list[dict]]:
    if len(requirement_embs) != len(weights) or len(requirement_embs) != len(requirement_texts):
        raise ValueError("requirement arrays length mismatch")
    if len(unit_embs) != len(unit_texts):
        raise ValueError("unit arrays length mismatch")
    if unit_sections is not None and len(unit_sections) != len(unit_texts):
        raise ValueError("unit_sections length mismatch")
    evidences: list[float] = []
    rows: list[dict] = []
    for req_emb, req_text, weight in zip(requirement_embs, requirement_texts, weights, strict=True):
        best_i, evidence = maxsim_best_unit_index(
            req_emb,
            unit_embs,
            requirement_text=req_text,
            unit_texts=unit_texts,
            unit_sections=unit_sections,
            skills=skills,
            skill_bonus=skill_bonus,
        )
        unit_text = unit_texts[best_i] if best_i is not None else None
        evidences.append(evidence)
        status = "hit" if evidence >= hit_threshold else "miss"
        rows.append(
            {
                "requirement": req_text,
                "weight": float(weight),
                "evidence_unit": unit_text,
                "evidence_score": round(evidence, 4),
                "status": status,
            }
        )
    return coverage_from_evidence(weights, evidences), rows
def single_linkage_clusters(
    ids: list[str],
    embeddings: list[list[float]],
    *,
    threshold: float = NEAR_DUP_COSINE_THRESHOLD,
) -> dict[str, str]:
    if len(ids) != len(embeddings):
        raise ValueError("ids and embeddings length mismatch")
    n = len(ids)
    if n == 0:
        return {}
    parent = list(range(n))
    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra == rb:
            return
        if ra < rb:
            parent[rb] = ra
        else:
            parent[ra] = rb
    for i in range(n):
        for j in range(i + 1, n):
            if cosine_similarity(embeddings[i], embeddings[j]) >= threshold:
                union(i, j)
    components: dict[int, list[str]] = {}
    for i, item_id in enumerate(ids):
        root = find(i)
        components.setdefault(root, []).append(item_id)
    id_to_cluster: dict[str, str] = {}
    for members in components.values():
        label = min(members)
        for m in members:
            id_to_cluster[m] = label
    return id_to_cluster
def cluster_variant_label(
    resume_id: str,
    cluster_id: str,
    members_sorted: list[str],
) -> str:
    """Human label like 'variant 2 of base version <cluster_id[:8]>'."""
    try:
        idx = members_sorted.index(resume_id) + 1
    except ValueError:
        idx = 1
    base = cluster_id[:8] if cluster_id else "?"
    return f"variant {idx} of base version {base}"
def borda_order(
    contested_ids: list[str],
    pairwise_wins: dict[tuple[str, str], str],
    *,
    coverage_tiebreak: dict[str, float] | None = None,
) -> list[str]:
    """Order contested set by Borda (wins in round-robin), coverage as tiebreak."""
    scores: dict[str, int] = {i: 0 for i in contested_ids}
    for (a, b), winner in pairwise_wins.items():
        if a in scores and b in scores and winner in scores:
            scores[winner] += 1
    tb = coverage_tiebreak or {}
    return sorted(
        contested_ids,
        key=lambda i: (-scores.get(i, 0), -tb.get(i, 0.0), i),
    )
def close_call_band(
    ordered_by_coverage: list[tuple[str, float]],
    *,
    gap: float = TOURNAMENT_GAP,
    top_k: int = TOURNAMENT_TOP_K,
) -> list[str]:
    """IDs within `gap` of the leader (capped at top_k). Empty if top-2 gap ≥ gap."""
    if len(ordered_by_coverage) < 2:
        return []
    head = ordered_by_coverage[: min(top_k, len(ordered_by_coverage))]
    leader_cov = head[0][1]
    if leader_cov - head[1][1] >= gap:
        return []
    return [rid for rid, cov in head if leader_cov - cov < gap]
def merge_tournament_order(
    full_ids_by_coverage: list[str],
    contested_ordered: list[str],
) -> list[str]:
    """Reorder contested band only; far-behind keep coverage order."""
    contested = set(contested_ordered)
    if not contested:
        return list(full_ids_by_coverage)
    prefix_len = 0
    for rid in full_ids_by_coverage:
        if rid in contested:
            prefix_len += 1
        else:
            break
    if prefix_len == len(contested):
        return list(contested_ordered) + full_ids_by_coverage[prefix_len:]
    t_iter = iter(contested_ordered)
    return [next(t_iter) if rid in contested else rid for rid in full_ids_by_coverage]
def order_normalized_pair(hash_a: str, hash_b: str) -> tuple[str, str]:
    """Symmetric pair key components (sorted)."""
    return (hash_a, hash_b) if hash_a <= hash_b else (hash_b, hash_a)
