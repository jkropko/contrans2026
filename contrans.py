import numpy as np
import pandas as pd
pd.options.mode.copy_on_write = True
import requests
import json
import dotenv
import os
import time
import yaml

class contrans:

# ENV variables and user agent
    def __init__(self):
        dotenv.load_dotenv()
        self.POSTGRES_PASSWORD = os.getenv('POSTGRES_PASSWORD')
        self.congresskey = os.getenv('congresskey')
        self.feckey = os.getenv('feckey')
        self.botname = 'contrans'
        self.version = '0.0'
        self.github = 'https://github.com/jkropko/contrans2026'
        self.useragent = f'{self.botname}/{self.version} ({self.github}) python-requests/{requests.__version__}'
        self.headers = {'User-Agent': self.useragent}

# Raw data acquisition
## build crosswalk with ideology
    def get_crosswalk(self, congress=119):
        url = f'https://voteview.com/static/data/out/members/HS{congress}_members.csv'
        ideology = pd.read_csv(url)

        cols_to_keep = ['bioname','chamber', 'nominate_dim1', 'party_code',
                        'state_abbrev','district_code','icpsr', 'bioguide_id']
        ideology = ideology[cols_to_keep]
        replace_map = {200: 'Republican', 
               100: 'Democrat',
               328: 'Independent'}
        ideology['party'] = ideology['party_code'].replace(replace_map)
        ideology = ideology.drop(['party_code'], axis=1)
        ideology = ideology.rename({'nominate_dim1': 'left_right_ideology'}, axis=1)

        # VoteView has no FEC IDs; congress-legislators lists them (one or more per member)
        legislators = self.get_legislators_yaml('legislators-current.yaml')
        fec_ids = pd.DataFrame([{'bioguide_id': x['id']['bioguide'],
                                 'fec_id': x['id'].get('fec')} for x in legislators])
        ideology = pd.merge(ideology, fec_ids, on='bioguide_id', how='left')
        ideology.to_parquet('data/raw/ideology.parquet', index=False)

## get biodata and terms
    def get_bio_data(self, bioguide_id):
        root = 'https://api.congress.gov/v3'
        endpoint = f'/member/{bioguide_id}'

        params = {'format': 'json', 'api_key': self.congresskey} 

        r = requests.get(root + endpoint, headers = self.headers, params = params)
        myjson = json.loads(r.text)['member']
        terms = myjson['terms'] 
        terms = pd.DataFrame(terms)
        terms['bioguide_id'] = bioguide_id
        try:
            terms['endYear'] = terms['endYear'].fillna(2027).astype(int)
        except: 
            terms['endYear'] = 2027
        termdata = terms[['bioguide_id','chamber', 'congress', 'stateCode', 'startYear', 'endYear']]
        try:
            termdata['district'] = terms['district']
        except:
            termdata['district'] = None
        member = {
            'bioguide_id': myjson['bioguideId'],
            'Full name':myjson['directOrderName'],
            'Chamber': myjson['terms'][-1]['chamber'],
            'State': myjson['state'],
            'Party': myjson['partyHistory'][-1]['partyName']}
        try:
            member['District'] = myjson['district']
        except:
            member['District'] = None
        try:
            member['birthYear'] = myjson['birthYear']
        except:
            pass
        try:
            member['image'] = myjson['depiction']['imageUrl']
        except:
            pass
        try:
            member['Office address'] = f'{myjson["addressInformation"]["officeAddress"]}, {myjson["addressInformation"]["city"]}, {myjson["addressInformation"]["district"]} {myjson["addressInformation"]["zipCode"]}'
            member['Phone'] = myjson['addressInformation']['phoneNumber']
            member['Website'] = myjson['officialWebsiteUrl']
        except:
            pass
        return termdata, member   

    def save_bio_terms(self):
        ideology = pd.read_parquet('data/raw/ideology.parquet')
        bioguide_ids = ideology['bioguide_id'].dropna().unique()
        memberlist = []
        termslist = []
        i = 0
        for bioguide_id in bioguide_ids:
            if i % 10 == 0:
                print(f'Now uploading legislator {i} ({bioguide_id}) of {len(bioguide_ids)}')
            terms, member = self.get_bio_data(bioguide_id)
            termslist.append(terms)
            memberlist.append(member)
            i += 1
        member = pd.DataFrame(memberlist)
        terms = pd.concat(termslist)
        member.to_parquet(f'data/raw/bioinfo.parquet', index=False)
        terms.to_parquet(f'data/raw/terms.parquet', index=False)

