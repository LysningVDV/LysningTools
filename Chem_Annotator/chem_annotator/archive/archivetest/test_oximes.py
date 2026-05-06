import pytest

OXIME_CASES = [
    ("COC(=O)c1ccccc1N=C(C)O", 1),
    ("COC(=O)c1ccccc1N=CO",    1),
    ("CC(C)=NO",               1),
]

@pytest.mark.parametrize("smi, expected", OXIME_CASES)
def test_oxime_exclusion(run, smi, expected):
    result = run(smi)
    assert result["OximeCount"] == expected
    assert result["TotalAlcoholCount"] == 0
    