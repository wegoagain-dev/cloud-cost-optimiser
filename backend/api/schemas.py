"""
API Request/Response Schemas using Pydantic.

Learning: Why Pydantic?
=======================
Pydantic provides:
1. Data validation (ensure age is int, not string)
2. Type conversion (convert "123" string to 123 int)
3. Auto-generated API docs
4. Serialization (Python dict ↔ JSON)

"How do you validate API inputs?"
"Use Pydantic models for automatic validation with type hints"
"""

from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, Field, validator

# ============================================================================
# SCAN SCHEMAS
# ============================================================================


class ScanRunRequest(BaseModel):
    """
    Request to trigger a new scan.

    Example request:
    POST /api/scans/run
    {
        "region": "eu-west-2",
        "save_to_db": true
    }
    """

    region: str = Field(
        default="eu-west-2", description="AWS region to scan", example="eu-west-2"
    )
    save_to_db: bool = Field(
        default=True, description="Whether to save results to database"
    )

    @validator("region")
    def validate_region(cls, v):
        """Ensure region is valid AWS region format"""
        valid_regions = [
            "us-east-1",
            "us-east-2",
            "us-west-1",
            "us-west-2",
            "eu-west-1",
            "eu-west-2",
            "eu-west-3",
            "eu-central-1",
            "ap-southeast-1",
            "ap-southeast-2",
            "ap-northeast-1",
        ]
        if v not in valid_regions:
            raise ValueError(f"Region must be one of: {', '.join(valid_regions)}")
        return v


class ScanRunResponse(BaseModel):
    """
    Response after triggering a scan.

    Learning: Status Codes
    ======================
    200 OK - Scan completed successfully
    202 Accepted - Scan started (for async operations)
    400 Bad Request - Invalid region
    500 Internal Server Error - Scan failed
    """

    scan_id: int
    status: str
    scan_date: str
    region: str
    duration_seconds: int
    total_monthly_savings: float
    total_annual_savings: float
    total_recommendations: int

    class Config:
        # Allow ORM models (SQLAlchemy) to be converted to Pydantic
        from_attributes = True


class ScanSummary(BaseModel):
    """Brief summary of a scan (for list view)"""

    id: int
    scan_date: datetime
    region: str
    status: str
    potential_monthly_savings: float
    total_recommendations: int

    class Config:
        from_attributes = True


# ============================================================================
# FINDING SCHEMAS
# ============================================================================


class EC2FindingResponse(BaseModel):
    """Individual EC2 finding details"""

    id: int
    instance_id: str
    instance_name: str
    instance_type: str
    avg_cpu: float
    max_cpu: float
    current_monthly_cost: float
    potential_monthly_savings: float
    recommendation_type: str
    recommendation_text: str
    severity: str
    is_implemented: bool

    class Config:
        from_attributes = True


class EBSFindingResponse(BaseModel):
    """Individual EBS finding details"""

    id: int
    finding_type: str
    resource_id: str
    resource_name: Optional[str]
    size_gb: Optional[int]
    monthly_cost: float
    potential_monthly_savings: float
    recommendation_text: str
    severity: str
    is_implemented: bool

    class Config:
        from_attributes = True


class FindingsResponse(BaseModel):
    """All findings from a scan"""

    scan_id: int
    ec2_findings: List[EC2FindingResponse]
    ebs_findings: List[EBSFindingResponse]
    summary: Dict[str, float]


# ============================================================================
# DASHBOARD SCHEMAS
# ============================================================================


class DashboardSummary(BaseModel):
    """
    High-level metrics for dashboard.

    """

    last_scan_date: Optional[str]
    total_potential_monthly_savings: float
    total_potential_annual_savings: float
    total_recommendations: int
    critical_count: int
    high_count: int
    medium_count: int
    implemented_count: int
    total_realized_savings: float


class SavingsTrend(BaseModel):
    """Time-series data for charts"""

    date: str
    potential_savings: float
    realized_savings: float


# ============================================================================
# IMPLEMENTATION TRACKING
# ============================================================================


class ImplementationRequest(BaseModel):
    """
    Mark a recommendation as implemented.

    Example:
    POST /api/findings/ec2/123/implement
    {
        "action_taken": "stopped_instance",
        "notes": "Stopped dev server during nights/weekends",
        "implemented_by": "me@company.com"
    }
    """

    action_taken: str = Field(
        ...,
        description="Action taken (stopped, terminated, downsized, deleted)",
        example="stopped_instance",
    )
    notes: Optional[str] = Field(
        None, description="Additional notes about implementation"
    )
    implemented_by: str = Field(
        ..., description="Email of person who implemented", example="admin@company.com"
    )


class ImplementationResponse(BaseModel):
    """Response after marking as implemented"""

    success: bool
    message: str
    monthly_savings_realized: float
    annual_savings_realized: float


# ============================================================================
# ERROR RESPONSES
# ============================================================================


class ErrorResponse(BaseModel):
    """Standard error response"""

    error: str
    detail: Optional[str] = None
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
