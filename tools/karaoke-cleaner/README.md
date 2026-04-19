# Karaoke CSV Cleaner

This folder is for raw karaoke DJ machine exports and cleanup files only. It is separate from the public song search page.

## Folder Rules

Use these locations:

```text
tools/karaoke-cleaner/upload-csv/
```

Put raw exported CSV files here. These are upload/input files only.

```text
tools/karaoke-cleaner/output/
```

The cleaner writes generated files here.

Do not use raw upload files as the public website `songs.csv`.

## Clean A Raw Upload CSV

From the main `Website` folder, run:

```powershell
python tools\karaoke-cleaner\karaoke_csv_cleaner.py "tools\karaoke-cleaner\upload-csv\raw-export.csv"
```

Replace `raw-export.csv` with the actual exported file name.

The source upload CSV is not overwritten.

## Output Files

The cleaner creates:

```text
tools/karaoke-cleaner/output/cleaned_output.csv
tools/karaoke-cleaner/output/review_needed.csv
tools/karaoke-cleaner/output/duplicates_removed.csv
```

Use `cleaned_output.csv` as the working cleanup result.

Review `review_needed.csv` before publishing. These rows were flagged because artist/title separation, lookup confidence, metadata, vocal type, or duplicate status may need a human check.

Keep `duplicates_removed.csv` as the audit trail for exact normalized artist/title duplicates that were removed.

## Output Columns

`cleaned_output.csv` uses:

```text
title, artist, year, decade, categories, social_singing, original_vocal, possible_duplicate, match_confidence, needs_review, notes, raw_input
```

## Optional Online Validation

The default cleanup pass is offline and conservative.

For metadata validation and enrichment through MusicBrainz, run:

```powershell
python tools\karaoke-cleaner\karaoke_csv_cleaner.py "tools\karaoke-cleaner\upload-csv\raw-export.csv" --validate-online
```

Lookup results are cached at:

```text
tools/karaoke-cleaner/output/metadata_cache.json
```

Uncertain online matches stay blank where needed and are flagged for review.

## Publish To The Search Site

Only after review, copy approved clean song rows into the public site CSV:

```text
songs.csv
```

or:

```text
data/songs.csv
```

Then rebuild the search index using the public-site instructions in the main README.
