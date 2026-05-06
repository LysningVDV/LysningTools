import pytest
from chem_annotator.aggregator import features_for_smiles


@pytest.fixture
def run():
    """
    Convenience wrapper to call features_for_smiles.
    """
    def _run(smiles: str):
        return features_for_smiles(smiles)
    return _run