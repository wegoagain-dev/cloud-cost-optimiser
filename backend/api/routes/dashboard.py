# backend/api/routes/dashboard.py

from backend.api import schemas
from backend.models.database import (
    EBSFinding,
    EC2Finding,
    SavingsRealized,
    ScanRun,
    get_db,
)
from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

router = APIRouter()


@router.get("/stats", response_model=schemas.DashboardSummary)
def get_dashboard_stats(db: Session = Depends(get_db)):
    """Get high-level dashboard metrics"""
    latest_scan = (
        db.query(ScanRun)
        .filter(ScanRun.status == "completed")
        .order_by(ScanRun.scan_date.desc())
        .first()
    )

    if not latest_scan:
        return {
            "last_scan_date": None,
            "total_potential_monthly_savings": 0.0,
            "total_potential_annual_savings": 0.0,
            "total_recommendations": 0,
            "critical_count": 0,
            "high_count": 0,
            "medium_count": 0,
            "implemented_count": 0,
            "total_realized_savings": 0.0,
        }

    # Count severities
    crit_ec2 = (
        db.query(EC2Finding)
        .filter(
            EC2Finding.scan_run_id == latest_scan.id, EC2Finding.severity == "critical"
        )
        .count()
    )
    crit_ebs = (
        db.query(EBSFinding)
        .filter(
            EBSFinding.scan_run_id == latest_scan.id, EBSFinding.severity == "critical"
        )
        .count()
    )

    high_ec2 = (
        db.query(EC2Finding)
        .filter(EC2Finding.scan_run_id == latest_scan.id, EC2Finding.severity == "high")
        .count()
    )
    high_ebs = (
        db.query(EBSFinding)
        .filter(EBSFinding.scan_run_id == latest_scan.id, EBSFinding.severity == "high")
        .count()
    )

    med_ec2 = (
        db.query(EC2Finding)
        .filter(
            EC2Finding.scan_run_id == latest_scan.id, EC2Finding.severity == "medium"
        )
        .count()
    )
    med_ebs = (
        db.query(EBSFinding)
        .filter(
            EBSFinding.scan_run_id == latest_scan.id, EBSFinding.severity == "medium"
        )
        .count()
    )

    # Calculate realized savings
    realized = (
        db.query(func.sum(SavingsRealized.monthly_savings_realized)).scalar() or 0.0
    )
    implemented_count = db.query(SavingsRealized).count()

    return {
        "last_scan_date": latest_scan.scan_date.isoformat(),
        "total_potential_monthly_savings": latest_scan.potential_monthly_savings or 0.0,
        "total_potential_annual_savings": latest_scan.potential_annual_savings or 0.0,
        "total_recommendations": latest_scan.total_recommendations or 0,
        "critical_count": crit_ec2 + crit_ebs,
        "high_count": high_ec2 + high_ebs,
        "medium_count": med_ec2 + med_ebs,
        "implemented_count": implemented_count,
        "total_realized_savings": realized,
    }
