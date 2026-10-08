"""Tests for engine/belief.py (spec §§8-11)."""

from __future__ import annotations

import pytest

from arf_rt.config import (
    MAX_EDGE_MASS,
    MAX_TEMPLATE_MASS,
    SATURATION_ALPHA_ALLOW,
    SATURATION_ALPHA_DENY,
    SATURATION_BETA_ALLOW,
    SATURATION_BETA_DENY,
)
from arf_rt.engine.belief import (
    apply_mass_cap,
    classify_polarity,
    compute_increment,
    get_base_w_q,
    get_saturation_values,
    is_template_eligible,
)
from arf_rt.util.canon import ARFValidationError


# ===================================================================
# get_base_w_q
# ===================================================================


class TestGetBaseWQ:
    """Spec §9.2: base_w_q lookup by ObservationStrength."""

    def test_deterministic(self) -> None:
        assert get_base_w_q("DETERMINISTIC") == 100

    def test_direct(self) -> None:
        assert get_base_w_q("DIRECT") == 95

    def test_inferred(self) -> None:
        assert get_base_w_q("INFERRED") == 60

    def test_heuristic(self) -> None:
        assert get_base_w_q("HEURISTIC") == 30

    def test_all_strengths_covered(self) -> None:
        """All four spec strengths are present."""
        results = {
            s: get_base_w_q(s)
            for s in ["DETERMINISTIC", "DIRECT", "INFERRED", "HEURISTIC"]
        }
        assert len(results) == 4
        assert all(isinstance(v, int) for v in results.values())

    def test_unknown_strength_raises(self) -> None:
        with pytest.raises(ARFValidationError, match="Unknown strength"):
            get_base_w_q("BOGUS")

    def test_empty_string_raises(self) -> None:
        with pytest.raises(ARFValidationError):
            get_base_w_q("")


# ===================================================================
# compute_increment
# ===================================================================


class TestComputeIncrement:
    """Spec §9.2: inc = floor(base_w_q * signal_q / 100)."""

    def test_direct_80(self) -> None:
        # floor(95 * 80 / 100) = floor(76.0) = 76
        assert compute_increment(95, 80) == 76

    def test_direct_90(self) -> None:
        # floor(95 * 90 / 100) = floor(85.5) = 85
        assert compute_increment(95, 90) == 85

    def test_deterministic_100(self) -> None:
        assert compute_increment(100, 100) == 100

    def test_heuristic_50(self) -> None:
        # floor(30 * 50 / 100) = floor(15.0) = 15
        assert compute_increment(30, 50) == 15

    def test_zero_signal(self) -> None:
        assert compute_increment(95, 0) == 0

    def test_integer_floor_behavior(self) -> None:
        # floor(60 * 33 / 100) = floor(19.8) = 19
        assert compute_increment(60, 33) == 19


# ===================================================================
# classify_polarity
# ===================================================================


class TestClassifyPolarity:
    """Spec §10: Polarity classification."""

    def test_allow_is_support(self) -> None:
        assert classify_polarity("ALLOW", "UNKNOWN") == "SUPPORT"

    def test_allow_any_reason_is_support(self) -> None:
        for rc in ["UNKNOWN", "CONSTRAINT_DENY", "MISSING_PERMISSION"]:
            assert classify_polarity("ALLOW", rc) == "SUPPORT"

    def test_deny_constraint_deny_is_against(self) -> None:
        assert classify_polarity("DENY", "CONSTRAINT_DENY") == "AGAINST"

    def test_deny_missing_permission_is_against(self) -> None:
        assert classify_polarity("DENY", "MISSING_PERMISSION") == "AGAINST"

    def test_deny_condition_mismatch_is_neutral(self) -> None:
        assert classify_polarity("DENY", "CONDITION_MISMATCH") == "NEUTRAL"

    def test_deny_unknown_is_neutral(self) -> None:
        assert classify_polarity("DENY", "UNKNOWN") == "NEUTRAL"

    def test_deny_transient_is_neutral(self) -> None:
        assert classify_polarity("DENY", "TRANSIENT") == "NEUTRAL"

    def test_deny_throttled_is_neutral(self) -> None:
        assert classify_polarity("DENY", "THROTTLED") == "NEUTRAL"

    def test_error_is_neutral(self) -> None:
        assert classify_polarity("ERROR", "UNKNOWN") == "NEUTRAL"

    def test_inconclusive_is_neutral(self) -> None:
        assert classify_polarity("INCONCLUSIVE", "UNKNOWN") == "NEUTRAL"


