# backend/api/routes/scans.py

import os
import time
from datetime import datetime
from typing import List

from backend.api import schemas
from backend.models.database import (
    EBSFinding,
    EC2Finding,
    ScanRun,
    SessionLocal,  # Needed for background tasks
    get_db,
)
from backend.scanner.master_scanner import MasterScanner
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import desc
from sqlalchemy.orm import Session

router = APIRouter()


@router.get("/", response_model=List[schemas.ScanSummary])
async def list_scans(limit: int = 10, offset: int = 0, db: Session = Depends(get_db)):
    """Get list of all scans."""
    scans = (
        db.query(ScanRun)
        .order_by(desc(ScanRun.scan_date))
        .limit(limit)
        .offset(offset)
        .all()
    )
    return scans


@router.get("/{scan_id}", response_model=schemas.ScanRunResponse)
async def get_scan(scan_id: int, db: Session = Depends(get_db)):
    """Get details of a specific scan."""
    scan = db.query(ScanRun).filter(ScanRun.id == scan_id).first()
    if not scan:
        raise HTTPException(status_code=404, detail=f"Scan with id {scan_id} not found")

    return schemas.ScanRunResponse(
        scan_id=scan.id,
        status=scan.status,
        scan_date=scan.scan_date.isoformat(),
        region=scan.region,
        duration_seconds=scan.scan_duration_seconds or 0,
        total_monthly_savings=scan.potential_monthly_savings or 0.0,
        total_annual_savings=scan.potential_annual_savings or 0.0,
        total_recommendations=scan.total_recommendations or 0,
    )


