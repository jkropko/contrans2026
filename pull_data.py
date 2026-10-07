"""Run every raw data pull for the Congress Transparency Dashboard.

Usage (from the project root, where .env and data/ live):
    python pull_data.py                         # run every step
    python pull_data.py committees schedule_e   # run only the named steps

Every file lands in data/raw/. The crosswalk runs first because the other
pulls read data/raw/ideology.parquet to get the list of members.
"""

import os
import sys
import time

from contrans import contrans

ct = contrans()

# (name, method to call, does everything after it depend on this step?)
steps = [
    ('crosswalk',             ct.get_crosswalk,              True),
    ('bio_terms',             ct.save_bio_terms,             False),
    ('vote_similarity',       ct.get_vote_similarity_data,   False),
    ('sponsored_legislation', ct.get_sponsored_legislation,  False),
    ('bill_summaries',        ct.get_bill_summaries,         False),
    ('committees',            ct.get_committees,             False),
    ('committee_membership',  ct.get_committee_membership,   False),
    ('schedule_e',            ct.get_all_schedule_e,         False),
]


def main():
    requested = sys.argv[1:]
    known = [name for name, _, _ in steps]
    unknown = [name for name in requested if name not in known]
    if unknown:
        print(f'Unknown step(s): {unknown}. Choose from: {known}')
        sys.exit(1)

    os.makedirs('data/raw', exist_ok=True)

    results = {}
    for name, method, required in steps:
        if requested and name not in requested:
            continue
        print(f'\n=== {name} ===')
        start = time.time()
        try:
            method()
            results[name] = f'done in {time.time() - start:.0f}s'
        except Exception as e:
            # one failed source shouldn't stop the others
            results[name] = f'FAILED: {type(e).__name__}: {e}'
            if required:
                print(f'{name} failed and later steps depend on it; stopping.')
                break

    print('\n=== Summary ===')
    for name, outcome in results.items():
        print(f'{name:<24} {outcome}')

    if any(outcome.startswith('FAILED') for outcome in results.values()):
        sys.exit(1)


if __name__ == '__main__':
    main()
