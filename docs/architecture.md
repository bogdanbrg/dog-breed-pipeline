# Architecture decisions

## Data flow

1. Cloud Function is triggered (HTTP or Cloud Scheduler).
2. It calls the Dog API and receives a JSON array of all breeds (~170 records).
3. The raw response is written to Cloud Storage as a single JSON file, partitioned by date:
   `gs://dog-breed-raw-project-6a3a4778/breeds/date=YYYY-MM-DD/breeds.json`
4. The same function loads the file into a BigQuery bronze table (`dog_breeds_bronze.raw_breeds`).
5. dbt reads from the bronze table and produces cleaned, typed models in `dog_breeds_curated`.

## Why Cloud Storage before BigQuery?

Storing raw JSON in GCS before loading to BigQuery is the "medallion architecture" pattern:
- You always have the original source data for reprocessing or debugging.
- If the BigQuery load fails, you haven't lost the data.
- Auditors/analysts can inspect the raw file without hitting the API again.

## Why two BigQuery datasets?

`dog_breeds_bronze` holds raw, unmodified data — exactly what came from the API.
`dog_breeds_curated` holds dbt-transformed data with proper types, renamed columns, and business logic.
Keeping them separate means you can rerun dbt without re-ingesting, and you can always trace a curated value back to its raw source.

## Partitioning strategy

GCS path uses `date=YYYY-MM-DD` (Hive-style partitioning). This is a convention BigQuery understands natively when creating external tables, and it makes backfilling or inspecting a specific day straightforward.
