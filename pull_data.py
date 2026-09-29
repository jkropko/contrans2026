"""
pull_data.py -- run the whole acquisition pipeline and save everything.

    python pull_data.py                     # everything, into data/raw
    python pull_data.py --out /tmp/pull     # somewhere else
    python pull_data.py --limit 10          # first 10 members only, for testing
    python pull_data.py --skip votes        # leave out the slow one
    python pull_data.py --only crosswalk ideology
    python pull_data.py --fec                 # FEC data only

Two of these steps loop over members, so they make one request per
member and take several minutes for a full Congress. Use --limit while
you are developing; it is the difference between 20 seconds and 20
minutes.

The expenditures step does NOT loop -- it pulls the whole cycle in one
go and filters afterwards. Asking the FEC per candidate needs about
1,500 requests against a limit of 1,000 an hour.
"""

import argparse
import re
import sys
import time

import pandas as pd

from contrans import Contrans


# The steps this script can run, in the order they appear below.
ALL_STEPS = ["crosswalk", "committees", "ideology", "votes",
             "members", "member_details", "sponsored", "expenditures"]

# Named groups, so you don't have to remember which steps belong together.
# The FEC pull needs the crosswalk, because the expenditures come back for
# every federal candidate in the cycle and the crosswalk is how we work out
# which of them are sitting members.
GROUPS = {
    "fec": ["crosswalk", "expenditures"],
}


def log(message):
    """Print with a timestamp, flushed, so a long run shows progress."""
    print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)


def pull_member_details(ct, bioguide_ids):
    """Call get_member() once per member and stack the results.

    The detail endpoint returns nested terms and party history, so we
    keep the whole record flattened rather than picking columns now --
    deciding what matters is a later problem.
    """
    rows = []
    for i, bid in enumerate(bioguide_ids, 1):
        try:
            rows.append(ct.get_member(bid))
        except Exception as e:
            log(f"    skipped {bid}: {e}")
        if i % 50 == 0:
            log(f"    {i} of {len(bioguide_ids)}")
    return pd.json_normalize(rows)


def pull_sponsored(ct, bioguide_ids):
    """Call get_sponsored_legislation() once per member and stack."""
    frames = []
    for i, bid in enumerate(bioguide_ids, 1):
        try:
            df = ct.get_sponsored_legislation(bid)
            if not df.empty:
                frames.append(df)
        except Exception as e:
            log(f"    skipped {bid}: {e}")
        if i % 50 == 0:
            log(f"    {i} of {len(bioguide_ids)}")
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def fec_ids_from_crosswalk(crosswalk, bioguide_ids=None):
    """Pull FEC candidate ids out of the crosswalk, as a flat set.

    One member has several ids -- one per office and cycle they ran for
    -- and congress-legislators packs them into a single field. Split on
    commas AND whitespace, because the separator is not guaranteed and a
    missed split sends "H6FL11126,H6FL11134" as one id, which matches
    nothing and fails silently.
    """
    df = crosswalk
    if bioguide_ids is not None:
        df = df[df["bioguide_id"].isin(bioguide_ids)]
    ids = set()
    for value in df["fec_ids"].dropna():
        for piece in re.split(r"[,\s]+", str(value).strip()):
            if piece:
                ids.add(piece)
    return ids


