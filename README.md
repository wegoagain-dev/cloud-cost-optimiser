# What Problem Are We Solving?
**Real scenario:** A startup runs 50 EC2 instances. Their AWS bill is $8,000/month.

**After analysis:**\
15 instances idle at night (could be stopped): $2,400/month wasted\
8 instances oversized (t3.large when t3.small works): $1,200/month wasted\
20 unattached EBS volumes from deleted instances: $200/month wasted\
100+ old snapshots from 2 years ago: $300/month wasted

Total waste: $4,100/month = $49,200/year\
This tool finds this automatically.


# Architecture
```
┌─────────────────────────────────────────────────────────────────┐
│                        USER INTERFACE                           │
│  React Dashboard - Shows costs, recommendations, savings        │
└────────────────────────────┬────────────────────────────────────┘
                             │ HTTPS/REST
┌────────────────────────────▼────────────────────────────────────┐
│                         API LAYER                               │
│  FastAPI - Handles requests, authentication, business logic     │
└────────────────────────────┬────────────────────────────────────┘
                             │
          ┌──────────────────┼──────────────────┐
          │                  │                  │
┌─────────▼─────────┐ ┌─────▼──────┐ ┌────────▼────────┐
│   EC2 Scanner     │ │ EBS Scanner│ │  RDS Scanner    │
│ (CPU, Memory)     │ │ (Volumes)  │ │  (Databases)    │
└─────────┬─────────┘ └─────┬──────┘ └────────┬────────┘
          │                  │                  │
          └──────────────────┼──────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────────┐
│                       AWS APIs                                  │
│  • Cost Explorer API (billing data)                             │
│  • CloudWatch API (metrics: CPU, memory, network)               │
│  • EC2 API (instance details)                                   │
│  • EBS API (volume details)                                     │
└────────────────────────────┬────────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────────┐
│                    DATABASE (PostgreSQL)                        │
│  • Scan history                                                 │
│  • Recommendations                                              │
│  • Savings tracking                                             │
└─────────────────────────────────────────────────────────────────┘
```

# 🛠️ Tech Stack & Architecture Decisions

| Technology | Why This Choice? | Key Learning Outcomes |
| :--- | :--- | :--- |
| **🐍 Python** | Native AWS SDK (`boto3`) support and dominant in cloud automation. | Scripting real-world cloud automation and data processing. |
| **⚡ FastAPI** | Modern, high-performance framework with built-in async support and auto-documentation. | RESTful API design, asynchronous programming, and Swagger UI. |
| **🐘 PostgreSQL** | Robust relational database perfect for structured findings and historical cost data. | Schema normalization, SQL optimization, and data persistence. |
| **⚛️ React** | Industry-standard library for building interactive, component-based dashboards. | Modern frontend development, state management, and API integration. |
| **🐳 Docker** | Ensures consistency across environments (dev vs. prod) and simplifies deployment. | Containerization fundamentals and writing efficient Dockerfiles. |
| **🏗️ Terraform** | The "Gold Standard" for Infrastructure as Code (IaC) to manage cloud resources. | IaC best practices, state management, and declarative infra. |


# Project Structure

```
cloud-cost-optimiser/
├── backend/
│   ├── scanner/          # AWS scanning logic
│   │   ├── __init__.py
│   │   ├── ec2_scanner.py
│   │   ├── ebs_scanner.py
│   │   └── rds_scanner.py
│   ├── api/              # FastAPI endpoints
│   │   ├── __init__.py
│   │   ├── main.py
│   │   ├── schemas.py
│   │   └── routes/
│   ├── models/           # Database models
│   │   ├── __init__.py
│   │   └── database.py
│   ├── utils/            # Helper functions
│   │   └── __init__.py
│   └── tests/            # Unit tests
├── frontend/             # React dashboard
│   ├── src/
│   │   ├── components/
│   │   ├── pages/
│   │   └── services/
│   └── package.json
├── infrastructure/       # Terraform configs
│   └── terraform/
├── docker-compose.yml    # Local development
├── Dockerfile
├── requirements.txt      # Python dependencies
└── README.md
```

