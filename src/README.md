# Pipeline code

Suggested split, matching the order your data moves in. Rename anything —
just keep the README's description matching what's actually here.

| file | job |
|---|---|
| `extract.py` | pull from your sources, write untouched results to `data/raw/` |
| `transform.py` | clean, resolve identities, write to `data/processed/` |
| `load.py` | load processed data into the database |
| `app.py` | the Dash app Render runs |

Two habits worth keeping:

**Raw stays raw.** Never overwrite anything in `data/raw/`. When your parser
turns out to have a bug in November — and it will — you want to re-parse
rather than re-download.

**Cache your API responses.** Write raw JSON to disk keyed by the request, and
check the cache before hitting the network. Re-running your own pipeline should
be free and instant. This is the single change that makes development pleasant.
