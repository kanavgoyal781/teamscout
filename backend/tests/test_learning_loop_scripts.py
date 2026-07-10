"""Offline tests for feedback→eval builder, experiment harness, feedback suite, weekly gate."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from app.core.config import settings
from app.db.models import Feedback
from app.db.session import SessionLocal, ensure_db

ROOT = Path(__file__).resolve().parents[2]


def _seed_feedback(n: int = 5, *, include_find_team: bool = False, include_resume_pick: bool = False) -> None:
    ensure_db()
    db = SessionLocal()
    try:
        for i in range(n):
            kind = "thumbs_up" if i % 2 == 0 else "thumbs_down"
            if i == 1:
                kind = "apply_click"
            if include_find_team and i == 2:
                kind = "find_team_click"
            target_type = "resume_pick" if include_resume_pick and i == 0 else "job_match"
            db.add(
                Feedback(
                    kind=kind,
                    target_type=target_type,
                    target_id=f"job-{i}",
                    secondary_id=f"sec-{i}" if i == 0 else None,
                    profile_hash=f"{'a' * 16}",
                    jd_hash=f"{'b' * 16}",
                    score_shown=float(60 + i),
                    prompt_versions_json=json.dumps({"rerank": "1"}),
                    model="test-model",
                    embeddings_model="test-emb",
                    git_sha="deadbeef",
                    ranking_config_hash="abc123def4567890",
                )
            )
        # unknown kind should be skipped by builder
        db.add(
            Feedback(
                kind="legacy_unknown",
                target_type="job_match",
                target_id="skip-me",
                prompt_versions_json="{}",
            )
        )
        db.commit()
    finally:
        db.close()


def test_build_eval_from_feedback(tmp_path: Path) -> None:
    sys.path.insert(0, str(ROOT))
    from scripts.build_eval_from_feedback import build

    ensure_db()
    _seed_feedback(8, include_find_team=True, include_resume_pick=True)
    out = tmp_path / "feedback_set.jsonl"
    n = build(out)
    assert n >= 8
    lines = out.read_text(encoding="utf-8").strip().splitlines()
    rows = [json.loads(L) for L in lines]
    kinds = {r["kind"]: r["relevance"] for r in rows}
    assert kinds.get("thumbs_up") == 2.0
    assert kinds.get("thumbs_down") == 0.0
    assert kinds.get("apply_click") == 3.0
    assert kinds.get("find_team_click") == 2.5
    assert "legacy_unknown" not in kinds
    assert any(r.get("target_type") == "resume_pick" for r in rows)
    sample = rows[0]
    assert sample.get("ranking_config_hash") or sample.get("model")
    assert "prompt_versions" in sample
    assert "feedback_id" in sample


def test_build_eval_empty_db(tmp_path: Path) -> None:
    sys.path.insert(0, str(ROOT))
    from scripts.build_eval_from_feedback import build

    ensure_db()
    # Do not seed — may still have pollution from other tests; filter by writing and
    # accepting n>=0. For empty: wipe table.
    db = SessionLocal()
    try:
        db.query(Feedback).delete()
        db.commit()
    finally:
        db.close()
    out = tmp_path / "empty.jsonl"
    assert build(out) == 0
    assert out.read_text(encoding="utf-8") == ""


def test_experiment_config_hash_covers_all_result_params() -> None:
    sys.path.insert(0, str(ROOT))
    from scripts.experiment import RESULT_PARAM_KEYS, config_hash, normalize_variant

    base = normalize_variant(
        {
            "name": "baseline",
            "weights": {
                "llm": 0.38,
                "rrf": 0.2,
                "skills": 0.12,
                "recency": 0.08,
                "experience": 0.12,
                "requirements": 0.1,
            },
            "rrf_k": 60,
            "mmr_lambda": 0.75,
            "use_mmr": True,
            "expansion": True,
            "tournament_threshold": 0.05,
            "recency_half_life_days": 7,
            "rerank_top_n": 30,
            "search_results_top_n": 10,
        }
    )
    h0 = config_hash(base)
    # name excluded from hash
    renamed = dict(base)
    renamed["name"] = "other-name"
    assert config_hash(renamed) == h0

    mutators = {
        "weights": lambda v: {**v, "weights": {**v["weights"], "llm": 0.5, "rrf": 0.08}},
        "rrf_k": lambda v: {**v, "rrf_k": 40},
        "mmr_lambda": lambda v: {**v, "mmr_lambda": 1.0},
        "use_mmr": lambda v: {**v, "use_mmr": False},
        "expansion": lambda v: {**v, "expansion": False},
        "tournament_threshold": lambda v: {**v, "tournament_threshold": 0.1},
        "recency_half_life_days": lambda v: {**v, "recency_half_life_days": 14},
        "rerank_top_n": lambda v: {**v, "rerank_top_n": 20},
        "search_results_top_n": lambda v: {**v, "search_results_top_n": 5},
        "use_cross_encoder": lambda v: {**v, "use_cross_encoder": True},
        "cross_encoder_shortlist": lambda v: {**v, "cross_encoder_shortlist": True},
        "llm_listwise": lambda v: {**v, "llm_listwise": True},
        "cross_encoder_pool": lambda v: {**v, "cross_encoder_pool": 40},
        "llm_rerank_top_n": lambda v: {**v, "llm_rerank_top_n": 12},
        "direct_ats_boost": lambda v: {**v, "direct_ats_boost": 3.0},
    }
    for key in RESULT_PARAM_KEYS:
        mutated = mutators[key](base)
        assert config_hash(mutated) != h0, f"config_hash must change when {key} changes"


def test_experiment_use_mmr_changes_diversity_metrics(tmp_path: Path, monkeypatch) -> None:
    sys.path.insert(0, str(ROOT / "backend"))
    sys.path.insert(0, str(ROOT))
    import scripts.experiment as exp

    monkeypatch.setattr(exp, "OUT", tmp_path / "experiments.jsonl")
    on = exp.normalize_variant(json.loads((ROOT / "configs/experiments/defaults.json").read_text()))
    off = exp.normalize_variant(json.loads((ROOT / "configs/experiments/no_mmr.json").read_text()))
    assert on["use_mmr"] is True and off["use_mmr"] is False

    prev = exp.apply_variant(on)
    try:
        m_on, f_on = exp.run_synthetic(on)
    finally:
        exp.restore_settings(prev)
    prev = exp.apply_variant(off)
    try:
        m_off, f_off = exp.run_synthetic(off)
    finally:
        exp.restore_settings(prev)

    assert f_on["use_mmr"] is True and f_off["use_mmr"] is False
    # Pure diversity path must differ when MMR is on vs off
    assert m_on["mmr_companies_top10"] > m_off["mmr_companies_top10"]
    assert m_on["mmr_companies_top10"] >= 4
    assert m_off["mmr_companies_top10"] == m_off["rel_only_companies_top10"]


def test_experiment_restore_settings() -> None:
    sys.path.insert(0, str(ROOT))
    import scripts.experiment as exp

    baseline = {
        "RANKING_WEIGHT_LLM": settings.RANKING_WEIGHT_LLM,
        "RANKING_WEIGHT_RRF": settings.RANKING_WEIGHT_RRF,
        "RRF_K": settings.RRF_K,
        "RERANK_TOP_N": settings.RERANK_TOP_N,
    }
    variant = exp.normalize_variant(
        {
            "name": "tmp",
            "weights": {
                "llm": 0.5,
                "rrf": 0.1,
                "skills": 0.1,
                "recency": 0.1,
                "experience": 0.1,
                "requirements": 0.1,
            },
            "rrf_k": 11,
            "rerank_top_n": 7,
        }
    )
    prev = exp.apply_variant(variant)
    assert settings.RRF_K == 11
    exp.restore_settings(prev)
    assert settings.RANKING_WEIGHT_LLM == baseline["RANKING_WEIGHT_LLM"]
    assert settings.RRF_K == baseline["RRF_K"]
    assert settings.RERANK_TOP_N == baseline["RERANK_TOP_N"]


def test_experiment_harness_records_two_variants(tmp_path: Path, monkeypatch) -> None:
    sys.path.insert(0, str(ROOT / "backend"))
    sys.path.insert(0, str(ROOT))
    import scripts.experiment as exp

    out = tmp_path / "experiments.jsonl"
    monkeypatch.setattr(exp, "OUT", out)
    ensure_db()
    defaults_path = ROOT / "configs/experiments/defaults.json"
    no_mmr_path = ROOT / "configs/experiments/no_mmr.json"
    mtime_before = defaults_path.stat().st_mtime
    variants = [
        exp.normalize_variant(json.loads(defaults_path.read_text())),
        exp.normalize_variant(json.loads(no_mmr_path.read_text())),
    ]
    for variant in variants:
        ch = exp.config_hash(variant)
        prev = exp.apply_variant(variant)
        try:
            metrics, flags = exp.run_synthetic(variant)
        finally:
            exp.restore_settings(prev)
        exp.append_experiment(
            {
                "ts": "2020-01-01T00:00:00+00:00",
                "name": variant["name"],
                "config_hash": ch,
                "git_sha": "test",
                "variant": {k: variant[k] for k in exp.RESULT_PARAM_KEYS},
                "variant_flags": flags,
                "metrics": metrics,
            }
        )
    lines = out.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    assert defaults_path.stat().st_mtime == mtime_before  # observe-only: configs untouched
    by_name = {json.loads(L)["name"]: json.loads(L) for L in lines}
    assert by_name["defaults"]["variant_flags"]["use_mmr"] is True
    assert by_name["no_mmr"]["variant_flags"]["use_mmr"] is False
    assert by_name["defaults"]["metrics"]["mmr_companies_top10"] != by_name["no_mmr"]["metrics"][
        "mmr_companies_top10"
    ]


def _write_feedback_set(path: Path, *, n: int, invert: bool = False, bad_line: bool = False) -> None:
    rows = []
    for i in range(n):
        pos = i % 2 == 0
        if invert:
            pos = not pos
        kind = "thumbs_up" if pos else "thumbs_down"
        score = 90.0 - (i % 5) if pos else 40.0 + (i % 5)
        if invert:
            score = 40.0 if pos else 90.0
        rows.append(
            {
                "kind": kind,
                "relevance": 2.0 if pos else 0.0,
                "score_shown": score,
                "target_type": "job_match",
                "target_id": f"t{i}",
            }
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        if bad_line:
            fh.write("not-json\n")
        for r in rows:
            fh.write(json.dumps(r) + "\n")


def test_eval_ranking_feedback_insufficient_isolated(tmp_path: Path, monkeypatch) -> None:
    sys.path.insert(0, str(ROOT))
    import scripts.eval_ranking as er

    missing = tmp_path / "missing.jsonl"
    monkeypatch.setattr(er, "FEEDBACK_SET", missing)
    assert er.evaluate_feedback_suite() == 0

    short = tmp_path / "short.jsonl"
    _write_feedback_set(short, n=29)
    monkeypatch.setattr(er, "FEEDBACK_SET", short)
    # capture print via return only
    assert er.evaluate_feedback_suite() == 0


def test_eval_ranking_feedback_pass_and_fail(tmp_path: Path, monkeypatch) -> None:
    sys.path.insert(0, str(ROOT))
    import scripts.eval_ranking as er

    good = tmp_path / "good.jsonl"
    _write_feedback_set(good, n=30, invert=False, bad_line=True)
    monkeypatch.setattr(er, "FEEDBACK_SET", good)
    assert er.evaluate_feedback_suite() == 0

    bad = tmp_path / "bad.jsonl"
    _write_feedback_set(bad, n=30, invert=True)
    monkeypatch.setattr(er, "FEEDBACK_SET", bad)
    assert er.evaluate_feedback_suite() == 1


def test_weekly_threshold_gate(tmp_path: Path) -> None:
    sys.path.insert(0, str(ROOT))
    from scripts.eval_threshold_gate import check_ranking_thresholds

    floors = {"ndcg_at_10": 0.85, "mrr": 0.8}
    history = tmp_path / "history.jsonl"
    history.write_text(
        json.dumps({"suite": "ranking", "metrics": {"hybrid_ndcg10": 0.9, "hybrid_mrr": 0.9}})
        + "\n"
    )
    assert check_ranking_thresholds(history, floors) == []
    history.write_text(
        json.dumps({"suite": "ranking", "metrics": {"hybrid_ndcg10": 0.5, "hybrid_mrr": 0.5}})
        + "\n"
    )
    breaches = check_ranking_thresholds(history, floors)
    assert any("hybrid_ndcg10" in b for b in breaches)


def test_weekly_workflow_yaml_mentions_feedback_and_experiment() -> None:
    import yaml

    wf = yaml.safe_load((ROOT / ".github/workflows/weekly-eval.yml").read_text(encoding="utf-8"))
    jobs = wf["jobs"]
    assert "scope" in jobs
    weekly = jobs["weekly"]
    assert "scope" in (weekly.get("needs") or [])
    runs = "\n".join(
        step.get("run", "") for step in weekly.get("steps", []) if isinstance(step.get("run"), str)
    )
    assert "--suite feedback" in runs or "--suite all" in runs
    assert "experiment.py" in runs
    assert "eval_threshold_gate" in runs
    assert ".env" not in runs


def test_learning_file_stats_trends(tmp_path: Path) -> None:
    from app.services.feedback_store import learning_file_stats

    evals = tmp_path / "evals"
    evals.mkdir()
    (evals / "history.jsonl").write_text(
        json.dumps({"suite": "ranking", "metrics": {"hybrid_ndcg10": 0.8}, "ts": "1", "git_sha": "a"})
        + "\n"
        + json.dumps({"suite": "ranking", "metrics": {"hybrid_ndcg10": 0.9}, "ts": "2", "git_sha": "b"})
        + "\n"
        + "not-json\n"
    )
    (evals / "experiments.jsonl").write_text(
        "\n".join(json.dumps({"name": f"v{i}", "config_hash": str(i)}) for i in range(25)) + "\n"
    )
    stats = learning_file_stats(tmp_path)
    assert stats["evals_root"]
    suite = next(s for s in stats["suites"] if s["suite"] == "ranking")
    assert suite["trend"]["hybrid_ndcg10"]["delta"] == 0.1
    assert len(stats["experiments"]) == 20


def test_resolve_evals_root_env(monkeypatch, tmp_path: Path) -> None:
    from app.services import feedback_store

    evals = tmp_path / "evals"
    evals.mkdir()
    (evals / "thresholds.json").write_text("{}")
    monkeypatch.setattr(settings, "EVALS_DIR", str(tmp_path))
    assert feedback_store.resolve_evals_root() == tmp_path.resolve()


def test_run_feedback_suite_paths(tmp_path: Path, monkeypatch) -> None:
    sys.path.insert(0, str(ROOT))
    import scripts.experiment as exp

    monkeypatch.setattr(exp, "ROOT", tmp_path)
    # missing file
    assert exp.run_feedback_suite() is None
    # insufficient
    path = tmp_path / "evals" / "feedback_set.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"kind": "thumbs_up", "score_shown": 90}) + "\n")
    out = exp.run_feedback_suite()
    assert out is not None and out.get("insufficient") == 1.0
    # enough labels
    rows = []
    for i in range(30):
        kind = "thumbs_up" if i % 2 == 0 else "thumbs_down"
        rows.append(json.dumps({"kind": kind, "score_shown": 80 if kind == "thumbs_up" else 40}))
    path.write_text("\n".join(rows) + "\n")
    out = exp.run_feedback_suite()
    assert out is not None and out["label_count"] == 30.0
    assert out["pos"] + out["neg"] == 30.0


def test_threshold_gate_no_history(tmp_path: Path) -> None:
    sys.path.insert(0, str(ROOT))
    from scripts.eval_threshold_gate import check_ranking_thresholds

    assert check_ranking_thresholds(tmp_path / "missing.jsonl", {"ndcg_at_10": 0.85, "mrr": 0.8}) == []


def test_shared_ranking_config_hash_matches_experiment() -> None:
    sys.path.insert(0, str(ROOT))
    from app.services.ranking_config import live_ranking_params, ranking_config_hash
    from scripts.experiment import config_hash, normalize_variant

    live = live_ranking_params()
    variant = normalize_variant({"name": "from-live", **live})
    assert ranking_config_hash(live) == config_hash(variant)
    assert ranking_config_hash() == ranking_config_hash(live_ranking_params())
