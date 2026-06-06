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
# Entry point — Cloud Functions calls this function when the HTTP trigger fires
# ---------------------------------------------------------------------------
@functions_framework.http
def ingest_breeds(request):
    """
    HTTP-triggered Cloud Function.
    1. Fetches all breed records from the Dog API.
    2. Writes the raw JSON response to Cloud Storage.
    3. Loads the data into a BigQuery bronze table.
    Returns a JSON response with a status message.
    """
    run_date = date.today().isoformat()   # e.g. "2026-06-07"

    try:
        breeds = _fetch_breeds()
        gcs_uri = _write_to_gcs(breeds, run_date)
        rows_loaded = _load_to_bigquery(gcs_uri, run_date)

        logger.info("Pipeline complete. date=%s rows=%d", run_date, rows_loaded)
        return {"status": "ok", "date": run_date, "rows_loaded": rows_loaded}, 200

    except Exception as exc:
        logger.exception("Pipeline failed: %s", exc)
        return {"status": "error", "message": str(exc)}, 500


# ---------------------------------------------------------------------------
# Step 1: call the Dog API
# ---------------------------------------------------------------------------
def _fetch_breeds():
    """
    Calls the Dog API and returns a list of breed dicts.
    Raises an exception if the request fails or returns a non-200 status.
    """
    headers = {}
    if DOG_API_KEY:
        headers["x-api-key"] = DOG_API_KEY

    response = requests.get(DOG_API_URL, headers=headers, timeout=30)
    response.raise_for_status()   # raises HTTPError for 4xx/5xx responses

    breeds = response.json()
    logger.info("Fetched %d breeds from Dog API", len(breeds))
    return breeds


# ---------------------------------------------------------------------------
# Step 2: write raw JSON to Cloud Storage
# ---------------------------------------------------------------------------
def _write_to_gcs(breeds: list, run_date: str) -> str:
    """
    Serialises the breed list to newline-delimited JSON (one record per line)
    and uploads it to GCS at:
      gs://<bucket>/breeds/date=<run_date>/breeds.json

    Returns the GCS URI so the BigQuery load job can reference it.
    """
    # Newline-delimited JSON (NDJSON): BigQuery's preferred format for load jobs.
    # Each line is one complete JSON object — easier to stream and parse than
    # a single large JSON array.
    ndjson_content = "\n".join(json.dumps(record) for record in breeds)

    blob_path = f"breeds/date={run_date}/breeds.json"
    gcs_uri = f"gs://{GCS_BUCKET_NAME}/{blob_path}"

    client = storage.Client()
    bucket = client.bucket(GCS_BUCKET_NAME)
    blob = bucket.blob(blob_path)
    blob.upload_from_string(ndjson_content, content_type="application/json")

    logger.info("Wrote raw data to %s", gcs_uri)
    return gcs_uri


# ---------------------------------------------------------------------------
# Step 3: load from GCS into BigQuery
# ---------------------------------------------------------------------------
def _load_to_bigquery(gcs_uri: str, run_date: str) -> int:
    """
    Runs a BigQuery load job that reads the NDJSON file from GCS and appends
    rows to the bronze table. Adds an `ingested_date` column so each row is
    tagged with the date it was loaded.

    Returns the number of rows loaded.
    """
    client = bigquery.Client(project=BQ_PROJECT)
    table_ref = f"{BQ_PROJECT}.{BQ_DATASET}.{BQ_TABLE}"

    job_config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
        autodetect=True,               # BQ infers schema from the JSON keys
        write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
                                       # append rows; never overwrite history
        schema_update_options=[
            bigquery.SchemaUpdateOption.ALLOW_FIELD_ADDITION,
        ],                             # safe if the API adds new fields in future
    )

    # BigQuery does not natively add a load-time column, so we add
    # ingested_date to every record before loading.
    # We re-read the GCS file, inject the field, and upload a patched version.
    gcs_uri_with_date = _inject_ingested_date(gcs_uri, run_date)

    load_job = client.load_table_from_uri(
        gcs_uri_with_date,
        table_ref,
        job_config=job_config,
    )
    load_job.result()   # blocks until the job completes; raises on failure

    destination = client.get_table(table_ref)
    logger.info("Loaded data into %s", table_ref)
    return destination.num_rows


# ---------------------------------------------------------------------------
# Helper: inject ingested_date into every record
# ---------------------------------------------------------------------------
def _inject_ingested_date(gcs_uri: str, run_date: str) -> str:
    """
    Downloads the NDJSON file from GCS, adds `ingested_date` to each record,
    and uploads the patched version to a separate GCS path:
      breeds/date=<run_date>/breeds_with_date.json

    Returns the URI of the patched file.
    """
    client = storage.Client()

    # Parse  gs://bucket/path  into its components
    path_without_scheme = gcs_uri.replace("gs://", "")
    bucket_name, blob_path = path_without_scheme.split("/", 1)

    # Download and patch
    bucket = client.bucket(bucket_name)
    raw_content = bucket.blob(blob_path).download_as_text()

    patched_lines = []
    for line in raw_content.splitlines():
        record = json.loads(line)
        record["ingested_date"] = run_date
        patched_lines.append(json.dumps(record))

    patched_content = "\n".join(patched_lines)

    # Upload patched file
    patched_blob_path = blob_path.replace("breeds.json", "breeds_with_date.json")
    bucket.blob(patched_blob_path).upload_from_string(
        patched_content, content_type="application/json"
    )

    patched_uri = f"gs://{bucket_name}/{patched_blob_path}"
    logger.info("Uploaded patched file to %s", patched_uri)
    return patched_uri
