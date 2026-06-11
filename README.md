# Dog Breed Data Pipeline

[![CD — deploy on merge to main](https://github.com/bogdanbrg/dog-breed-pipeline/actions/workflows/cd.yml/badge.svg)](https://github.com/bogdanbrg/dog-breed-pipeline/actions/workflows/cd.yml)
[![CI — dbt run & test on PR](https://github.com/bogdanbrg/dog-breed-pipeline/actions/workflows/ci.yml/badge.svg)](https://github.com/bogdanbrg/dog-breed-pipeline/actions/workflows/ci.yml)

A batch data engineering pipeline that ingests breed data from the [Dog API](https://api.thedogapi.com/v1/breeds), stores raw JSON in Cloud Storage, loads it into BigQuery, and transforms it with dbt.

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
