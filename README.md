# Dog Breed Data Pipeline

[![CD — deploy on merge to main](https://github.com/bogdanbrg/dog-breed-pipeline/actions/workflows/cd.yml/badge.svg)](https://github.com/bogdanbrg/dog-breed-pipeline/actions/workflows/cd.yml)
[![CI — dbt run & test on PR](https://github.com/bogdanbrg/dog-breed-pipeline/actions/workflows/ci.yml/badge.svg)](https://github.com/bogdanbrg/dog-breed-pipeline/actions/workflows/ci.yml)

A batch data engineering pipeline that ingests breed data from the [Dog API](https://api.thedogapi.com/v1/breeds), stores raw JSON in Cloud Storage, loads it into BigQuery, and transforms it with dbt.

## Case Study Overview

This project was built as a complete end-to-end data engineering case study, covering ingestion, storage, transformation, testing, CI/CD, and visualisation.

### Dashboard

[View the live dashboard →](https://datastudio.google.com/s/kwo-ewne7PM)

### Questions answered by the dashboard

1. **Which breeds have the longest predicted life span?** — Top 10 breeds ranked by maximum life span, extracted from the API's mixed-format range strings (e.g. `"12-15 years"`).
2. **What is the distribution of breeds by weight class?** — Breeds classified into Toy / Small / Medium / Large / Giant based on maximum weight in kg.
3. **What are the most common temperaments?** — Top 15 temperament tags ranked by frequency across all breeds, derived by splitting the comma-separated `temperament` field into individual rows.

### Data exploration findings

During exploration, several data quality issues were identified directly from the raw source:

- **`perfect_for` and `bred_for` are null for all 628 breeds** — confirmed by inspecting raw GCS files. These fields are absent at the API level, not lost during ingestion.
- **Mixed height/weight formats** — the API returns both simple ranges (`"38-46"`) and sex-specific ranges (`"Male: 45-53; Female: 43-53"`) in the same column. Handled in `stg_breeds` using `REGEXP_EXTRACT_ALL` to extract all numbers and take `MIN`/`MAX`.
- **Case inconsistency in temperament** — `"loyal"` and `"Loyal"` appeared as separate values. Fixed in `mart_temperaments` by applying `LOWER()` before splitting.
- **Temperament inflation bias** — `"intelligent"` appears in ~86% of breeds, suggesting low signal in this field for distinguishing breeds.

### Data model

The pipeline follows a **medallion architecture**:

| Layer | Dataset | Description |
|---|---|---|
| Bronze | `dog_breeds_bronze` | Raw JSON loaded directly from the Dog API, append-only |
| Curated | `dog_breeds_curated` | dbt-transformed tables, deduplicated and typed |

The curated layer uses **dimensional modelling**:

- `dim_breed` — one row per breed, descriptive attributes + size classification
- `fact_weight_life_span` — numeric measurements (weight, height, life span) per breed
- `mart_breeds` — denormalised join of dim + fact, dashboard-ready
- `mart_temperaments` — bridge table, one row per breed per temperament tag

## Architecture

```
Dog API
  └─► Cloud Function (Python 3.12)
        └─► Cloud Storage (raw JSON, partitioned by date)
              └─► BigQuery bronze table (raw load)
                    └─► dbt (curated/silver layer)
                          └─► BigQuery curated tables
```

## Stack

| Layer | Technology |
|---|---|
| Ingestion | Google Cloud Functions (Python 3.12) |
| Raw storage | Google Cloud Storage (JSON, date-partitioned) |
| Warehouse | Google BigQuery |
| Transformation | dbt Core with BigQuery adapter |
| CI/CD | GitHub Actions |
| Visualisation | Looker Studio (Data Studio) |

## GCP Setup

### Prerequisites

- GCP project: `project-6a3a4778-6bf8-49b1-984`
- [gcloud CLI](https://cloud.google.com/sdk/docs/install) installed and authenticated

### Enable required APIs

```bash
gcloud config set project project-6a3a4778-6bf8-49b1-984

gcloud services enable \
  cloudfunctions.googleapis.com \
  storage.googleapis.com \
  bigquery.googleapis.com \
  cloudbuild.googleapis.com \
  run.googleapis.com
```

### Create a service account

```bash
gcloud iam service-accounts create dog-pipeline-sa \
  --display-name="Dog Pipeline Service Account"

# Grant BigQuery write access
gcloud projects add-iam-policy-binding project-6a3a4778-6bf8-49b1-984 \
  --member="serviceAccount:dog-pipeline-sa@project-6a3a4778-6bf8-49b1-984.iam.gserviceaccount.com" \
  --role="roles/bigquery.dataEditor"

# Grant BigQuery job runner (needed to run load jobs)
gcloud projects add-iam-policy-binding project-6a3a4778-6bf8-49b1-984 \
  --member="serviceAccount:dog-pipeline-sa@project-6a3a4778-6bf8-49b1-984.iam.gserviceaccount.com" \
  --role="roles/bigquery.jobUser"

# Grant Cloud Storage write access
gcloud projects add-iam-policy-binding project-6a3a4778-6bf8-49b1-984 \
  --member="serviceAccount:dog-pipeline-sa@project-6a3a4778-6bf8-49b1-984.iam.gserviceaccount.com" \
  --role="roles/storage.objectCreator"
```

### Create Cloud Storage bucket

```bash
gcloud storage buckets create gs://dog-breed-raw-project-6a3a4778 \
  --location=US \
  --uniform-bucket-level-access
```

### Create BigQuery datasets

```bash
bq mk --location=US dog_breeds_bronze
bq mk --location=US dog_breeds_curated
```

## Local development

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r ingestion/requirements.txt
```

## Repository structure

```
├── ingestion/          # Cloud Function source code
├── dbt/                # dbt project (models, tests, macros)
├── .github/workflows/  # GitHub Actions CI/CD
├── docs/               # Architecture notes
└── README.md
```