**Learning Point:** Practicing, Good project structure.

# Setting up Python environment
```bash
# Create virtual environment (isolates project dependencies)
# ensure `brew install python@3.11` as its more stable
python3.11 -m venv venv

# Activate it
source venv/bin/activate  # Mac/Linux

# Install dependencies
pip install -r requirements.txt
```
**Learning Point:** requirements.txt ensures everyone has the same dependencies. Critical for team projects.

# Setting up AWS Credentials

```bash
# Install AWS CLI if you haven't
# Mac: brew install awscli

# Configure AWS credentials
# create user on aws, then configure locally
aws configure --profile cost-optimiser

# Create IAM Policy for Read-Only Access:

{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "ec2:Describe*",
        "cloudwatch:GetMetricStatistics",
        "cloudwatch:ListMetrics",
        "ce:GetCostAndUsage",
        "ce:GetCostForecast",
        "rds:Describe*",
        "s3:ListAllMyBuckets",
        "s3:GetBucketLocation",
        "s3:GetBucketTagging"
      ],
      "Resource": "*"
    }
  ]
}

```
**Why read-only?** Your scanner should NEVER modify resources automatically. Only recommend changes.

# Building Core Scanner

Understanding AWS Cost Data, you'll need to understand how AWS stores data:

**CloudWatch Metrics** - Performance data (CPU, memory, disk I/O)\
Stored in 1-minute or 5-minute intervals\
Retained for 15 months\
Example: CPUUtilization metric for EC2

**Cost Explorer** - Billing data\
Daily granularity available\
Can filter by service, region, tag\
Example: Total EC2 costs for November

**Resource APIs** - Instance/volume metadata\
Current state (running, stopped)\
Instance type, size, age\
Tags and names

The scanner combines all three to find waste.

## Testing the EC2 Scanner

```bash
# You can use an ENV file to use as profile name or this
export AWS_PROFILE=cost-optimiser
# now run the scanner for ec2
python -m backend.scanner.ec2_scanner
```

✅ AWS API Integration - boto3 client usage, pagination\
✅ CloudWatch Metrics - Time-series data analysis\
✅ Cost Calculation - Business logic for savings\
✅ Decision Algorithms - Severity classification\
✅ Clean Code - Docstrings, type hints, error handling

# Testing the EBS (Elastic Block Store) scanner
```bash
python -m backend.scanner.ebs_scanner
```

## Business problems it fixes

**1. orphaned volumes**\
Developer launches EC2 instance with 500GB volume → Tests feature → 
Terminates instance → Volume remains attached (default) → 
Forgot to delete → $50/month waste forever

**2. ancient snapshots**\
Automated daily backups for 2 years → 730 snapshots → 
Each 100GB → 73TB stored → $3,650/month in snapshot costs

**3. wrong volume type**\
Dev uses io2 (high performance SSD) for logs → 
Costs $0.125/GB vs st1 (throughput HDD) at $0.045/GB → 
2.7x overpaying

✅ **EBS Volume Lifecycle** - States, attachments, deletion policies\
✅ **Storage Cost Optimisation** - Type selection, size analysis\
✅ **I/O Pattern Analysis** - CloudWatch volume metrics\
✅ **Snapshot Management** - Retention policies, incremental backups\
✅ **Cost Calculation** - Storage pricing across different types\
✅ **Data Analysis** - Grouping, bucketing, statistical analysis

# Database Layer (PostgreSQL for YOUR application)

**What it does:** Stores YOUR scan results\
**Purpose:** Track history, show trends, power the dashboard

Now to use the docker compose file to run for local development

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

**Expected output:**
```
List of relations
Schema |       Name       | Type  |  Owner
--------+------------------+-------+----------
public | daily_costs      | table | postgres
public | ebs_findings     | table | postgres
public | ec2_findings     | table | postgres
public | savings_realized | table | postgres
public | scan_runs        | table | postgres
(5 rows)
```

