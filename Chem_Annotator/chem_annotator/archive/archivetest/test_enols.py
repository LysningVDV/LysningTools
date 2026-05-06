
def test_enols_are_alcohols_and_enols(run):
    r = run("C=CO")

    assert r["EnolicOHCount"] == 1
    assert r["TotalAlcoholCount"] == 1
    assert r["PrimaryAlcoholCount"] == 1  # correct for vinyl alcohol
    assert r["PhenolCount"] == 0