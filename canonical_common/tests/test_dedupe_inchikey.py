import pandas as pd
from canonical_common.canonical_db import dedupe_by_inchikey


def test_dedupe_by_inchikey_duplicate_column_labels_no_crash():
    df = pd.DataFrame(
        [
            ["AAAAAAAAAAAAAA-UHFFFAOYSA-N", 1, None],
            ["AAAAAAAAAAAAAA-UHFFFAOYSA-N", None, 3],
        ],
        columns=["inchi_key", "dup", "dup"],
    )

    out = dedupe_by_inchikey(df)

    assert len(out) == 1
    assert "dup" in out.columns
    # "first row wins; later rows fill blanks"
    assert float(out.loc[0, "dup"]) == 1.0