# ===================================================================
# get_saturation_values
# ===================================================================


class TestGetSaturationValues:
    """Spec §9.3: DETERMINISTIC saturation."""

    def test_allow_saturation(self) -> None:
        alpha, beta, status, frozen = get_saturation_values("ALLOW")
        assert alpha == SATURATION_ALPHA_ALLOW  # 9900
        assert beta == SATURATION_BETA_ALLOW    # 100
        assert status == "CONFIRMED"
        assert frozen == 1

    def test_deny_saturation(self) -> None:
        alpha, beta, status, frozen = get_saturation_values("DENY")
        assert alpha == SATURATION_ALPHA_DENY   # 100
        assert beta == SATURATION_BETA_DENY     # 9900
        assert status == "REFUTED"
        assert frozen == 1

    def test_error_raises(self) -> None:
        with pytest.raises(ARFValidationError, match="ALLOW or DENY"):
            get_saturation_values("ERROR")

    def test_inconclusive_raises(self) -> None:
        with pytest.raises(ARFValidationError):
            get_saturation_values("INCONCLUSIVE")


# ===================================================================
# apply_mass_cap
# ===================================================================


class TestApplyMassCap:
    """Spec §9.5: Mass cap renormalization."""

    def test_under_cap_unchanged(self) -> None:
        assert apply_mass_cap(100, 50, MAX_EDGE_MASS) == (100, 50)

    def test_exactly_at_cap_unchanged(self) -> None:
        assert apply_mass_cap(10000, 10000, MAX_EDGE_MASS) == (10000, 10000)

    def test_over_cap_renormalized(self) -> None:
        # mass = 25000 > 20000
        # new_alpha = max(1, floor(15000 * 20000 / 25000)) = max(1, 12000) = 12000
        # new_beta = max(1, 20000 - 12000) = 8000
        alpha, beta = apply_mass_cap(15000, 10000, MAX_EDGE_MASS)
        assert alpha == 12000
        assert beta == 8000
        assert alpha + beta == MAX_EDGE_MASS

    def test_mass_cap_deterministic(self) -> None:
        """Same inputs always produce same outputs."""
        for _ in range(10):
            a, b = apply_mass_cap(15000, 10000, MAX_EDGE_MASS)
            assert (a, b) == (12000, 8000)

    def test_minimum_one_enforced(self) -> None:
        """Even with extreme skew, both values >= 1."""
        alpha, beta = apply_mass_cap(30000, 1, 100)
        assert alpha >= 1
        assert beta >= 1
        assert alpha + beta == 100

    def test_template_mass_cap(self) -> None:
        # Template cap = 200000
        alpha, beta = apply_mass_cap(150000, 100000, MAX_TEMPLATE_MASS)
        assert alpha + beta == MAX_TEMPLATE_MASS

    def test_zero_alpha_handled(self) -> None:
        alpha, beta = apply_mass_cap(0, 25000, MAX_EDGE_MASS)
        assert alpha >= 1
        assert beta >= 1


# ===================================================================
# is_template_eligible
# ===================================================================


class TestIsTemplateEligible:
    """Spec §11.1: Template aggregation eligibility."""

    def test_direct_allow_eligible(self) -> None:
        assert is_template_eligible(0, "DIRECT", "ALLOW") is True

    def test_direct_deny_eligible(self) -> None:
        assert is_template_eligible(0, "DIRECT", "DENY") is True

    def test_deterministic_allow_eligible(self) -> None:
        assert is_template_eligible(0, "DETERMINISTIC", "ALLOW") is True

    def test_inferred_deny_eligible(self) -> None:
        assert is_template_eligible(0, "INFERRED", "DENY") is True

    def test_heuristic_not_eligible(self) -> None:
        """HEURISTIC does NOT update templates (spec §11.1)."""
        assert is_template_eligible(0, "HEURISTIC", "ALLOW") is False
        assert is_template_eligible(0, "HEURISTIC", "DENY") is False

    def test_counterfactual_not_eligible(self) -> None:
        assert is_template_eligible(1, "DIRECT", "ALLOW") is False

    def test_error_result_not_eligible(self) -> None:
        assert is_template_eligible(0, "DIRECT", "ERROR") is False

    def test_inconclusive_not_eligible(self) -> None:
        assert is_template_eligible(0, "DIRECT", "INCONCLUSIVE") is False