Now to save scan results to the database

# Run scan and save to database
```bash
python -m backend.scanner.master_scanner
```

```bash
# how to verify data was saved
# Connect to database
docker-compose exec postgres psql -U postgres -d cost_optimiser

# Check scan runs
SELECT id, scan_date, region, potential_monthly_savings FROM scan_runs;

# Check EC2 findings
SELECT instance_name, severity, potential_monthly_savings FROM ec2_findings LIMIT 5;

# Check EBS findings
SELECT resource_id, finding_type, monthly_cost FROM ebs_findings LIMIT 5;
```

whats been accomplished:

✅ Complete database schema - Normalized, indexed, relationships\
✅ SQLAlchemy ORM - Python ↔ PostgreSQL mapping\
✅ Docker Compose - Local development environment\
✅ Data persistence - Scan results stored permanently\
✅ Tracking capability - Can now show trends over time

# REST API - Deep Dive with FastAPI
Lets learn: (to expose to the world)

✅ RESTful API Design - Industry standard patterns\
✅ FastAPI Framework - Modern Python API framework\
✅ HTTP Methods - GET, POST, PUT, DELETE\
✅ Authentication - API key security\
✅ CORS - Allow frontend to call API\
✅ Error Handling - Proper HTTP status codes\
✅ API Documentation - Auto-generated with Swagger

## What is REST?
REST = Representational State Transfer\
It's a way for programs to talk to each other over HTTP (the same protocol browsers use).

example in simple world analogy
```
Restaurant Menu (API)
├── GET /menu          → Show me the menu (READ)
├── POST /order        → Place a new order (CREATE)
├── PUT /order/123     → Update order #123 (UPDATE)
└── DELETE /order/123  → Cancel order #123 (DELETE)
```
our cost optimiser API
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
## Structure

```
backend/
├── api/
│   ├── __init__.py
│   ├── main.py              # Main API app
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── scans.py         # Scan endpoints
│   │   ├── findings.py      # Findings endpoints
│   │   └── dashboard.py     # Dashboard endpoints
│   └── schemas.py           # Request/Response models (Pydantic)
```

The visual interface you see at localhost:8000/docs is called Swagger UI. You didn't have to build it because FastAPI built it for you automatically.

`master_scanner.py` runs automatically only when you specifically ask for it by sending a POST request to the /api/scans/run endpoint.

## Start the API server
```bash
python -m backend.api.main
```

**Expected output:**

🚀 Starting Cloud Cost Optimiser API...\
✅ Database tables created successfully!\
✅ API ready to accept requests\
📚 API docs available at: http://localhost:8000/docs\
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)

# React Dashboard

✅ React Fundamentals - Components, hooks, state management\
✅ API Integration - Fetch data from FastAPI backend\
✅ Data Visualization - Charts with Recharts\
✅ Responsive Design - Tailwind CSS\
✅ Real-world Patterns - Loading states, error handling


# Run Everything Locally
```bash
# Terminal 1 - Start Database
docker-compose up -d postgres

# Terminal 2 - Start API
cd backend
python -m backend.api.main

# Terminal 3 - Start Frontend
cd frontend
npm install

# Install additional libraries
npm install axios recharts lucide-react clsx tailwind-merge

# Install Tailwind CSS
npm install -D tailwindcss@3.4.17 postcss autoprefixer
npx tailwindcss init -p

# Run React Dashboard
npm run dev

# Access Dashboard
# Open your browser:
http://localhost:3000
```

# Run using Docker Compose

```bash
### 1. Create Environment File
cp .env.example .env
nano .env  # Edit with your credentials
```

### 2. Build Images
```bash
docker-compose build
```

### 3. Start Services
```bash
docker-compose up -d
```

### 4. Initialize Database
```bash
docker-compose exec backend python -m backend.models.database
```

### 5. Verify Everything Works
```bash
# Check services are running
docker-compose ps

# Check backend health
curl http://localhost:8000/health

# Check frontend
curl http://localhost:3000
```
