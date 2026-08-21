# Tests

Two different jobs live here, and it's worth knowing which is which.

**Pandera checks your data.** Schema, types, ranges, uniqueness, relationships
between tables. These catch a source that changed overnight, a parse that went
wrong, a join that silently dropped rows.

**pytest checks your code.** Your transformation functions, given known input,
produce known output. These catch you breaking something you wrote last week.

Both run against `data/sample/`, so no credentials and no network:

```
pytest
```

## Make your checks able to fail

A range check of -1000 to 1000 on a variable that lives in [-1, 1] passes
forever and proves nothing. The test of a good check is whether you can
describe the specific bad thing it would catch.

`test_validation.py` has four checks stubbed out. Replace them with ones
that match your data's real failure modes.
