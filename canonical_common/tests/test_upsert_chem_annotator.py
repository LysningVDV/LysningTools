import pandas as pd
from canonical_common.canonical_db import upsert_canonical


def test_upsert_chem_annotator_writes_counts_and_zeros():
    allowlist = ["inchi_key", "TotalAlcoholCount", "AldehydeCount"]

    k1 = "AAAAAAAAAAAAAA-UHFFFAOYSA-N"
    k2 = "BBBBBBBBBBBBBB-UHFFFAOYSA-N"

    existing = pd.DataFrame(
        {
            "inchi_key": [k1, k2],
            "TotalAlcoholCount": [pd.NA, pd.NA],
            "AldehydeCount": [pd.NA, pd.NA],
        }
    )

    incoming = pd.DataFrame(
        {
            "inchi_key": [k1, k2],
            "TotalAlcoholCount": [0, 2],  # important: 0 must be written
            "AldehydeCount": [1, 0],
        }
    )

    out = upsert_canonical(existing, incoming, tool_name="chem_annotator", allowlist=allowlist)
    out = out.set_index("inchi_key")

    assert int(out.loc[k1, "TotalAlcoholCount"]) == 0
    assert int(out.loc[k2, "TotalAlcoholCount"]) == 2
    assert int(out.loc[k1, "AldehydeCount"]) == 1
    assert int(out.loc[k2, "AldehydeCount"]) == 0

def test_upsert_drops_invalid_inchikeys():
    allowlist = ["inchi_key", "TotalAlcoholCount"]
    existing = pd.DataFrame({"inchi_key": ["K1"], "TotalAlcoholCount": [pd.NA]})
    incoming = pd.DataFrame({"inchi_key": ["K1"], "TotalAlcoholCount": [2]})
    out = upsert_canonical(existing, incoming, "chem_annotator", allowlist)
    assert out.empty