def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", default="data/raw",
                        help="where to write the parquet files")
    parser.add_argument("--congress", type=int, default=119)
    parser.add_argument("--cycle", type=int, default=2026,
                        help="FEC two-year cycle")
    parser.add_argument("--limit", type=int, default=None,
                        help="only this many members, for testing")
    parser.add_argument("--skip", nargs="*", default=[],
                        help="step names to leave out")
    parser.add_argument("--only", nargs="*", default=None,
                        help="run only these steps: " + ", ".join(ALL_STEPS))
    parser.add_argument("--fec", action="store_true",
                        help="shorthand for --only " + " ".join(GROUPS["fec"]))
    args = parser.parse_args()

    if args.fec:
        if args.only:
            parser.error("use --fec or --only, not both")
        args.only = GROUPS["fec"]

    if args.only:
        unknown = [n for n in args.only if n not in ALL_STEPS]
        if unknown:
            parser.error(f"unknown step(s): {', '.join(unknown)}. "
                         f"Choose from: {', '.join(ALL_STEPS)}")

    ct = Contrans(data_dir=args.out)

    def wanted(name):
        if args.only is not None:
            return name in args.only
        return name not in args.skip

    log(f"writing to {args.out}")
    saved = {}

    # -- the standalone pulls, in increasing order of how long they take

    if wanted("crosswalk"):
        log("crosswalk (congress-legislators)")
        crosswalk = ct.get_crosswalk()
        saved["crosswalk"] = ct.save(crosswalk, "crosswalk")
        log(f"  {len(crosswalk)} rows")
    else:
        crosswalk = None

    if wanted("committees"):
        log("committee assignments (congress-legislators)")
        committees = ct.get_committee_assignments()
        saved["committees"] = ct.save(committees, "committee_assignments")
        log(f"  {len(committees)} rows")

    if wanted("ideology"):
        log("ideology (Voteview)")
        ideology = ct.get_ideology(args.congress)
        saved["ideology"] = ct.save(ideology, "ideology")
        log(f"  {len(ideology)} rows")

    if wanted("votes"):
        log("votes (Voteview) -- this one is large")
        votes = ct.get_votes(args.congress)
        saved["votes"] = ct.save(votes, "votes")
        log(f"  {len(votes)} rows")

    # -- the member list, which the loops below depend on

    members = None
    if wanted("members") or wanted("member_details") or wanted("sponsored"):
        log("member list (Congress.gov)")
        members = ct.get_members(args.congress)
        if args.limit:
            members = members.head(args.limit)
            log(f"  limited to {len(members)} members")
        if wanted("members"):
            saved["members"] = ct.save(members, "members")
        log(f"  {len(members)} rows")

    bioguide_ids = []
    if members is not None and "bioguideId" in members.columns:
        bioguide_ids = members["bioguideId"].dropna().unique().tolist()

    # -- the loops: one request per member, so these are the slow ones

    if wanted("member_details") and bioguide_ids:
        log(f"member details -- {len(bioguide_ids)} requests")
        details = pull_member_details(ct, bioguide_ids)
        saved["member_details"] = ct.save(details, "member_details")
        log(f"  {len(details)} rows")

    if wanted("sponsored") and bioguide_ids:
        log(f"sponsored legislation -- {len(bioguide_ids)} requests")
        sponsored = pull_sponsored(ct, bioguide_ids)
        saved["sponsored"] = ct.save(sponsored, "sponsored_legislation")
        log(f"  {len(sponsored)} rows")

    if wanted("expenditures"):
        log(f"independent expenditures ({args.cycle} cycle, House and Senate)")
        expenditures = ct.get_independent_expenditures(cycle=args.cycle)
        log(f"  {len(expenditures)} rows before filtering")

        # Filter to our members. The API gives us every federal candidate
        # for the cycle; we only want the ones currently serving.
        if crosswalk is None:
            try:
                crosswalk = ct.load("crosswalk")
            except FileNotFoundError:
                log("  no crosswalk available -- keeping all candidates")
        if crosswalk is not None and "candidate_id" in expenditures.columns:
            # bioguide_ids is empty when we did not pull the member list --
            # for instance on a --fec run. In that case keep every member
            # in the crosswalk rather than filtering to nobody.
            keep = fec_ids_from_crosswalk(
                crosswalk, bioguide_ids if bioguide_ids else None)
            expenditures = expenditures[expenditures["candidate_id"].isin(keep)]
            log(f"  {len(expenditures)} rows after filtering to {len(keep)} ids")

        saved["expenditures"] = ct.save(expenditures, "independent_expenditures")

    # -- summary

    log("done")
    for name, path in saved.items():
        print(f"    {name:20} {path}")

    if not saved:
        print("nothing was written -- check your --only and --skip arguments",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
