"""
Validation checks for the sample data.

These run offline against data/sample/. Replace the specifics with your
own schema, your own relationships, and your own edge cases -- the shape
of each check is what to keep.

Run with:  pytest
"""

from pathlib import Path

import pandas as pd
import pytest
from pandera.pandas import Check, Column, DataFrameSchema

SAMPLE = Path(__file__).resolve().parents[1] / "data" / "sample"

VALID_STATES = {
    "AL","AK","AZ","AR","CA","CO","CT","DE","FL","GA","HI","ID","IL","IN",
    "IA","KS","KY","LA","ME","MD","MA","MI","MN","MS","MO","MT","NE","NV",
    "NH","NJ","NM","NY","NC","ND","OH","OK","OR","PA","RI","SC","SD","TN",
    "TX","UT","VT","VA","WA","WV","WI","WY",
    # Territories and DC belong here too -- forgetting them is a classic
    # way to write a check that fails on correct data.
    "DC","PR","VI","GU","AS","MP",
}


@pytest.fixture(scope="module")
def members():
    return pd.read_csv(SAMPLE / "members_sample.csv")


@pytest.fixture(scope="module")
def facts():
    return pd.read_csv(SAMPLE / "facts_sample.csv")


# ---------------------------------------------------------------------
# CHECK 1 -- schema, types, and ranges
# Catches: a bad parse, a source adding an unexpected value, a null that
# silently turns an integer column into floats.
# ---------------------------------------------------------------------

members_schema = DataFrameSchema(
    {
        "id": Column(str, unique=True, nullable=False),
        "name": Column(str, nullable=False),
        "state": Column(str, Check.isin(VALID_STATES), nullable=False),
        "party": Column(str, Check.isin({"D", "R", "I"}), nullable=False),
        # Nullable on purpose: not every record has a score, and the sample
        # includes one that doesn't.
        "score": Column(float, Check.in_range(-1.0, 1.0), nullable=True),
        "joined": Column(str, nullable=False),
    },
    strict=True,   # fails if an unexpected column appears
    coerce=True,
)


def test_members_schema(members):
    members_schema.validate(members)


# ---------------------------------------------------------------------
# CHECK 2 -- referential integrity
# Catches: an entity resolution defect. If your crosswalk quietly dropped
# records, this is where you find out -- not from empty dashboard panels.
# ---------------------------------------------------------------------

def test_every_fact_has_a_member(members, facts):
    orphans = set(facts["id"]) - set(members["id"])
    assert not orphans, f"facts reference unknown ids: {sorted(orphans)}"


# ---------------------------------------------------------------------
# CHECK 3 -- idempotency
# Catches: an "upsert" that is really an append. Load twice, count rows.
# Replace the fake loader with your real one.
# ---------------------------------------------------------------------

def _load(target: pd.DataFrame, incoming: pd.DataFrame) -> pd.DataFrame:
    """Stand-in for your real load step. Yours should upsert on a key."""
    combined = pd.concat([target, incoming], ignore_index=True)
    return combined.drop_duplicates(subset=["id"], keep="last")


def test_loading_twice_changes_nothing(members):
    once = _load(members.iloc[0:0], members)
    twice = _load(once, members)
    assert len(once) == len(twice), "second load changed the row count"


# ---------------------------------------------------------------------
# CHECK 4 -- reconcile against an external total
# Catches: double counting. This is the only check that tests whether you
# are RIGHT rather than merely internally consistent, so it is worth having
# even when it is awkward to write.
# ---------------------------------------------------------------------

PUBLISHED_TOTALS = {"A000001": 2045.50}   # from the source's own published figures


def test_totals_match_published_figures(facts):
    for entity_id, expected in PUBLISHED_TOTALS.items():
        actual = facts.loc[facts["id"] == entity_id, "amount"].sum()
        assert actual == pytest.approx(expected, rel=0.01), (
            f"{entity_id}: computed {actual}, source publishes {expected}"
        )
