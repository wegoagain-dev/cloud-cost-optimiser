# Setting it up

S3 + CloudFront for Frontend

✅ Much cheaper - pennies per month for static hosting
✅ Faster - CloudFront CDN = global edge locations
✅ Scalable - handles millions of requests easily
✅ React builds to static files anyway (HTML/CSS/JS)
✅ No container overhead for serving static files


ECS Fargate for Backend

✅ Only pay for API compute, not frontend serving
✅ Auto-scaling based on API load
✅ Your FastAPI needs to run 24/7 anyway


RDS for Database

✅ Managed backups, updates, scaling
✅ Don't need PostgreSQL in a container


```
┌─────────────────────────────────────────────────────────┐
│                    Internet Users                        │
└────────────────┬────────────────────────────────────────┘
                 │
        ┌────────▼─────────┐
        │   Route 53 (DNS) │  ← Your custom domain (optional)
        └────────┬─────────┘
                 │
        ┌────────▼──────────┐
        │   CloudFront CDN  │  ← Global edge caching
        └────────┬──────────┘
                 │
        ┌────────▼──────────┐
        │   S3 Bucket       │  ← React app (static files)
        │   (Frontend)      │
        └───────────────────┘
                 │
                 │ (API calls)
                 │
        ┌────────▼──────────────────┐
        │  Application Load Balancer│  ← Routes traffic, HTTPS
        └────────┬──────────────────┘
                 │
        ┌────────▼──────────┐
        │   ECS Fargate     │  ← FastAPI container
        │   (Backend)       │     Auto-scaling, serverless
        └────────┬──────────┘
                 │
        ┌────────▼──────────┐
        │   RDS PostgreSQL  │  ← Managed database
        │   (Database)      │     Backups, high availability
        └───────────────────┘
```

Prerequisites

## Install AWS CLI, Docker

## Phase 1: Database Setup (RDS)

**What is RDS?**
- Relational Database Service
- Managed PostgreSQL - AWS handles backups, updates, scaling
- You only manage the data and schema
