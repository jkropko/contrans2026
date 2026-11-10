# conda install -n ds6600 prefect

from contrans import contrans
from prefect import flow, task
import subprocess

ct = contrans()

# Tasks
## Raw data extraction
extract_ideology = task(ct.get_ideology, name='extract_ideology', retries=2, retry_delay_seconds=60)
extract_bio_terms = task(ct.save_bio_terms, name='extract_bio_terms', retries=2, retry_delay_seconds=60)
extract_vote_similarity = task(ct.get_vote_similarity_data, name='extract_vote_similarity', retries=2, retry_delay_seconds=60)
extract_sponsored_legislation = task(ct.get_sponsored_legislation, name='extract_sponsored_legislation', retries=2, retry_delay_seconds=60)
extract_bill_summaries = task(ct.get_bill_summaries, name='extract_bill_summaries', retries=2, retry_delay_seconds=60)
extract_committees = task(ct.get_committees, name='extract_committees', retries=2, retry_delay_seconds=60)
extract_committee_membership = task(ct.get_committee_membership, name='extract_committee_membership', retries=2, retry_delay_seconds=60)
extract_schedule_e = task(ct.get_all_schedule_e, name='extract_schedule_e', retries=2, retry_delay_seconds=60)

## Data wrangling into 3NF
make_members = task(ct.make_members, name='make_members')
make_crosswalk = task(ct.make_crosswalk, name='make_crosswalk')
make_terms = task(ct.make_terms, name='make_terms')
make_bills = task(ct.make_bills, name='make_bills')
make_expenditures = task(ct.make_expenditures, name='make_expenditures')
make_others = task(ct.make_others, name='make_others')

## Launch docker
@task
def docker_launch():
    result = subprocess.run(['docker', 'compose', 'up', '-d', '--wait', 'postgres'], capture_output=True, text=True)
    print(result.stdout + result.stderr)
    result.check_returncode()

## Create new Postgres DB if contrans DB does not exist (GitHub actions always starts from scratch)

## Upload processed data to postgres
create_new_db = task(ct.create_new_db, name='create_new_db')
data_to_postgres = task(ct.data_to_postgres, name='data_to_postgres')

## Deploy to Neon
@task
def deploy_neon_dump():
    with open('contrans.dump', 'wb') as dump:
        result = subprocess.run(['docker', 'compose', 'exec', '-T', 'postgres',
                                 'pg_dump', '-U', 'postgres', '-d', 'contrans', '-Fc', '-v'],
                                stdout=dump, stderr=subprocess.PIPE,
                                encoding='utf-8', errors='replace')
    print(result.stderr)          
    result.check_returncode()

@task
def deploy_neon_restore():
    with open('contrans.dump', 'rb') as dump:                # replaces "< contrans.dump"
        result = subprocess.run(['docker', 'compose', 'exec', '-T', 'postgres', 'sh', '-c',
                                 'pg_restore -v --no-owner --no-privileges --clean --if-exists '
                                 '--single-transaction -d "$NEON_DATABASE_URL_UNPOOLED"'],
                                stdin=dump, capture_output=True,
                                encoding='utf-8', errors='replace')
    print(result.stdout + result.stderr)
    result.check_returncode()


# Flow
@flow(name='contrans-pipeline', log_prints=True)
def contrans_pipeline():
    
    ideology = extract_ideology.submit()
    bill_summaries = extract_bill_summaries.submit()
    committees = extract_committees.submit()
    committee_membership = extract_committee_membership.submit()

    sponsored_legislation = extract_sponsored_legislation.submit(wait_for=[ideology])
    schedule_e = extract_schedule_e.submit(wait_for=[ideology])
    bio_terms = extract_bio_terms.submit(wait_for=[ideology])
    vote_similarity = extract_vote_similarity.submit(wait_for=[ideology])

    processed_members = make_members.submit(wait_for=[ideology, bio_terms])
    processed_crosswalk = make_crosswalk.submit(wait_for=[ideology])
    processed_terms = make_terms.submit(wait_for=[bio_terms])
    processed_bills = make_bills.submit(wait_for=[bill_summaries, sponsored_legislation])
    processed_expenditures = make_expenditures.submit(wait_for=[schedule_e])
    processed_others = make_others.submit(wait_for=[committees, committee_membership,vote_similarity])

    #processed_members = make_members.submit()
    #processed_crosswalk = make_crosswalk.submit()
    #processed_terms = make_terms.submit()
    #processed_bills = make_bills.submit()
    #processed_expenditures = make_expenditures.submit()
    #processed_others = make_others.submit()

    docker = docker_launch.submit()
    new_db = create_new_db.submit(
        wait_for=[processed_members, processed_crosswalk, processed_terms, 
                          processed_bills, processed_expenditures, processed_others, docker]
        )

    to_postgres = data_to_postgres.submit(wait_for=[new_db])

    neon_dump = deploy_neon_dump.submit(wait_for=[to_postgres])
    neon_restore = deploy_neon_restore.submit(wait_for=[neon_dump])
    neon_restore.result()

if __name__ == '__main__':
    contrans_pipeline()