import pandas as pd

from canonical_common.cas_registry_adapters import incoming_from_resolver


def test_incoming_from_resolver_preserves_mixture_type_and_maps_status():
    df_res = pd.DataFrame([
        # single substance should not force mixture/uvcb
        {"cas": "64-17-5", "inchikey": "ETOH-KEY-1234", "cas_validity": "valid", "mixture_type": "single substance"},
        # unknown should not force mixture/uvcb
        {"cas": "67-56-1", "inchikey": "MEOH-KEY-0001", "cas_validity": "valid", "mixture_type": "unknown"},
        # uvcb
        {"cas": "90000-00-0", "inchikey": "", "cas_validity": "valid", "mixture_type": "natural product / UVCB"},
        # mixtures
        {"cas": "80000-00-0", "inchikey": "", "cas_validity": "valid", "mixture_type": "fragrance mixture"},
        {"cas": "60000-00-0", "inchikey": "", "cas_validity": "valid", "mixture_type": "polymer / complex mixture"},
        {"cas": "123-45-6", "inchikey": "", "cas_validity": "valid", "mixture_type": "mixture (multi-component structure)"},
    ])

    inc = incoming_from_resolver(df_res)

    # mixture_type must be preserved
    assert "mixture_type" in inc.columns
    assert inc["mixture_type"].astype(str).tolist() == df_res["mixture_type"].astype(str).tolist()

    # cas_number_normalized must be populated from 'cas'
    assert inc["cas_number_normalized"].astype(str).tolist()[0] == "64-17-5"

    # status mapping
    statuses = inc["cas_status"].astype(str).str.lower().tolist()
    assert statuses[0] == "valid"     # single substance -> keep base validity
    assert statuses[1] == "valid"     # unknown -> keep base validity
    assert statuses[2] == "uvcb"      # natural product / UVCB -> uvcb
    assert statuses[3] == "mixture"   # fragrance mixture -> mixture
    assert statuses[4] == "mixture"   # polymer / complex mixture -> mixture
    assert statuses[5] == "mixture"   # mixture (multi-component structure) -> mixture