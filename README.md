# Cloud Cost Optimiser (AWS, Terraform, ECS Fargate)

## Overview

This project transforms a local Python/React application into a production grade, cloud native architecture on AWS. 

It solves a real world financial problem wasted cloud spend, while demonstrating a comprehensive DevOps lifecycle: from Infrastructure as Code (Terraform) to CI/CD automation (GitHub Actions) and Serverless Compute (Fargate).

The application scans an AWS account for idle resources (EC2, EBS, RDS) and generates actionable cost-saving recommendations on a dashboard.

## What Problem Are We Solving?
**Real scenario:** A startup runs 50 EC2 instances. Their AWS bill is $8,000/month.

**After analysis:**\
15 instances idle at night (could be stopped): $2,400/month wasted\
8 instances oversized (t3.large when t3.small works): $1,200/month wasted\
20 unattached EBS volumes from deleted instances: $200/month wasted\
100+ old snapshots from 2 years ago: $300/month wasted

Total waste: $4,100/month = $49,200/year\
This tool finds this automatically.


## Architecture
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
## Key Features
- Serverless Compute: Runs on AWS ECS Fargate, eliminating the need to manage EC2 servers.

- Infrastructure as Code: 100% of the infrastructure (VPC, Subnets, ALB, RDS, ECR) is provisioned via Terraform.

- Zero Downtime Deployments: Automated CI/CD Pipeline using GitHub Actions to build multi-arch Docker images and update ECS services without interruption.

- Production Security: Implements Least Privilege IAM Roles (no hardcoded keys) and strict Security Groups (firewalls).

- Cost Efficient: Designed to run within the AWS Free Tier (where possible) using t3.micro instances and Spot Fargate pricing concepts.

## 🛠️ Tech Stack & Architecture Decisions

| Technology | Why This Choice? | Key Learning Outcomes |
| :--- | :--- | :--- |
| **🐍 Python** | Native AWS SDK (`boto3`) support and dominant in cloud automation. | Scripting real-world cloud automation and data processing. |
| **⚡ FastAPI** | Modern, high performance framework with built-in async support and auto-documentation. | RESTful API design, asynchronous programming, and Swagger UI. |
| **🐘 PostgreSQL** | Robust relational database perfect for structured findings and historical cost data. | Schema normalization, SQL optimization, and data persistence. |
| **⚛️ React** | Industry standard library for building interactive, component-based dashboards. | Modern frontend development, state management, and API integration. |
| **🐳 Docker** | Ensures consistency across environments (dev vs. prod) and simplifies deployment. | Containerization fundamentals and writing efficient Dockerfiles. |
| **🏗️ Terraform** | The "Gold Standard" for Infrastructure as Code (IaC) to manage cloud resources. | IaC best practices, state management, and declarative infra. |

## Security Strategy (The "No Keys" Policy)
You will notice no AWS keys are present in the production configuration.

- In Production (ECS): The application uses IAM Task Roles. The container automatically retrieves temporary, rotating credentials from the AWS metadata service.

- In Development (Local): The app falls back to the boto3 credential chain, using `.env` file, keeping secrets strictly out of the repository.

- Database Security: The RDS instance is set to `publicly_accessible = false` and is protected by a Security Group that only allows traffic from the Backend ECS Task.

## CI/CD Pipeline
Every push to main triggers the automated workflow:

1. Checkout & Login: Authenticates with AWS and Amazon ECR.

2. Build Multi-Arch: Builds Docker images compatible with Fargate (AMD64) even if triggered from an ARM Mac.

3. Push: Uploads images to the private ECR registry.

4. Deploy: Forces a rolling update on the ECS Cluster, replacing old containers with new ones.


## Running this locally (Docker Compose)
### Clone this Project  
```bash
git clone https://github.com/wegoagain-dev/cloud-cost-optimiser.git
```
### Ensure your AWS account has the following policies

```bash
# Install AWS CLI if you haven't
# Create IAM Policy for Read-Only Access and attach to a user in AWS IAM:

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

### Modify the .env file

```bash
# AWS credentials are loaded from environment variables:
# - AWS_ACCESS_KEY_ID
# - AWS_SECRET_ACCESS_KEY  
### 1. Create Environment File
cp .env.example .env
nano .env  # Edit with your credentials
```

### Run the Docker Compose
```bash
### 2. Build Images
docker-compose build

### 3. Start Services
docker-compose up -d

### 4. Initialize Database (optional)
docker-compose exec backend python -m backend.models.database

### 5. Verify Everything Works
# Check services are running
docker-compose ps
```

**Check frontend** \
http://localhost:3000

**Check backend health** \
http://localhost:8000/health

**Check backend docs** \
http://localhost:8000/docs

## Running this using Terraform

Prerequisites: AWS CLI installed, Terraform installed.

### 1. Provision Infrastructure

```Bash
cd terraform
# Initialize and Apply
terraform init
terraform apply -var="my_ip=$(curl -s ifconfig.me)/32" 
# if issue replace $(curl -s ifconfig.me) with your public ip
```
### 2. Setup GitHub Secrets, Go to your Repo Settings -> Secrets and add:

- AWS_ACCESS_KEY_ID & AWS_SECRET_ACCESS_KEY (For the "Builder" user)

- AWS_REGION (e.g., eu-west-2)

- ECR_BACKEND_URI & ECR_FRONTEND_URI (Get these from AWS Console -> ECR)

### 3. Trigger Deployment, Simply push to main.

```Bash
git add .
git commit -m "feat: Initial deploy"
git push origin main
# Wait ~5 minutes for GitHub Actions to build and ECS to deploy.
```

## Teardown
To avoid costs, destroy the infrastructure when done.

```Bash
cd terraform
terraform destroy -var="my_ip=0.0.0.0/0"
```
## Errors encountered
---
