import io
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
    2. Writes the raw JSON response to Cloud Storage (one file, unmodified).
    3. Loads into BigQuery with ingested_date injected in memory — no second file.
    Returns a JSON response with a status message.
    """
    run_date = date.today().isoformat()  # e.g. "2026-06-06"

    try:
        breeds = _fetch_breeds()
        _write_to_gcs(breeds, run_date)
        rows_loaded = _load_to_bigquery(breeds, run_date)

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
# Step 2: write raw JSON to Cloud Storage (archive, unmodified)
# ---------------------------------------------------------------------------
def _write_to_gcs(breeds: list, run_date: str) -> str:
    """
    Uploads the raw API payload as NDJSON to:
      gs://<bucket>/breeds/date=<run_date>/breeds.json

    Nothing is added or changed — this is the unmodified source record.
    Returns the GCS URI.
    """
    ndjson = "\n".join(json.dumps(record) for record in breeds)
    blob_path = f"breeds/date={run_date}/breeds.json"

    client = storage.Client()
    client.bucket(GCS_BUCKET_NAME).blob(blob_path).upload_from_string(
        ndjson, content_type="application/json"
    )

    uri = f"gs://{GCS_BUCKET_NAME}/{blob_path}"
    logger.info("Wrote raw data to %s", uri)
    return uri


# ---------------------------------------------------------------------------
# Step 3: load into BigQuery with ingested_date injected in memory
# ---------------------------------------------------------------------------
def _load_to_bigquery(breeds: list, run_date: str) -> int:
    """
    Injects ingested_date into each record in memory, then streams the result
    directly to BigQuery via load_table_from_file — no second GCS file needed.

    autodetect=True: BQ infers column types from the JSON keys.
    WRITE_APPEND: each daily run appends; history is never overwritten.
    ALLOW_FIELD_ADDITION: safe if the Dog API adds new fields in future.

    Returns the total row count of the table after loading.
    """
    ndjson = "\n".join(
        json.dumps({**record, "ingested_date": run_date}) for record in breeds
    )

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

    load_job = client.load_table_from_file(
        io.BytesIO(ndjson.encode("utf-8")),
        table_ref,
        job_config=job_config,
    )
    load_job.result()  # blocks until complete; raises on failure

    destination = client.get_table(table_ref)
    logger.info("Loaded data into %s (%d total rows)", table_ref, destination.num_rows)
    return destination.num_rows