## vote similarity matrix
    def get_vote_similarity_data(self, congress=119):
        url = f'https://voteview.com/static/data/out/votes/HS{congress}_votes.csv'
        votes = pd.read_csv(url)
        votes = votes.drop(['congress', 'prob'], axis=1)
        vote_compare = pd.merge(votes, votes,
                        on = ['chamber', 'rollnumber'],
                        how = 'inner')
        vote_compare = vote_compare.query("icpsr_x != icpsr_y")
        vote_compare['agree'] = vote_compare['cast_code_x'] == vote_compare['cast_code_y']
        vote_compare = vote_compare.groupby(['icpsr_x', 'icpsr_y']).agg({'agree': 'mean'}).reset_index()
        crosswalk = pd.read_parquet('data/raw/ideology.parquet')
        vote_compare =pd.merge(vote_compare, crosswalk,
                left_on='icpsr_x',
                right_on='icpsr',
                how='inner')
        vote_compare = vote_compare[['bioname', 'icpsr_y', 'agree']]
        vote_compare =pd.merge(vote_compare, crosswalk,
                left_on='icpsr_y',
                right_on='icpsr',
                how='inner')
        vote_compare = vote_compare[['bioname_x', 'bioname_y', 'agree']]
        vote_compare = vote_compare.rename({'bioname_x': 'bioname',
                                        'bioname_y': 'comparison_member'}, axis=1)
        vote_compare.to_parquet('data/raw/vote_compare.parquet', index=False)

## Sponsored legislation

    def get_sponsored_legislation_member(self, bioguide_id, congress=119):
        root = 'https://api.congress.gov/v3'
        endpoint = f'/member/{bioguide_id}/sponsored-legislation'
        params = {'format': 'json',
                  'offset': 0,
                  'limit': 250,
                  'api_key': self.congresskey}

        legislation = []
        while True:
            r = requests.get(root + endpoint, headers=self.headers, params=params)
            if r.status_code == 429:   # rate limited: wait, then retry the same page
                time.sleep(60)
                continue
            r.raise_for_status()
            myjson = r.json()

            batch = myjson.get('sponsoredLegislation', [])
            legislation = legislation + batch

            total = myjson.get('pagination', {}).get('count')
            params['offset'] += params['limit']
            if len(batch) < params['limit'] or (total is not None and params['offset'] >= total):
                break

        s = [x for x in legislation if x.get('congress') == congress]
        s = [{k: v for k, v in x.items() if k in ['introducedDate', 'type', 'number', 'title', 'url']} for x in s]
        spons = pd.DataFrame(s)
        spons['bioguide_id'] = bioguide_id
        return spons

    def get_sponsored_legislation(self):
        sl_list = []
        failed = []
        ideology = pd.read_parquet('data/raw/ideology.parquet')
        bioguide_ids = ideology['bioguide_id'].dropna().unique()
        for i, bioguide_id in enumerate(bioguide_ids):
            if i % 10 == 0:
                print(f'Now uploading legislator {i} ({bioguide_id}) of {len(bioguide_ids)}')
            try:
                spons = self.get_sponsored_legislation_member(bioguide_id)
                sl_list.append(spons)
            except requests.HTTPError as e:
                print(f'Skipping {bioguide_id}: {e}')
                failed.append(bioguide_id)
        spons = pd.concat(sl_list)
        spons.to_parquet('data/raw/sponsored_legislation.parquet', index=False)
        if failed:
            print(f'{len(failed)} members failed: {failed}')

## Bill summaries
    def get_bill_summaries(self, congress=119):
        root = 'https://api.congress.gov/v3'
        endpoint = f'/summaries/{congress}'
        # without a date window this endpoint returns only the last day's summaries;
        # a Congress begins January 3 of odd year (1789 + 2 * (congress - 1)), e.g. 2025 for the 119th
        start_year = 1789 + 2 * (congress - 1)
        now = pd.Timestamp.now(tz='UTC').strftime('%Y-%m-%dT%H:%M:%SZ')
        params = {'format': 'json',
                  'offset': 0,
                  'limit': 250,
                  'sort': 'updateDate asc',   # requests encodes the space as '+'
                  'fromDateTime': f'{start_year}-01-01T00:00:00Z',
                  'toDateTime': now,
                  'api_key': self.congresskey}

        sum_list = []
        while True:
            r = requests.get(root + endpoint, headers=self.headers, params=params)
            if r.status_code == 429:   # rate limited: wait, then retry the same page
                time.sleep(60)
                continue
            r.raise_for_status()
            myjson = r.json()

            batch = myjson.get('summaries', [])
            sum_list = sum_list + batch

            total = myjson.get('pagination', {}).get('count')
            print(f'{len(sum_list)} of {total} summaries')
            params['offset'] += params['limit']
            if len(batch) < params['limit'] or (total is not None and params['offset'] >= total):
                break

        summaries = pd.json_normalize(sum_list)
        summaries = summaries.drop_duplicates()
        summaries.to_parquet(f'data/raw/bill_summaries_{congress}.parquet', index=False)

