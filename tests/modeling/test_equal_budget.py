"""Ticket: prove oldest/random (and every other method) get the same network length."""


def test_every_method_gets_the_same_length_budget(evaluation):
    for (_, _), rows in evaluation.year_table.groupby(["test_year", "budget"]):
        assert rows["budget_length_m"].nunique() == 1
        assert rows["eligible_segments"].nunique() == 1
        assert (rows["selected_length_m"] <= rows["budget_length_m"]).all()


def test_no_method_leaves_more_than_one_segment_of_budget_unused(evaluation):
    longest = evaluation.predictions.groupby("test_year")["length_m"].max()
    table = evaluation.year_table
    unused = table["budget_length_m"] - table["selected_length_m"]
    assert (unused < table["test_year"].map(longest)).all()


def test_oldest_and_random_rank_the_same_segments(evaluation):
    for _, rows in evaluation.predictions.groupby("test_year"):
        oldest = set(rows.loc[rows["method"] == "oldest", "segment_id"])
        random_ = set(rows.loc[rows["method"] == "random", "segment_id"])
        assert oldest == random_
