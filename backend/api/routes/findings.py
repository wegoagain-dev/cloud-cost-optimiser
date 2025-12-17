# backend/api/routes/findings.py
from typing import Any, Dict  # ← Add this

from backend.api import schemas
from backend.models.database import EBSFinding, EC2Finding, ScanRun, get_db
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

router = APIRouter()


@router.get("/latest", response_model=schemas.FindingsResponse)
def get_latest_findings(db: Session = Depends(get_db)):
    """Get findings from the most recent completed scan"""
    latest_scan = (
        db.query(ScanRun)
        .filter(ScanRun.status == "completed")
        .order_by(ScanRun.scan_date.desc())
        .first()
    )

    if not latest_scan:
        # Return empty structure if no scans exist
        return schemas.FindingsResponse(
            scan_id=0,
            ec2_findings=[],
            ebs_findings=[],
            summary={"total_findings": 0, "total_savings": 0},
        )

    ec2_findings = (
        db.query(EC2Finding).filter(EC2Finding.scan_run_id == latest_scan.id).all()
    )
    ebs_findings = (
        db.query(EBSFinding).filter(EBSFinding.scan_run_id == latest_scan.id).all()
    )

    # Map raw DB models to Pydantic schemas
    formatted_ec2 = [
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

    formatted_ebs = [
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
        scan_id=latest_scan.id,
        ec2_findings=formatted_ec2,
        ebs_findings=formatted_ebs,
        summary={
            "total_findings": len(formatted_ec2) + len(formatted_ebs),
            "total_savings": latest_scan.potential_monthly_savings or 0.0,
        },
    )


@router.post("/{finding_type}/{finding_id}/implement")
async def mark_as_implemented(
    finding_type: str,  # "ec2" or "ebs"
    finding_id: int,
    request: schemas.ImplementationRequest,
    db: Session = Depends(get_db),
):
    """
    Mark a finding as implemented and track savings.

    Example:
    POST /api/findings/ec2/5/implement
    {
        "action_taken": "stopped_instance",
        "notes": "Stopped during off-hours",
        "implemented_by": "admin@company.com"
    }
    """
    from backend.models.database import SavingsRealized

    # Find the finding
    if finding_type == "ec2":
        finding = db.query(EC2Finding).filter(EC2Finding.id == finding_id).first()
        if not finding:
            raise HTTPException(status_code=404, detail="EC2 finding not found")
        savings = finding.potential_monthly_savings
    elif finding_type == "ebs":
        finding = db.query(EBSFinding).filter(EBSFinding.id == finding_id).first()
        if not finding:
            raise HTTPException(status_code=404, detail="EBS finding not found")
        savings = finding.potential_monthly_savings
    else:
        raise HTTPException(
            status_code=400, detail="finding_type must be 'ec2' or 'ebs'"
        )

    # Mark as implemented
    finding.is_implemented = True
    finding.implementation_date = datetime.utcnow()
    finding.implementation_notes = request.notes

    # Track realized savings
    realized = SavingsRealized(
        finding_type=finding_type,
        finding_id=finding_id,
        action_taken=request.action_taken,
        action_date=datetime.utcnow(),
        monthly_savings_realized=savings,
        annual_savings_realized=savings * 12,
        implemented_by=request.implemented_by,
        notes=request.notes,
    )

    db.add(realized)
    db.commit()

    return schemas.ImplementationResponse(
        success=True,
        message=f"Successfully marked {finding_type} finding {finding_id} as implemented",
        monthly_savings_realized=savings,
        annual_savings_realized=savings * 12,
    )
