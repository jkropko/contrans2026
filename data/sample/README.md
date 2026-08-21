# Sample data

A small slice of your cleaned data, committed so the validation checks in
`tests/` run without credentials or a network connection.

**A few hundred rows is plenty.** Check the license on your source first —
some of the sources in this course permit redistribution and some don't.
If yours doesn't, say so here and use synthetic rows with the same schema
instead.

## Build the sample deliberately

The easy thing is `df.head(200)`, and it's close to useless: every check
passes trivially and you learn nothing. Include the awkward cases —

- a record with a one-to-many relationship (an entity with several IDs)
- a low-confidence match from your entity resolution
- a null where nulls legitimately occur
- a boundary value at the edge of a range you check

A sample built this way makes your tests able to fail, which is the whole
point of having them.

## What's in here

*Describe your sample files: what each one is, how many rows, and how you
selected them.*
