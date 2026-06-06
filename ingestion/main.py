import os
import json
import logging
from datetime import date

import requests
import functions_framework
from google.cloud import storage, bigquery

# ---------------------------------------------------------------------------
# Configuration — read from environment variables, never hardcoded
# ---------------------------------------------------------------------------
DOG_API_URL = "https://api.thedogapi.com/v1/breeds"
DOG_API_KEY = os.environ.get("DOG_API_KEY", "")

GCS_BUCKET_NAME = os.environ["GCS_BUCKET_NAME"]
BQ_PROJECT = os.environ["BQ_PROJECT"]
BQ_DATASET = os.environ["BQ_DATASET"]
BQ_TABLE = os.environ["BQ_TABLE"]

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Entry point — Cloud Functions calls this when the HTTP trigger fires
# ---------------------------------------------------------------------------
@functions_framework.http
def ingest_breeds(request):
    """
    HTTP-triggered Cloud Function.
    1. Fetches all breed records from the Dog API.
    2. Writes the raw JSON response to Cloud Storage (archive copy).
    3. Writes an enriched copy (with ingested_date) to GCS for BQ loading.
    4. Loads the enriched file into the BigQuery bronze table.
    Returns a JSON response with a status message.
    """
    run_date = date.today().isoformat()  # e.g. "2026-06-06"

    try:
        breeds = _fetch_breeds()
        raw_uri, enriched_uri = _write_to_gcs(breeds, run_date)
        rows_loaded = _load_to_bigquery(enriched_uri, run_date)

        logger.info("Pipeline complete. date=%s rows=%d", run_date, rows_loaded)
        return {"status": "ok", "date": run_date, "rows_loaded": rows_loaded}, 200

    except Exception as exc:
        logger.exception("Pipeline failed: %s", exc)
        return {"status": "error", "message": str(exc)}, 500


# ---------------------------------------------------------------------------
# Step 1: call the Dog API
# ---------------------------------------------------------------------------
def _fetch_breeds() -> list:
    """Calls the Dog API and returns a list of breed dicts."""
    headers = {}
    if DOG_API_KEY:
        headers["x-api-key"] = DOG_API_KEY

    response = requests.get(DOG_API_URL, headers=headers, timeout=30)
    response.raise_for_status()  # raises HTTPError for 4xx/5xx

    breeds = response.json()
    logger.info("Fetched %d breeds from Dog API", len(breeds))
    return breeds


# ---------------------------------------------------------------------------
# Step 2: write to Cloud Storage
# ---------------------------------------------------------------------------
def _write_to_gcs(breeds: list, run_date: str) -> tuple[str, str]:
    """
    Uploads two files to GCS under breeds/date=<run_date>/:

      breeds.json             — raw API payload, no modifications (archive)
      breeds_enriched.json    — same payload with ingested_date added (for BQ)

    Both are newline-delimited JSON (NDJSON). BigQuery's load jobs require
    NDJSON: one JSON object per line rather than a single large array.

    Returns (raw_uri, enriched_uri).
    """
    client = storage.Client()
    bucket = client.bucket(GCS_BUCKET_NAME)
    prefix = f"breeds/date={run_date}"

    # Build both NDJSON strings in one pass over the list
    raw_lines = []
    enriched_lines = []
    for record in breeds:
        raw_lines.append(json.dumps(record))
        enriched = {**record, "ingested_date": run_date}
        enriched_lines.append(json.dumps(enriched))

    raw_ndjson = "\n".join(raw_lines)
    enriched_ndjson = "\n".join(enriched_lines)

    raw_path = f"{prefix}/breeds.json"
    enriched_path = f"{prefix}/breeds_enriched.json"

    bucket.blob(raw_path).upload_from_string(raw_ndjson, content_type="application/json")
    bucket.blob(enriched_path).upload_from_string(enriched_ndjson, content_type="application/json")

    raw_uri = f"gs://{GCS_BUCKET_NAME}/{raw_path}"
    enriched_uri = f"gs://{GCS_BUCKET_NAME}/{enriched_path}"

    logger.info("Wrote raw data to %s", raw_uri)
    logger.info("Wrote enriched data to %s", enriched_uri)
    return raw_uri, enriched_uri


# ---------------------------------------------------------------------------
# Step 3: load enriched file from GCS into BigQuery
# ---------------------------------------------------------------------------
def _load_to_bigquery(enriched_uri: str, run_date: str) -> int:
    """
    Runs a BigQuery load job that appends rows from the enriched NDJSON file.

    autodetect=True: BQ infers column types from the JSON keys. Fine for a
    bronze table where we want to capture everything the API sends.

    WRITE_APPEND: we never overwrite history. Each day's run adds new rows
    tagged with ingested_date, giving us a full reload history.

    ALLOW_FIELD_ADDITION: safe if the Dog API ever adds new fields — BQ
    will extend the schema rather than reject the load.

    Returns the total row count of the table after loading.
    """
    client = bigquery.Client(project=BQ_PROJECT)
    table_ref = f"{BQ_PROJECT}.{BQ_DATASET}.{BQ_TABLE}"

    job_config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
        autodetect=True,
        write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
        schema_update_options=[
            bigquery.SchemaUpdateOption.ALLOW_FIELD_ADDITION,
        ],
    )

    load_job = client.load_table_from_uri(
        enriched_uri,
        table_ref,
        job_config=job_config,
    )
    load_job.result()  # blocks until complete; raises on failure

    destination = client.get_table(table_ref)
    logger.info("Loaded data into %s (%d total rows)", table_ref, destination.num_rows)
    return destination.num_rows
