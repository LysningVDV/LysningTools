import pytest

CASES = [
    ("NO",        "N–OH should be excluded"),
    ("CS(=O)O",   "S–OH should be excluded"),
    ("OP(=O)(O)O","P–OH should be excluded"),
    ("[Na]O",     "metal–OH should be excluded"),
]

@pytest.mark.parametrize("smi, description", CASES)
def test_heteroatom_bound_oh(run, smi, description):
    r = run(smi)
    assert r["TotalAlcoholCount"] == 0, f"{smi}: {description}"
    