# Local Development Guide

This guide walks through the local setup, the backend logic, and the database schema. It is designed to be educational, explaining *why* certain decisions were made.

## Setting up Python environment
```bash
# Create virtual environment (isolates project dependencies)
# ensure `brew install python@3.11` as its more stable
python3.11 -m venv venv

# Activate it
source venv/bin/activate  # Mac/Linux

# Install dependencies
pip install -r requirements.txt
```
**Learning Point:** `requirements.txt` ensures everyone has the same dependencies. Critical for consistency.

## Building the Core Scanner

To understand AWS Cost Data, you need to understand how AWS stores data:

1.  **CloudWatch Metrics:** Performance data (CPU, memory, disk I/O). Stored in 1-minute or 5-minute intervals.
2.  **Cost Explorer:** Billing data. Daily granularity.
3.  **Resource APIs:** Instance/volume metadata (current state, tags).

The scanner combines all three to find waste.

## Testing the EC2 Scanner

```bash
# Run the scanner for ec2 (defaults to eu-west-2)
python -m backend.scanner.ec2_scanner
```

✅ AWS API Integration - boto3 client usage, pagination\
✅ CloudWatch Metrics - Time-series data analysis\
✅ Cost Calculation - Business logic for savings\
✅ Decision Algorithms - Severity classification\
✅ Clean Code - Docstrings, type hints, error handling

## Testing the EBS (Elastic Block Store) Scanner
```bash
python -m backend.scanner.ebs_scanner
```

## Business Problems Solved

**1. Orphaned Volumes**\
Developer launches EC2 instance with 500GB volume → Tests feature → Terminates instance → Volume remains attached (default) → Forgot to delete → $50/month waste forever.

**2. Ancient Snapshots**\
Automated daily backups for 2 years → 730 snapshots → Each 100GB → 73TB stored → $3,650/month in snapshot costs.

**3. Wrong Volume Type**\
Dev uses `io2` (high performance SSD) for logs → Costs $0.125/GB vs `st1` (throughput HDD) at $0.045/GB → 2.7x overpaying.

✅ **EBS Volume Lifecycle** - States, attachments, deletion policies\
✅ **Storage Cost Optimisation** - Type selection, size analysis\
✅ **I/O Pattern Analysis** - CloudWatch volume metrics\
✅ **Snapshot Management** - Retention policies, incremental backups

## Database Layer (PostgreSQL)

**What it does:** Stores scan results.\
**Purpose:** Track history, show trends, power the dashboard.

Use the docker compose file to run Postgres locally:

```bash 
# 1. Start PostgreSQL
docker-compose up -d postgres

# 2. Wait for it to be ready
docker-compose logs -f postgres
# (Wait for "database system is ready to accept connections")

# 3. Create tables
python -m backend.models.database

# 4. Verify tables were created
docker-compose exec postgres psql -U postgres -d cost_optimiser -c "\dt"
```

## REST API - Deep Dive with FastAPI

I used FastAPI to expose the logic to the world.

✅ RESTful API Design - Industry standard patterns\
✅ FastAPI Framework - Modern Python API framework\
✅ HTTP Methods - GET, POST, PUT, DELETE\
✅ Authentication - API key security\
✅ CORS - Allow frontend to call API\
✅ Error Handling - Proper HTTP status codes\
✅ API Documentation - Auto-generated with Swagger

### API Structure
```
Cost Optimiser API
├── GET /api/scans                    → List all past scans
├── GET /api/scans/{id}               → Get specific scan details
├── POST /api/scans/run               → Trigger a new scan
├── GET /api/scans/{id}/findings      → Get findings from a scan
├── GET /api/dashboard/summary        → Dashboard overview
├── GET /api/savings/realized         → Track implemented savings
└── POST /api/findings/{id}/implement → Mark recommendation as done
```

## Run Everything Locally (Demo Mode)
```bash
# Terminal 1 - Start Database
docker-compose up -d postgres

# Terminal 2 - Start API
python -m backend.api.main

# Terminal 3 - Start Frontend
cd frontend
npm install
npm run dev

# Access Dashboard
http://localhost:3000
```
