# backend/models/database.py
"""
Database models and schema for Cost Optimiser.

Learning: Database Design Principles
====================================
1. Normalization - Avoid data duplication
2. Indexing - Fast queries on common lookups
3. Foreign Keys - Maintain referential integrity
4. Timestamps - Track when data was created/modified
"""

import os
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker

# Database URL from environment variable (12-factor app pattern)
DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/cost_optimiser"
)

# Create engine
engine = create_engine(DATABASE_URL, echo=False)

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for all models
Base = declarative_base()


# ============================================================================
# CORE TABLES
# ============================================================================


class ScanRun(Base):
    """
    Represents a single scan execution.

    Learning: Why a separate table for scan runs?
    ==============================================
    - Track scan history (when, what region, how long)
    - Group all findings from one scan together
    - Calculate trends (savings increasing/decreasing?)
    - Audit trail (who ran scan, when)

    "How would you track cost savings over time?"
    A: "Store scan runs with timestamps, then query findings
             grouped by scan_run_id to see trends."
    """

    __tablename__ = "scan_runs"

    id = Column(Integer, primary_key=True, index=True)
    scan_date = Column(DateTime, default=datetime.utcnow, index=True)
    region = Column(String(50), nullable=False, index=True)
    status = Column(String(20), default="running")  # running, completed, failed

    # Summary metrics (denormalized for quick access)
    total_resources_scanned = Column(Integer, default=0)
    total_recommendations = Column(Integer, default=0)
    potential_monthly_savings = Column(Float, default=0.0)
    potential_annual_savings = Column(Float, default=0.0)

    # Scan performance
    scan_duration_seconds = Column(Integer)

    # Metadata
    scanner_version = Column(String(20))
    notes = Column(Text)

    # Relationships (one scan has many findings)
    ec2_findings = relationship(
        "EC2Finding", back_populates="scan_run", cascade="all, delete-orphan"
    )
    ebs_findings = relationship(
        "EBSFinding", back_populates="scan_run", cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<ScanRun(id={self.id}, date={self.scan_date}, region={self.region})>"


class EC2Finding(Base):
    """
    Individual EC2 instance finding.

    Learning: Granular Data Storage
    ================================
    Store each recommendation separately so you can:
    - Filter by severity
    - Track if recommendation was implemented
    - Show detailed instance-level reports
    """

    __tablename__ = "ec2_findings"

    id = Column(Integer, primary_key=True, index=True)
    scan_run_id = Column(
        Integer, ForeignKey("scan_runs.id"), nullable=False, index=True
    )

    # Instance details
    instance_id = Column(String(50), nullable=False, index=True)
    instance_name = Column(String(255))
    instance_type = Column(String(50))
    instance_state = Column(String(20))
    launch_date = Column(DateTime)

    # Metrics
    avg_cpu_utilization = Column(Float)
    max_cpu_utilization = Column(Float)
    min_cpu_utilization = Column(Float)
    cpu_datapoints = Column(Integer)

    # Costs
    current_monthly_cost = Column(Float)
    potential_monthly_savings = Column(Float)
    potential_annual_savings = Column(Float)

    # Recommendation
    recommendation_type = Column(String(50))  # schedule, downsize, terminate, none
    recommendation_text = Column(Text)
    severity = Column(String(20), index=True)  # critical, high, medium, low, info

    # All scenarios (JSON for flexibility)
    savings_scenarios = Column(JSON)

    # Tracking
    is_implemented = Column(Boolean, default=False)
    implementation_date = Column(DateTime)
    implementation_notes = Column(Text)

    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    scan_run = relationship("ScanRun", back_populates="ec2_findings")

    def __repr__(self):
        return f"<EC2Finding(id={self.id}, instance={self.instance_id}, severity={self.severity})>"


class EBSFinding(Base):
    """
    EBS volume or snapshot finding.

    Learning: Polymorphic Data
    ==========================
    This table stores both volume AND snapshot findings.
    Alternative: Separate tables (ebs_volumes, ebs_snapshots)
    But one table for now because they share most attributes.
    """

    __tablename__ = "ebs_findings"

    id = Column(Integer, primary_key=True, index=True)
    scan_run_id = Column(
        Integer, ForeignKey("scan_runs.id"), nullable=False, index=True
    )

    # Type of finding
    finding_type = Column(
        String(50), index=True
    )  # unattached_volume, old_snapshot, type_optimisation, low_activity

    # Resource details (some fields only apply to volumes or snapshots)
    resource_id = Column(
        String(100), nullable=False, index=True
    )  # volume-id or snapshot-id
    resource_name = Column(String(255))

    # Volume-specific
    volume_type = Column(String(20))
    size_gb = Column(Integer)
    is_attached = Column(Boolean)
    attached_instance_id = Column(String(50))

    # Snapshot-specific
    source_volume_id = Column(String(50))
    is_ami_snapshot = Column(Boolean, default=False)

    # Age
    created_date = Column(DateTime)
    age_days = Column(Integer)

    # Costs
    monthly_cost = Column(Float)
    potential_monthly_savings = Column(Float)
    annual_cost = Column(Float)

    # Recommendation
    recommendation_text = Column(Text)
    severity = Column(String(20), index=True)

    # For type optimisations
    current_type = Column(String(20))
    recommended_type = Column(String(20))

    # I/O stats (for low activity volumes)
    io_stats = Column(JSON)

    # Tracking
    is_implemented = Column(Boolean, default=False)
    implementation_date = Column(DateTime)
    implementation_notes = Column(Text)

    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    scan_run = relationship("ScanRun", back_populates="ebs_findings")

    def __repr__(self):
        return f"<EBSFinding(id={self.id}, type={self.finding_type}, resource={self.resource_id})>"


class SavingsRealized(Base):
    """
    Track when recommendations are actually implemented.

    Learning: Business Value Tracking
    ==================================
    "We saved $... last quarter by implementing these recommendations"

    "How to prove ROI of cost optimisation?"
    "Track implemented recommendations in this table,
             sum up savings_realized, show quarterly reports."
    """

    __tablename__ = "savings_realized"

    id = Column(Integer, primary_key=True, index=True)

    # Link to original finding
    finding_type = Column(String(20))  # ec2 or ebs
    finding_id = Column(Integer)  # ID of EC2Finding or EBSFinding

    # Action details
    action_taken = Column(String(100))  # stopped, terminated, downsized, deleted
    action_date = Column(DateTime, default=datetime.utcnow, index=True)

    # Financial impact
    monthly_savings_realized = Column(Float)
    annual_savings_realized = Column(Float)

    # Audit trail
    implemented_by = Column(String(100))  # user email or "automated"
    notes = Column(Text)

    created_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<SavingsRealized(id={self.id}, action={self.action_taken}, savings=${self.monthly_savings_realized}/mo)>"


class DailyCost(Base):
    """
    Time-series table for cost trends.

    Learning: Time-Series Data
    ==========================
    Store daily AWS costs to show trends over time.
    In production, better to use TimescaleDB extension for better performance.

    "How to show cost trends over 6 months?"
    "Storing daily costs in this table, query with GROUP BY MONTH,
             show line chart of monthly totals."
    """

    __tablename__ = "daily_costs"

    id = Column(Integer, primary_key=True, index=True)
    date = Column(DateTime, nullable=False, index=True)

    # Cost breakdown
    service = Column(String(50), index=True)  # EC2, EBS, RDS, etc.
    region = Column(String(50), index=True)

    # Amounts
    total_cost = Column(Float)

    # Metadata
    currency = Column(String(10), default="USD")

    created_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<DailyCost(date={self.date}, service={self.service}, cost=${self.total_cost})>"


# ============================================================================
# DATABASE INITIALIZATION
# ============================================================================


def init_db():
    """
    Create all tables in the database.

    Learning: Database Migration
    =============================
    In production, use Alembic for migrations (version control for DB schema).
    For learning, we'll create tables directly.
    """
    Base.metadata.create_all(bind=engine)
    print("✅ Database tables created successfully!")


def get_db():
    """
    Dependency for FastAPI - provides database session.

    Learning: Dependency Injection Pattern
    =======================================
    FastAPI calls this function for each request.
    Ensures proper session management (open/close).
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def reset_db():
    """
    Drop and recreate all tables (DANGER - deletes all data!).
    Only use during development.
    """
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    print("⚠️  Database reset complete! All data deleted.")


# ============================================================================
# EXAMPLE USAGE
# ============================================================================

if __name__ == "__main__":
    """Test database setup"""
    print("Creating database tables...")
    init_db()

    # Test connection
    db = SessionLocal()

    # Create a test scan run
    test_scan = ScanRun(
        region="eu-west-2",
        status="completed",
        total_resources_scanned=10,
        potential_monthly_savings=500.00,
    )

    db.add(test_scan)
    db.commit()

    print(f"✅ Test scan created: {test_scan}")

    # Query it back
    scan = db.query(ScanRun).first()
    print(f"✅ Retrieved scan: {scan}")

    db.close()
