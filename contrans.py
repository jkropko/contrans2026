"""
contrans.py -- data acquisition for the Congress Transparency Dashboard

Eight things we need, in one place.

The idea of a class: all of our requests need the same two things -- a
user agent, so the server knows who is calling, and an API key. Rather
than repeating that in every script, we write it once in `get()` and
every data method below calls it.

    from contrans import Contrans

    ct = Contrans()
    members = ct.get_members()
    ct.save(members, "members")
"""

import io
import os
import time

import dotenv
import pandas as pd
import requests
import yaml

dotenv.load_dotenv()

# The FEC wants a state alongside office=house, so we loop. Territories
# are included because the House seats non-voting delegates from them.
STATES = [
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
    "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
    "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
    "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
    "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
    "DC", "PR", "VI", "GU", "AS", "MP",
]


class Contrans:

    def __init__(self, botname="ds6600", version="0.1", data_dir="data/raw",
                 pace=0.0):
        self.botname = botname
        self.version = version
        self.data_dir = data_dir
        self.pace = pace              # seconds to wait between requests
        self.rate_limit = None        # set after each request, from headers
        self.rate_remaining = None
        os.makedirs(data_dir, exist_ok=True)

    # =================================================================
    # Setup: the things every request needs
    # =================================================================

    def useragent(self):
        """Identify our code to the servers we call."""
        return f"{self.botname}/{self.version} python-requests/{requests.__version__}"

    def headers(self, api_key=None):
        """Headers for a request. Pass a key and it goes in a header.

        Keys belong in headers, not in the URL. A key in the query string
        ends up in tracebacks, server logs, and browser history -- and
        requests puts the full URL into the error it raises, so one failed
        call prints your credential to the terminal.
        """
        h = {"User-Agent": self.useragent()}
        if api_key:
            h["X-Api-Key"] = api_key
        return h

    def key(self, name):
        """Read one API key from the .env file.

        We raise instead of returning None: a request sent with an empty
        key fails later, and more confusingly, than this does.
        """
        value = os.getenv(name)
        if not value:
            raise KeyError(
                f"{name} not found. Add a line to your .env file:\n"
                f"    {name}=your_key_here\n"
                f"and check that .env is in the directory you are running from.")
        return value

    def congress_key(self):
        """The Congress.gov key, from CONGRESS_API_KEY in .env."""
        return self.key("CONGRESS_API_KEY")

    def fec_key(self):
        """The openFEC key, from FEC_API_KEY in .env.

        Kept separate from the Congress key on purpose. Falling back to
        the other one would be worse than failing: a key the FEC does not
        recognise comes back as a 403, which reads like a permissions
        problem rather than a missing variable, and you would go looking
        in the wrong place.

        If you happen to be using one key for both, set both variables to
        the same value.
        """
        return self.key("FEC_API_KEY")

    def get(self, url, params=None, api_key=None):
        """Make one request and return the parsed JSON.

        We don't use raise_for_status(). It raises on the status code and
        throws away the response body -- but for a 4xx the body is where
        the server tells you which parameter it did not like. Losing that
        turns a two-minute fix into an afternoon.

        It also puts the full URL in the error message, which leaks the
        key if the key is in the query string. Ours is in a header, and
        the message below is built by hand so it cannot leak either.
        """
        if self.pace:
            time.sleep(self.pace)
        response = requests.get(url, params=params,
                                headers=self.headers(api_key), timeout=30)
        # api.data.gov reports your remaining budget on every response.
        # Worth watching: it is how you find out you are nearly out
        # BEFORE the request that fails.
        self.rate_limit = response.headers.get("X-RateLimit-Limit")
        self.rate_remaining = response.headers.get("X-RateLimit-Remaining")
        if not response.ok:
            raise requests.HTTPError(
                f"{response.status_code} {response.reason} from {url}\n"
                f"  params: { {k: v for k, v in (params or {}).items()} }\n"
                f"  server said: {response.text[:600]}",
                response=response)
        return response.json()

    # =================================================================
    # Pagination: two flavors, because the two APIs differ
    # =================================================================

    def get_offset_pages(self, url, params=None, limit=250, max_pages=None,
                         api_key=None):
        """Congress.gov style: rows 0-249, then 250-499, and so on.

        max_pages is a seatbelt against a loop that never ends, not a
        quota. Leave it as None to keep going until a short page tells
        us we are done.
        """
        params = dict(params or {})
        pages = []
        i = 0
        while max_pages is None or i < max_pages:
            i += 1
            params["limit"] = limit
            params["offset"] = (i - 1) * limit
            page = self.get(url, params, api_key=api_key)
            pages.append(page)
            if self.count_records(page) < limit:
                break
        return pages

    def get_fec_pages(self, url, params=None, per_page=100, max_pages=None):
        """FEC style: ask for the rows AFTER a particular row.

        Offset pagination is a bet that the data isn't changing. Filings
        arrive continuously, so a row inserted between requests shifts
        everything after it and you miss records.
        """
        params = dict(params or {})
        params["per_page"] = per_page
        pages = []
        i = 0
        while max_pages is None or i < max_pages:
            i += 1
            page = self.get(url, params, api_key=self.fec_key())
            pages.append(page)
            after = page.get("pagination", {}).get("last_indexes")
            if not after:
                break
            params.update(after)
        return pages

    def count_records(self, page):
        """How many records came back in one page response."""
        if "results" in page:
            return len(page["results"])
        for value in page.values():
            if isinstance(value, list):
                return len(value)
        return 0

    # =================================================================
    # 1 and 2. Voteview (bulk CSV, no key)
    # =================================================================

    def _voteview(self, kind, congress):
        tag = "HSall" if congress is None else f"HS{congress}"
        url = f"https://voteview.com/static/data/out/{kind}/{tag}_{kind}.csv"
        response = requests.get(url, headers=self.headers(), timeout=120)
        response.raise_for_status()
        # icpsr and state codes are identifiers, not numbers. Read as
        # integers they lose leading zeros, and you can do arithmetic on
        # a code number, which you never want to be able to do.
        return pd.read_csv(io.BytesIO(response.content),
                           dtype={"icpsr": "string",
                                  "state_icpsr": "string",
                                  "district_code": "string"})

    def get_ideology(self, congress=119):
        """1. Ideology scores from Voteview. One row per member per congress.

        The DW-NOMINATE columns are nominate_dim1 (liberal to conservative)
        and nominate_dim2. Also carries bioguide_id, which is the free half
        of our crosswalk.

        Note: NOMINATE is re-estimated over the whole history whenever new
        votes are added, so a member who cast no new votes can still have a
        different score after a refresh.
        """
        return self._voteview("members", congress)

    def get_votes(self, congress=119):
        """2. Every vote cast. One row per member per roll call.

        The full history is millions of rows. Pass a congress number.
        """
        return self._voteview("votes", congress)

    # =================================================================
    # 3 and 4. Congress.gov member data
    # =================================================================

    def get_members(self, congress=119):
        """3. Every member of a Congress. One row each, with bioguideId.

        This is the list we loop over for everything member-specific.
        """
        url = f"https://api.congress.gov/v3/member/congress/{congress}"
        pages = self.get_offset_pages(
            url, {"format": "json"}, api_key=self.congress_key())
        records = [m for page in pages for m in page.get("members", [])]
        return pd.json_normalize(records)

    def get_member(self, bioguide_id):
        """4. One member in detail: terms, party history, leadership roles.

        The list endpoint gives a summary; tenure has to be computed from
        the terms, which only appear here. One call per member.
        """
        url = f"https://api.congress.gov/v3/member/{bioguide_id}"
        page = self.get(url, {"format": "json"},
                        api_key=self.congress_key())
        return page.get("member", {})

    # =================================================================
    # 5. Committee assignments -- NOT from Congress.gov
    # =================================================================

    def get_committee_assignments(self):
        """5. Which members sit on which committees.

        Congress.gov does not provide this, in either direction:

          /member/{bioguideId}          has no committee field
          /committee/{chamber}/{code}   returns bills, reports,
                                        communications, subcommittees,
                                        history, type -- no roster

        Verified against /committee/house/hsju00, which returns 74,379
        bills referred to House Judiciary and 15 subcommittees, and not
        one member. The API models a committee as something bills flow
        through, not as a group of people. That is a defensible design
        and it is simply not the question we are asking.

        So this comes from congress-legislators instead -- the same
        project as the crosswalk in method 7. One row per member per
        committee.
        """
        url = ("https://unitedstates.github.io/congress-legislators/"
               "committee-membership-current.yaml")
        response = requests.get(url, headers=self.headers(), timeout=60)
        response.raise_for_status()
        data = yaml.safe_load(response.text)

        rows = []
        for committee_id, members in data.items():
            for member in members:
                rows.append({"committee_id": committee_id,
                             "bioguide_id": member.get("bioguide"),
                             "name": member.get("name"),
                             "party": member.get("party"),
                             "title": member.get("title"),
                             "rank": member.get("rank")})
        return pd.DataFrame(rows)

    # =================================================================
    # 6. Sponsored legislation, with summaries
    # =================================================================

    def get_sponsored_legislation(self, bioguide_id, max_pages=None):
        """6a. Bills a member sponsored. One row per bill."""
        url = f"https://api.congress.gov/v3/member/{bioguide_id}/sponsored-legislation"
        pages = self.get_offset_pages(
            url, {"format": "json"}, limit=250, max_pages=max_pages,
            api_key=self.congress_key())
        records = [b for page in pages
                   for b in page.get("sponsoredLegislation", [])]
        df = pd.json_normalize(records)
        if not df.empty:
            df["sponsor_bioguide_id"] = bioguide_id
        return df

    def get_bill_summary(self, congress, bill_type, bill_number):
        """6b. CRS summaries for one bill.

        Summaries are a separate endpoint, so this is ONE CALL PER BILL.
        A member with 40 bills costs 40 requests on top of the one above.
        Across 535 members that is tens of thousands of requests, so pull
        the sponsored lists first and decide which bills you actually need
        summaries for.
        """
        url = (f"https://api.congress.gov/v3/bill/{congress}/"
               f"{bill_type.lower()}/{bill_number}/summaries")
        page = self.get(url, {"format": "json"},
                        api_key=self.congress_key())
        return pd.json_normalize(page.get("summaries", []))

    # =================================================================
    # 7. The crosswalk
    # =================================================================

    def get_crosswalk(self):
        """7. Identifier crosswalk from unitedstates/congress-legislators.

        One row per member, with bioguide, ICPSR, and FEC candidate ids
        among others. This is what lets us join Congress.gov to Voteview
        and to the FEC.

        Note the FEC column: a member can have several FEC candidate ids,
        one per office and cycle they ran for, so that column holds a list
        rather than a single value.
        """
        url = ("https://unitedstates.github.io/congress-legislators/"
               "legislators-current.csv")
        response = requests.get(url, headers=self.headers(), timeout=60)
        response.raise_for_status()
        return pd.read_csv(io.BytesIO(response.content),
                           dtype={"bioguide_id": "string",
                                  "icpsr_id": "string",
                                  "fec_ids": "string"})

    # =================================================================
    # 8. FEC independent expenditures
    # =================================================================

    def get_independent_expenditures(self, candidate_ids, cycle=2026,
                                     verbose=True):
        """8. Money spent to support or oppose candidates, by candidate.

        Returns (dataframe, remaining_ids).

        One request per candidate, roughly 540 of them. If the API rate
        limits us part way through we stop and hand back what we have
        plus the ids we did not reach, so an interrupted run costs you
        nothing and you can pick up where you stopped.

        Whatever your limit happens to be, self.rate_remaining carries
        what the server last reported, so you can watch the budget rather
        than assume a number.

        Getting to candidate_id took five rejections from this endpoint,
        each of which said what was missing:

            no filter        -> "Must include candidate_id or office"
            office="H"       -> "Must be one of: house, senate, president"
            office="house"   -> "Must include argument 'state'"
            + state="AL"     -> "Must include argument 'district'"

        Office plus state plus district is 435 House requests and a
        district table to maintain. candidate_id was the other branch the
        first error offered, and it needs no lookup tables.

        Pass only the ids you need. Members hold several each -- one per
        office and cycle they have run for -- so filter to the chamber
        they serve in now.
        """
        url = "https://api.open.fec.gov/v1/schedules/schedule_e/by_candidate/"
        candidate_ids = list(candidate_ids)
        frames = []
        for i, cid in enumerate(candidate_ids):
            try:
                pages = self.get_fec_pages(
                    url, {"cycle": cycle, "candidate_id": cid})
            except requests.HTTPError as e:
                status = getattr(e.response, "status_code", None)
                if status != 429:
                    raise
                remaining = candidate_ids[i:]
                limit = self.rate_limit or "?"
                print(f"    rate limited after {i} candidates; "
                      f"{len(remaining)} left to fetch "
                      f"(your key allows {limit} per window)", flush=True)
                if not self.pace:
                    print("    tip: re-run with --pace to stay under the "
                          "limit instead of hitting it", flush=True)
                df = (pd.concat(frames, ignore_index=True)
                      if frames else pd.DataFrame())
                return df, remaining

            records = [r for page in pages for r in page.get("results", [])]
            if records:
                frames.append(pd.json_normalize(records))
            if verbose and (i + 1) % 50 == 0:
                left = self.rate_remaining
                note = f", {left} calls left this hour" if left else ""
                print(f"    {i + 1} of {len(candidate_ids)} candidates{note}",
                      flush=True)

        df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
        return df, []

    def get_expenditures_for_candidate(self, candidate_id, cycle=2026):
        """8b. Every individual expenditure for ONE candidate.

        Use this for a drill-down -- who spent it, on what, when -- not
        for the whole roster. One call per candidate is how you run out
        of requests.
        """
        url = "https://api.open.fec.gov/v1/schedules/schedule_e/"
        pages = self.get_fec_pages(
            url, {"candidate_id": candidate_id, "cycle": cycle})
        records = [r for page in pages for r in page.get("results", [])]
        df = pd.json_normalize(records)
        if not df.empty:
            df["candidate_id_queried"] = candidate_id
        return df

    # =================================================================
    # Saving
    # =================================================================

    def save(self, df, name):
        """Write a dataframe to Parquet.

        Parquet, not CSV, because it carries the column types with it. A
        CSV round trip turns "00123" into 123 and loses the zeros.
        """
        path = os.path.join(self.data_dir, name + ".parquet")
        df.to_parquet(path, index=False)
        return path

    def load(self, name):
        return pd.read_parquet(os.path.join(self.data_dir, name + ".parquet"))