@router.post("/run", response_model=schemas.ScanRunResponse, status_code=202)
async def trigger_scan(
    request: schemas.ScanRunRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Trigger a new cost optimization scan."""
    # Create scan record immediately with "running" status
    scan_run = ScanRun(
        scan_date=datetime.utcnow(),
        region=request.region,
        status="running",
        scanner_version="1.0.0",
    )
    db.add(scan_run)
    db.commit()
    db.refresh(scan_run)

    # Run scan in background
    background_tasks.add_task(
        run_scan_task, scan_run.id, request.region, request.save_to_db
    )

    return schemas.ScanRunResponse(
        scan_id=scan_run.id,
        status="running",
        scan_date=scan_run.scan_date.isoformat(),
        region=scan_run.region,
        duration_seconds=0,
        total_monthly_savings=0.0,
        total_annual_savings=0.0,
        total_recommendations=0,
    )


def run_scan_task(scan_run_id: int, region: str, save_to_db: bool):
    """Background task that runs the actual scan."""
    db = SessionLocal()  # Use new session for background task

    try:
        start_time = time.time()

        # Initialize MasterScanner without profile argument.
        # It handles Demo Mode and Auth automatically now.
        scanner = MasterScanner(region=region)

        # Run scan but DO NOT let MasterScanner save to DB internal method.
        # We save it here to associate with the existing 'running' scan_run_id
        results = scanner.scan(save_to_db=False)

        duration = int(time.time() - start_time)

        # Update scan run with results
        scan_run = db.query(ScanRun).filter(ScanRun.id == scan_run_id).first()
        scan_run.status = "completed"
        scan_run.scan_duration_seconds = duration
        scan_run.potential_monthly_savings = results["executive_summary"][
            "total_monthly_savings"
        ]
        scan_run.potential_annual_savings = results["executive_summary"][
            "total_annual_savings"
        ]
        scan_run.total_recommendations = results["executive_summary"][
            "total_recommendations"
        ]
        scan_run.total_resources_scanned = results["ec2_findings"].get(
            "instances_scanned", 0
        ) + results["ebs_findings"].get("summary", {}).get("total_findings", 0)

        if save_to_db:
            # 1. Save EC2 findings
            for rec in results["ec2_findings"].get("recommendations", []):
                finding = EC2Finding(
                    scan_run_id=scan_run_id,
                    instance_id=rec["instance_id"],
                    instance_name=rec["instance_name"],
                    instance_type=rec["instance_type"],
                    avg_cpu_utilization=rec["metrics"]["avg_cpu"],
                    max_cpu_utilization=rec["metrics"]["max_cpu"],
                    min_cpu_utilization=rec["metrics"].get("min_cpu", 0),
                    cpu_datapoints=rec["metrics"]["datapoints"],
                    current_monthly_cost=rec["costs"]["current_monthly_cost"],
                    potential_monthly_savings=rec["recommendation"]["primary_savings"],
                    potential_annual_savings=rec["recommendation"]["annual_impact"],
                    recommendation_type=rec["recommendation"]["action"],
                    recommendation_text=rec["recommendation"]["reason"],
                    severity=rec["recommendation"]["severity"],
                    savings_scenarios=rec["all_scenarios"],
                )
                db.add(finding)

            # 2. Save EBS Unattached Volumes
            for vol in (
                results["ebs_findings"]
                .get("findings", {})
                .get("unattached_volumes", {})
                .get("items", [])
            ):
                finding = EBSFinding(
                    scan_run_id=scan_run_id,
                    finding_type="unattached_volume",
                    resource_id=vol["volume_id"],
                    resource_name=vol["name"],
                    volume_type=vol["type"],
                    size_gb=vol["size_gb"],
                    is_attached=False,
                    age_days=vol["age_days"],
                    monthly_cost=vol["monthly_cost"],
                    potential_monthly_savings=vol["monthly_cost"],
                    annual_cost=vol["annual_cost"],
                    recommendation_text=vol["recommendation"],
                    severity=vol["severity"],
                )
                db.add(finding)

            # 3. Save EBS Volume Optimizations
            for opt in (
                results["ebs_findings"]
                .get("findings", {})
                .get("volume_optimizations", {})
                .get("items", [])
            ):
                finding = EBSFinding(
                    scan_run_id=scan_run.id,
                    finding_type="type_optimization",
                    resource_id=opt["volume_id"],
                    resource_name="Volume Optimization",
                    volume_type=opt["current_type"],
                    recommended_type=opt["recommended_type"],
                    size_gb=opt["size_gb"],
                    is_attached=True,
                    monthly_cost=opt["current_monthly_cost"],
                    potential_monthly_savings=opt["monthly_savings"],
                    annual_cost=opt["current_monthly_cost"] * 12,
                    recommendation_text=opt["reason"],
                    severity=opt["severity"],
                )
                db.add(finding)

        db.commit()

    except Exception as e:
        db.rollback()
        scan_run = db.query(ScanRun).filter(ScanRun.id == scan_run_id).first()
        if scan_run:
            scan_run.status = "failed"
            scan_run.notes = f"Error: {str(e)}"
            db.commit()
        print(f"❌ Scan {scan_run_id} failed: {e}")
    finally:
        db.close()


@router.delete("/{scan_id}")
async def delete_scan(scan_id: int, db: Session = Depends(get_db)):
    scan = db.query(ScanRun).filter(ScanRun.id == scan_id).first()
    if not scan:
        raise HTTPException(status_code=404, detail="Scan not found")
    db.delete(scan)
    db.commit()
    return {"message": f"Scan {scan_id} deleted successfully"}


@router.get("/{scan_id}/findings", response_model=schemas.FindingsResponse)
async def get_scan_findings(scan_id: int, db: Session = Depends(get_db)):
    """
    Get all findings from a specific scan.

    This allows frontend to view historical scan results.
    """
    scan = db.query(ScanRun).filter(ScanRun.id == scan_id).first()

    if not scan:
        raise HTTPException(status_code=404, detail=f"Scan {scan_id} not found")

    ec2_findings = db.query(EC2Finding).filter(EC2Finding.scan_run_id == scan_id).all()
    ebs_findings = db.query(EBSFinding).filter(EBSFinding.scan_run_id == scan_id).all()

    # Convert to response schemas
    ec2_list = [
        schemas.EC2FindingResponse(
            id=f.id,
            instance_id=f.instance_id,
            instance_name=f.instance_name or "Unknown",
            instance_type=f.instance_type,
            avg_cpu=f.avg_cpu_utilization or 0.0,
            max_cpu=f.max_cpu_utilization or 0.0,
            current_monthly_cost=f.current_monthly_cost or 0.0,
            potential_monthly_savings=f.potential_monthly_savings or 0.0,
            recommendation_type=f.recommendation_type or "none",
            recommendation_text=f.recommendation_text or "",
            severity=f.severity or "low",
            is_implemented=f.is_implemented,
        )
        for f in ec2_findings
    ]

    ebs_list = [
        schemas.EBSFindingResponse(
            id=f.id,
            finding_type=f.finding_type,
            resource_id=f.resource_id,
            resource_name=f.resource_name,
            size_gb=f.size_gb,
            monthly_cost=f.monthly_cost or 0.0,
            potential_monthly_savings=f.potential_monthly_savings or 0.0,
            recommendation_text=f.recommendation_text,
            severity=f.severity or "low",
            is_implemented=f.is_implemented,
        )
        for f in ebs_findings
    ]

    return schemas.FindingsResponse(
        scan_id=scan_id,
        ec2_findings=ec2_list,
        ebs_findings=ebs_list,
        summary={
            "total_findings": len(ec2_list) + len(ebs_list),
            "total_savings": scan.potential_monthly_savings or 0.0,
        },
    )
