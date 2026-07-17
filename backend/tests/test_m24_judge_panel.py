"""M24: model override, panel majority, cache keys, max pairs, grounding, flag-off identity."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.core.config import settings
from app.schemas.jobs import Job
from app.services import observability
from app.services.resume.jd_decompose import JdRequirement
from app.services.resume.tournament import (
    AlignmentEvidence,
    agreement_label,
    argument_grounded,
    majority_from_votes,
    maybe_run_tournament,
    pairwise_cache_key,
    select_pairs_by_gap,
)


def _job() -> Job:
    return Job(
        id="j1",
        source="t",
        source_job_id="s1",
        title="ML Engineer",
        company="Co",
        location="Remote",
        description="Need PyTorch and MLflow.",
        apply_url="https://ex.com/j",
        skills=["PyTorch"],
    )


def _ev(rid: str, cov: float, ch: str | None = None, rows: list | None = None) -> AlignmentEvidence:
    return AlignmentEvidence(
        resume_id=rid,
        content_hash=ch or rid,
        coverage=cov,
        top_units=[f"evidence for {rid}"],
        alignment_rows=rows
        or [
            {
                "kind": "must",
                "requirement": "PyTorch",
                "evidence_unit": f"built {rid} with PyTorch",
                "status": "hit",
                "strength": "strong",
            }
        ],
        filename=f"{rid}.pdf",
    )


def test_estimate_cost_finite_default_and_panel_model() -> None:
    d = observability.estimate_llm_cost_usd(model=settings.LLM_MODEL, input_tokens=1000, output_tokens=500)
    p = observability.estimate_llm_cost_usd(model="deepseek-ai/DeepSeek-V3.2", input_tokens=1000, output_tokens=500)
    assert d > 0 and p > 0 and isinstance(d, float)


def test_complete_model_override_body_and_trace(monkeypatch) -> None:
    from app.services.inference import llm as llm_mod

    monkeypatch.setattr(settings, "LLM_API_KEY", "k")
    monkeypatch.setattr(settings, "LLM_API_BASE", "https://example.test/v1")
    monkeypatch.setattr(settings, "LLM_MODEL", "gpt-4o-mini")
    captured: dict = {}

    class FakeResp:
        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": "ok"}}], "usage": {"prompt_tokens": 10, "completion_tokens": 5}}

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, url, headers=None, json=None):
            captured["json"] = json
            return FakeResp()

    with patch("app.services.inference.llm.httpx.Client", FakeClient):
        with patch("app.services.inference.llm.observability.traced_call") as tc:

            class Ctx:
                input_tokens = 0
                output_tokens = 0
                cost_usd = 0.0

                def __enter__(self):
                    return self

                def __exit__(self, *a):
                    return False

            def _traced(*a, **kw):
                captured["trace_model"] = kw.get("model")
                return Ctx()

            tc.side_effect = _traced
            out = llm_mod.complete("hi", model="deepseek-ai/DeepSeek-V3.2", operation="pairwise_judge")
    assert out == "ok"
    assert captured["json"]["model"] == "deepseek-ai/DeepSeek-V3.2"
    assert captured["trace_model"] == "deepseek-ai/DeepSeek-V3.2"


def test_complete_default_model_when_omitted(monkeypatch) -> None:
    from app.services.inference import llm as llm_mod

    monkeypatch.setattr(settings, "LLM_API_KEY", "k")
    monkeypatch.setattr(settings, "LLM_API_BASE", "https://example.test/v1")
    monkeypatch.setattr(settings, "LLM_MODEL", "gpt-4o-mini")
    captured: dict = {}

    class FakeResp:
        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": "ok"}}], "usage": {"prompt_tokens": 10, "completion_tokens": 5}}

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, url, headers=None, json=None):
            captured["json"] = json
            return FakeResp()

    with patch("app.services.inference.llm.httpx.Client", FakeClient):
        with patch("app.services.inference.llm.observability.traced_call") as tc:

            class Ctx:
                input_tokens = 0
                output_tokens = 0
                cost_usd = 0.0

                def __enter__(self):
                    return self

                def __exit__(self, *a):
                    return False

            tc.return_value = Ctx()
            llm_mod.complete("hi", operation="llm")
    assert captured["json"]["model"] == "gpt-4o-mini"


def test_single_judge_cache_key_unchanged_shape() -> None:
    # Pre-M24: no model suffix — identity for flag-off
    k1 = pairwise_cache_key("jd", "ha", "hb", None)
    k2 = pairwise_cache_key("jd", "hb", "ha", "")
    k3 = pairwise_cache_key("jd", "ha", "hb", "model-a")
    assert k1 == k2
    assert k3 != k1


def test_majority_unanimous_decisive_and_split_slight() -> None:
    w, m, r = majority_from_votes([("a", "slight"), ("a", "decisive"), ("a", "slight")])
    assert w == "a" and m == "decisive" and r == 1.0
    w2, m2, r2 = majority_from_votes([("a", "decisive"), ("a", "slight"), ("b", "decisive")])
    assert w2 == "a" and m2 == "slight" and abs(r2 - 2 / 3) < 1e-9
    assert "2/3" in (agreement_label(r2, 3) or "")
    assert "3/3" in (agreement_label(1.0, 3) or "")


def test_select_pairs_max_closest_gap() -> None:
    contested = [_ev("a", 0.90), _ev("b", 0.89), _ev("c", 0.88), _ev("d", 0.50)]
    # 6 pairs total; max 2 keeps closest coverage pairs
    pairs = select_pairs_by_gap(contested, 2)
    assert len(pairs) == 2
    gaps = [abs(x.coverage - y.coverage) for x, y in pairs]
    assert max(gaps) <= abs(0.90 - 0.88) + 1e-9


def test_panel_majority_and_independent_flip(monkeypatch) -> None:
    monkeypatch.setattr(settings, "JUDGE_PANEL_MODELS", "m1,m2,m3")
    monkeypatch.setattr(settings, "PAIRWISE_PANEL_MAX_PAIRS", 6)
    monkeypatch.setattr(settings, "ADVERSARIAL_CRITIQUE", False)
    reqs = [JdRequirement(text="PyTorch", kind="must", category="skill", weight=2.0)]
    ordered = [_ev("a", 0.90, "ha"), _ev("b", 0.88, "hb")]
    calls: list[str | None] = []
    flips_seen: list[bool] = []

    def fake_complete_json(prompt, schema, **kwargs):
        calls.append(kwargs.get("llm_model"))
        flips_seen.append("Resume A (b.pdf)" in prompt)
        # Map A/B to resume ids from prompt labels; m1+m2 prefer a, m3 prefers b
        model = kwargs.get("llm_model") or ""
        prefer = "b" if model.endswith("m3") else "a"
        # Which side is preferred resume?
        # filenames are a.pdf / b.pdf from _ev
        left_is_a = "Resume A (a.pdf)" in prompt
        if prefer == "a":
            winner = "A" if left_is_a else "B"
        else:
            winner = "B" if left_is_a else "A"
        return schema(
            winner=winner,
            margin="decisive",
            key_differences=["clearer PyTorch production evidence"],
            reason="decisive unit on must-have PyTorch evidence",
        )

    with patch("app.services.resume.tournament.llm.complete_json", side_effect=fake_complete_json):
        with patch("app.services.resume.tournament.load_prompt") as lp:
            lp.return_value = MagicMock(
                body="Judge which resume is better.",
                system="json",
                version="1",
                content_hash="ph",
                name="pairwise_judge",
                model_params={},
            )
            result = maybe_run_tournament(_job(), reqs, ordered, use_llm=True, db=None)
    assert result.ran and result.comparisons == 1
    assert result.pairwise_winners[("a", "b")] == "a"
    assert result.pairwise_margins[("a", "b")] == "slight"
    assert abs((result.judge_agreement_mean or 0) - 2 / 3) < 1e-9
    assert set(calls) == {"m1", "m2", "m3"}
    assert len(calls) == 3


def test_panel_max_pairs_cap(monkeypatch) -> None:
    monkeypatch.setattr(settings, "JUDGE_PANEL_MODELS", "m1")
    monkeypatch.setattr(settings, "PAIRWISE_PANEL_MAX_PAIRS", 1)
    monkeypatch.setattr(settings, "ADVERSARIAL_CRITIQUE", False)
    reqs = [JdRequirement(text="PyTorch", kind="must", category="skill", weight=2.0)]
    ordered = [_ev("a", 0.90, "ha"), _ev("b", 0.89, "hb"), _ev("c", 0.88, "hc")]
    calls = {"n": 0}

    def fake_complete_json(prompt, schema, **kwargs):
        calls["n"] += 1
        return schema(
            winner="A",
            margin="decisive",
            key_differences=["clearer PyTorch production evidence"],
            reason="decisive unit on must-have PyTorch evidence",
        )

    with patch("app.services.resume.tournament.llm.complete_json", side_effect=fake_complete_json):
        with patch("app.services.resume.tournament.load_prompt") as lp:
            lp.return_value = MagicMock(
                body="Judge", system="json", version="1", content_hash="ph", name="pairwise_judge", model_params={}
            )
            result = maybe_run_tournament(_job(), reqs, ordered, use_llm=True, db=None)
    assert result.comparisons == 1  # capped
    assert calls["n"] == 1  # one panel model × one pair


def test_flag_off_single_judge_one_call(monkeypatch) -> None:
    monkeypatch.setattr(settings, "JUDGE_PANEL_MODELS", "")
    monkeypatch.setattr(settings, "ADVERSARIAL_CRITIQUE", False)
    reqs = [JdRequirement(text="PyTorch", kind="must", category="skill", weight=2.0)]
    ordered = [_ev("a", 0.90, "ha"), _ev("b", 0.88, "hb")]
    calls = {"n": 0, "models": []}

    def fake_complete_json(prompt, schema, **kwargs):
        calls["n"] += 1
        calls["models"].append(kwargs.get("llm_model"))
        return schema(
            winner="A",
            margin="decisive",
            key_differences=["clearer PyTorch production evidence"],
            reason="decisive unit on must-have PyTorch evidence",
        )

    with patch("app.services.resume.tournament.llm.complete_json", side_effect=fake_complete_json):
        with patch("app.services.resume.tournament.load_prompt") as lp:
            lp.return_value = MagicMock(
                body="Judge", system="json", version="1", content_hash="ph", name="pairwise_judge", model_params={}
            )
            result = maybe_run_tournament(_job(), reqs, ordered, use_llm=True, db=None)
    assert calls["n"] == 1 and calls["models"] == [None]
    assert result.panel_models == [] and result.adversarial is None


def test_advocate_grounding() -> None:
    from app.services.resume.tournament import evidence_phrases

    ev = _ev(
        "a",
        0.9,
        rows=[
            {
                "kind": "must",
                "requirement": "distributed systems",
                "evidence_unit": "built production pytorch serving on k8s",
                "status": "hit",
                "strength": "strong",
            }
        ],
    )
    phrases = evidence_phrases(ev)
    assert "distributed systems" not in phrases  # JD requirement alone is not grounding
    assert argument_grounded("This resume built production pytorch serving on k8s at scale.", phrases)
    # Invented claim that only name-drops the requirement label must fail
    assert not argument_grounded("Led distributed systems olympics with no real evidence unit text.", phrases)
    assert not argument_grounded("Won three olympic medals in fencing.", phrases)
    assert not argument_grounded("", phrases)


def test_adversarial_off_no_extra_calls(monkeypatch) -> None:
    monkeypatch.setattr(settings, "JUDGE_PANEL_MODELS", "")
    monkeypatch.setattr(settings, "ADVERSARIAL_CRITIQUE", False)
    from app.services.resume.tournament import maybe_run_adversarial_critique

    assert maybe_run_adversarial_critique(_job(), [], [_ev("a", 0.9), _ev("b", 0.88)]) is None


def test_adversarial_on_returns_critique_with_dual_models(monkeypatch) -> None:
    """Drive maybe_run_adversarial_critique on real path with stub LLM."""
    monkeypatch.setattr(settings, "ADVERSARIAL_CRITIQUE", True)
    monkeypatch.setattr(settings, "JUDGE_PANEL_MODELS", "model-adv-a,model-adv-b,model-verdict")
    monkeypatch.setattr(settings, "LLM_MODEL", "default-model")
    from app.services.resume.tournament import maybe_run_adversarial_critique

    a = _ev(
        "a",
        0.90,
        "ha",
        rows=[
            {
                "kind": "must",
                "requirement": "PyTorch",
                "evidence_unit": "shipped pytorch training pipeline in prod",
                "status": "hit",
                "strength": "strong",
            }
        ],
    )
    b = _ev(
        "b",
        0.88,
        "hb",
        rows=[
            {
                "kind": "must",
                "requirement": "PyTorch",
                "evidence_unit": "ran pytorch notebooks for research",
                "status": "hit",
                "strength": "solid",
            }
        ],
    )
    calls: list[tuple[str | None, str]] = []

    def fake_complete_json(prompt, schema, **kwargs):
        model = kwargs.get("llm_model")
        op_hint = "advocate" if "arguing FOR" in prompt or "Alignment evidence" in prompt else "judge"
        calls.append((model, op_hint))
        name = getattr(schema, "__name__", str(schema))
        if "Advocate" in name or (hasattr(schema, "model_fields") and "argument" in schema.model_fields):
            # cite real evidence unit from whichever resume is in the prompt
            if "shipped pytorch training pipeline" in prompt:
                arg = "Strong fit: shipped pytorch training pipeline in prod for this role."
            else:
                arg = "Solid fit: ran pytorch notebooks for research with clear ownership."
            return schema(argument=arg)
        # verdict pairwise
        left_is_a = "Resume A (a.pdf)" in prompt
        # prefer a
        winner = "A" if left_is_a else "B"
        return schema(
            winner=winner,
            margin="decisive",
            key_differences=["clearer production pytorch pipeline evidence"],
            reason="decisive unit on shipped pytorch training pipeline in prod",
        )

    with patch("app.services.resume.tournament.llm.complete_json", side_effect=fake_complete_json):
        with patch("app.services.resume.tournament.load_prompt") as lp:

            def _load(name):
                if name == "advocate":
                    return MagicMock(
                        body="Argue FOR resume.",
                        system="json",
                        version="1",
                        content_hash="ah",
                        name="advocate",
                        model_params={},
                    )
                return MagicMock(
                    body="Judge pair.",
                    system="json",
                    version="1",
                    content_hash="ph",
                    name="pairwise_judge",
                    model_params={},
                )

            lp.side_effect = _load
            crit = maybe_run_adversarial_critique(
                _job(), [JdRequirement(text="PyTorch", kind="must", category="skill", weight=2.0)], [a, b], db=None
            )
    assert crit is not None
    assert crit.side_a_resume_id == "a" and crit.side_b_resume_id == "b"
    assert "pytorch" in crit.side_a_argument.lower()
    assert "pytorch" in crit.side_b_argument.lower()
    assert crit.verdict_winner_resume_id == "a"
    assert crit.side_a_model != crit.side_b_model or crit.verdict_model  # dual models assigned
    models_used = {m for m, _ in calls if m}
    assert len(models_used) >= 2
    assert any("advocate" == h for _, h in calls)
    assert any("judge" == h for _, h in calls)


def test_adversarial_grounding_reject_skips_critique(monkeypatch) -> None:
    monkeypatch.setattr(settings, "ADVERSARIAL_CRITIQUE", True)
    monkeypatch.setattr(settings, "JUDGE_PANEL_MODELS", "m1,m2,m3")
    from app.services.resume.tournament import maybe_run_adversarial_critique

    a = _ev("a", 0.9, "ha")
    b = _ev("b", 0.88, "hb")

    def ungrounded(prompt, schema, **kwargs):
        if hasattr(schema, "model_fields") and "argument" in schema.model_fields:
            return schema(argument="Led distributed systems olympics inventing claims not in rows.")
        return schema(
            winner="A", margin="decisive", key_differences=["x" * 30], reason="decisive unit on must-have evidence here"
        )

    with patch("app.services.resume.tournament.llm.complete_json", side_effect=ungrounded):
        with patch("app.services.resume.tournament.load_prompt") as lp:
            lp.return_value = MagicMock(
                body="body", system="json", version="1", content_hash="h", name="advocate", model_params={}
            )
            crit = maybe_run_adversarial_critique(_job(), [], [a, b], db=None)
    assert crit is None  # fail closed


def test_out_tournament_meta_not_process_global(monkeypatch) -> None:
    """Critique/meta must come from out_tournament bucket for this call only."""
    monkeypatch.setattr(settings, "JUDGE_PANEL_MODELS", "")
    monkeypatch.setattr(settings, "ADVERSARIAL_CRITIQUE", False)
    from app.api.routers.library import _tournament_response_fields
    from app.services.resume.tournament import AdversarialCritique, TournamentResult

    # Empty recs + None meta → no critique
    fields = _tournament_response_fields([], None)
    assert fields["adversarial_critique"] is None
    # Explicit meta with critique → present
    adv = AdversarialCritique(
        side_a_resume_id="a1",
        side_a_filename="a.pdf",
        side_a_model="m1",
        side_a_argument="arg a with enough words for display",
        side_b_resume_id="b1",
        side_b_filename="b.pdf",
        side_b_model="m2",
        side_b_argument="arg b with enough words for display",
        verdict_winner_resume_id="a1",
        verdict_winner_filename="a.pdf",
        verdict_model="m3",
        verdict_reason="clearer evidence",
        verdict_margin="decisive",
    )
    tmeta = TournamentResult(ran=True, ordered_ids=["a1", "b1"], adversarial=adv)
    fields2 = _tournament_response_fields([], tmeta)
    assert fields2["adversarial_critique"] is not None
    assert fields2["adversarial_critique"].side_a_resume_id == "a1"
    # Without tmeta, no leak even if prior call had critique
    fields3 = _tournament_response_fields([], None)
    assert fields3["adversarial_critique"] is None