## Committees
    def get_legislators_yaml(self, filename):
        url = f'https://raw.githubusercontent.com/unitedstates/congress-legislators/main/{filename}'
        r = requests.get(url, headers=self.headers)
        r.raise_for_status()
        return yaml.safe_load(r.text)

    def get_committees(self):
        committees_yaml = self.get_legislators_yaml('committees-current.yaml')
        committee_list = []
        for c in committees_yaml:
            committee_list.append({'committee_code': c['thomas_id'],
                                   'committee_name': c['name'],
                                   'parent_code': c['thomas_id'],
                                   'subcommittee': False,
                                   'chamber': c['type'].capitalize(),
                                   'url': c.get('url')})
            for s in c.get('subcommittees', []):
                committee_list.append({'committee_code': c['thomas_id'] + s['thomas_id'],
                                       'committee_name': s['name'],
                                       'parent_code': c['thomas_id'],
                                       'subcommittee': True,
                                       'chamber': c['type'].capitalize(),
                                       'url': None})
        committees = pd.DataFrame(committee_list)
        committees.to_parquet('data/raw/committees.parquet', index=False)
        return committees

    def get_committee_membership(self):
        membership_yaml = self.get_legislators_yaml('committee-membership-current.yaml')
        member_list = []
        for committee_code, members in membership_yaml.items():
            for m in members:
                member_list.append({'committee_code': committee_code,
                                    'bioguide_id': m['bioguide'],
                                    'party': m.get('party'),
                                    'rank': m.get('rank'),
                                    'title': m.get('title')})
        membership = pd.DataFrame(member_list)
        membership.to_parquet('data/raw/committee_members.parquet', index=False)
        return membership

## FEC
    def get_schedule_e(self, fec_id, cycle=2026):
        root = 'https://api.open.fec.gov'
        endpoint = '/v1/schedules/schedule_e/'
        params = {'api_key': self.feckey,
                    'candidate_id': fec_id,
                    'cycle': cycle,
                    'most_recent': True,
                    'per_page': 100}

        results = []
        while True:
            r = requests.get(root + endpoint, params=params, headers=self.headers)
            if r.status_code == 429:   # rate limited: wait, then retry the same page
                print('Rate limited by FEC; waiting 60 seconds')
                time.sleep(60)
                continue
            r.raise_for_status()
            myjson = r.json()

            batch = myjson['results']
            if len(batch) == 0:
                break
            results.extend(batch)
            print(f'{fec_id}: {len(results)} of about {myjson["pagination"]["count"]} expenditures')

            # copy whatever cursor keys the API hands back; it swaps last_expenditure_date
            # for sort_null_only=True once it reaches records with no date
            params.pop('last_expenditure_date', None)
            params.update(myjson['pagination']['last_indexes'])

        schedule_e = pd.json_normalize(results)
        schedule_e['fec_id'] = fec_id
        return schedule_e

    def get_all_schedule_e(self, cycle=2026, fec_col='fec_id', save_every=25):
        ideology = pd.read_parquet('data/raw/ideology.parquet')

        # one row per FEC ID; explode() splits list cells (members who ran for more than one office)
        ids = ideology[['bioguide_id', fec_col]].explode(fec_col)
        ids = ids.rename({fec_col: 'fec_id'}, axis=1)
        ids = ids.dropna(subset=['fec_id']).drop_duplicates(subset=['fec_id'])

        # pick up where a previous run left off
        outfile = f'data/raw/schedule_e_{cycle}.parquet'
        try:
            schedule_e = pd.read_parquet(outfile)
            ids = ids[~ids['fec_id'].isin(schedule_e['fec_id'])]
            sche_list = [schedule_e]
        except FileNotFoundError:
            sche_list = []
        print(f'{len(ids)} FEC IDs still to download')

        failed = []
        for i, (bioguide_id, fec_id) in enumerate(zip(ids['bioguide_id'], ids['fec_id'])):
            print(f'Now downloading FEC ID {i + 1} of {len(ids)} ({fec_id})')
            try:
                newdata = self.get_schedule_e(fec_id, cycle=cycle)
            except requests.HTTPError as e:
                print(f'Skipping {fec_id}: {e}')
                failed.append(fec_id)
                continue
            newdata['bioguide_id'] = bioguide_id
            sche_list.append(newdata)
            if (i + 1) % save_every == 0:   # checkpoint so a crash doesn't lose everything
                pd.concat(sche_list, ignore_index=True).to_parquet(outfile, index=False)

        schedule_e = pd.concat(sche_list, ignore_index=True)
        schedule_e.to_parquet(outfile, index=False)
        if failed:
            print(f'{len(failed)} FEC IDs failed; rerun to retry them: {failed}')
        return schedule_e