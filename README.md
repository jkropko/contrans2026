# [Your Project Title]

> Replace this whole file as you go. The headings are the ones I'll look for when grading, and they're roughly the ones *Data in Brief* asks for, so filling them in during the semester means your final report is half-written by December.

One or two sentences: what data this pipeline collects, and what the dashboard lets someone see.

**Live dashboard:** [your Render URL]

---

## What this project does

A paragraph. What question motivated it, what data you collect, and what a visitor to the dashboard can find out. Write this for someone who has never heard of your topic.

## Data sources

| Source | What it provides | Access | License |
|---|---|---|---|
| *e.g. Example.gov API* | *daily observations, 2019–present* | *REST API, key required* | *public domain* |
| | | | |
| | | | |

At least two sources with a relationship between them — that's a project requirement, and it's where the interesting problems live.

For each source, note anything a future reader would need: rate limits, pagination quirks, how far back the data goes, whether the license permits redistribution.

## How the pipeline works

Raw → cleaned → loaded → served. A few sentences, or a list of steps, describing what happens in what order and which script does it.

```
src/extract.py     pulls from the APIs, writes to data/raw/
src/transform.py   cleans, resolves identities, writes to data/processed/
src/load.py        loads into the database
src/app.py         the Dash app the deployment runs
```

Rename these however you like — just make sure the README matches what's actually there.

## Database

Which engine, how many tables, and what the relationship between them is.

**Documentation:** [your dbdocs.io or GitHub Pages URL]

## Running this yourself

### What you need

Credentials for the sources listed above. Copy `.env.example` to `.env` and fill in your own values:

```
cp .env.example .env
```

Never commit `.env` — it's already in `.gitignore`. If you accidentally commit a real key, tell Prof. Kropko so it can be rotated. That's the actual fix; deleting the line doesn't remove it from the history.

### Running it

```
docker compose build
docker compose up
```

Say roughly how long a full run takes and what it writes. If there's a step that has to happen first — a database migration, an initial backfill — say so here.

### Running the tests

The validation checks run against `data/sample/`, so they work without credentials or a network:

```
pytest
```

## Repository layout

```
data/raw/          untouched source data, never edited
data/processed/    derived data, reproducible from raw
data/sample/       small committed sample the tests run against
src/               pipeline code
tests/             validation checks and unit tests
docs/              database documentation, notes
.env.example       every variable this project needs, with placeholder values
```

**`data/raw/` is deliberately not committed** if your raw data is large or its license prohibits redistribution. If that's your situation, delete this sentence and say instead where the raw data actually lives and how someone would obtain it.

## Limitations

What this data doesn't cover, what your entity matching probably missed, which numbers a reader shouldn't lean on. Being specific here is worth real points on the final report, and it's much easier to write in October, when you've just hit the problem, than in December.

## Use of generative AI

Required with the final submission, for both text and code. "I did not use generative AI" is a fine statement if it's true. AI-assisted commits should carry an `Assisted-by:` trailer.

## License

Pick one, or state that the code is unlicensed and the data belongs to its original sources.
