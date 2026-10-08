import pytest

from app.services import risk


def test_matrix_is_exhaustive_and_banded():
    expected = {
        (lk, c): ("LOW" if lk * c <= 4 else "MEDIUM" if lk * c <= 9 else "HIGH" if lk * c <= 16 else "CRITICAL")
        for lk in range(1, 6)
        for c in range(1, 6)
    }
    for (lk, c), band in expected.items():
        r = risk.assess(lk, c)
        assert r.score == lk * c
        assert r.band == band
        assert r.matrix_version == risk.MATRIX_VERSION
        assert str(r.score) in r.rationale and band in r.rationale


@pytest.mark.parametrize(
    ("lk", "c", "band"),
    [(1, 4, "LOW"), (1, 5, "MEDIUM"), (3, 3, "MEDIUM"), (2, 5, "HIGH"), (4, 4, "HIGH"), (4, 5, "CRITICAL")],
)
def test_band_boundaries(lk, c, band):
    assert risk.assess(lk, c).band == band


@pytest.mark.parametrize("bad", [0, 6, -1, 2.5, "3", None, True])
def test_invalid_inputs_rejected(bad):
    with pytest.raises(ValueError):
        risk.assess(bad, 3)
    with pytest.raises(ValueError):
        risk.assess(3, bad)


def test_deterministic():
    assert all(risk.assess(4, 3) == risk.assess(4, 3) for _ in range(50))
    assert risk.matrix() == risk.matrix()
