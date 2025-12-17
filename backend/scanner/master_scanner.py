# backend/scanner/master_scanner.py
"""
Master Cost Optimizer Scanner
Orchestrates all individual scanners and generates comprehensive report.
"""

import json
import os  # Needed for environment variables
import time
from datetime import datetime
from typing import Dict

from backend.models.database import EBSFinding, EC2Finding, ScanRun, SessionLocal
from sqlalchemy import text

from .ebs_scanner import EBSScanner
from .ec2_scanner import EC2Scanner


class MasterScanner:
    """
    Orchestrates all cost optimization scanners.

    Learning: Design Pattern - Facade Pattern
    ==========================================
    This class provides a simple interface to complex subsystems.
    """

    # FIX 1: Default region set to eu-west-2 (London)
    def __init__(self, region: str = "eu-west-2", profile_name: str = None):
        self.region = region
        self.profile_name = profile_name

        # Initialize all scanners
        self.ec2_scanner = EC2Scanner(region, profile_name)
        self.ebs_scanner = EBSScanner(region, profile_name)

    def scan(self, save_to_db: bool = True) -> Dict:
        """Run all scanners and generate comprehensive report"""
        start_time = time.time()

        print("\n" + "=" * 70)
        print("CLOUD COST OPTIMIZATION - FULL SCAN")
        print("=" * 70)
        print(f"Region: {self.region}")
        print(f"Start Time: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}")
        print("=" * 70)
        print()

        # Run EC2 scan
        print("🔍 PHASE 1: EC2 INSTANCE ANALYSIS")
        print("-" * 70)
        ec2_results = self.ec2_scanner.scan()
        print()

        # Run EBS scan
        print("🔍 PHASE 2: EBS STORAGE ANALYSIS")
        print("-" * 70)
        ebs_results = self.ebs_scanner.scan()
        print()

        # Safely extract savings (handle empty results)
        ec2_monthly_savings = ec2_results.get("potential_savings", {}).get("monthly", 0)
        ebs_monthly_savings = ebs_results.get("potential_savings", {}).get("monthly", 0)

        total_monthly = ec2_monthly_savings + ebs_monthly_savings
        total_annual = total_monthly * 12

        scan_duration = int(time.time() - start_time)

        # Generate final report
        report = {
            "scan_metadata": {
                "scan_date": datetime.utcnow().isoformat(),
                "region": self.region,
                "scanners_run": ["EC2", "EBS"],
                "scan_duration_seconds": scan_duration,
            },
            "ec2_findings": ec2_results,
            "ebs_findings": ebs_results,
            "executive_summary": {
                "total_monthly_savings": round(total_monthly, 2),
                "total_annual_savings": round(total_annual, 2),
                "total_recommendations": (
                    len(ec2_results.get("recommendations", []))
                    + ebs_results.get("summary", {}).get("total_findings", 0)
                ),
                "critical_items": (
                    ec2_results.get("summary", {}).get("critical", 0)
                    + ebs_results.get("summary", {}).get("critical_severity", 0)
                ),
                "high_priority_items": (
                    ec2_results.get("summary", {}).get("high", 0)
                    + ebs_results.get("summary", {}).get("high_severity", 0)
                ),
            },
        }

        # Print executive summary
        print("=" * 70)
        print("📊 EXECUTIVE SUMMARY")
        print("=" * 70)
        print(f"Total EC2 Savings:        ${ec2_monthly_savings:>10,.2f}/month")
        print(f"Total EBS Savings:        ${ebs_monthly_savings:>10,.2f}/month")
        print("-" * 70)
        print(f"TOTAL MONTHLY SAVINGS:    ${total_monthly:>10,.2f}")
        print(f"TOTAL ANNUAL SAVINGS:     ${total_annual:>10,.2f}")
        print("=" * 70)
        print(
            f"Critical Issues:          {report['executive_summary']['critical_items']:>10}"
        )
        print(
            f"High Priority Issues:     {report['executive_summary']['high_priority_items']:>10}"
        )
        print(
            f"Total Recommendations:    {report['executive_summary']['total_recommendations']:>10}"
        )
        print("=" * 70)

        # Save to database
        if save_to_db and total_monthly > 0:
            try:
                scan_run_id = self._save_to_database(report)
                report["scan_metadata"]["scan_run_id"] = scan_run_id
                print(f"\n✅ Results saved to database (scan_run_id: {scan_run_id})")
            except Exception as e:
                print(f"\n⚠️  Warning: Could not save to database: {e}")
                print("Continuing without database storage...")
        elif total_monthly == 0:
            print(
                f"\nℹ️  No findings to save (no cost optimization opportunities found)"
            )

        return report

    def _save_to_database(self, report: Dict) -> int:
        """Save scan results to PostgreSQL"""
        db = SessionLocal()

        try:
            # Create scan run record
            scan_run = ScanRun(
                scan_date=datetime.utcnow(),
                region=self.region,
                status="completed",
                total_resources_scanned=(
                    report["ec2_findings"].get("instances_scanned", 0)
                    + report["ebs_findings"].get("summary", {}).get("total_findings", 0)
                ),
                total_recommendations=report["executive_summary"][
                    "total_recommendations"
                ],
                potential_monthly_savings=report["executive_summary"][
                    "total_monthly_savings"
                ],
                potential_annual_savings=report["executive_summary"][
                    "total_annual_savings"
                ],
                scan_duration_seconds=report["scan_metadata"]["scan_duration_seconds"],
                scanner_version="1.0.0",
            )

            db.add(scan_run)
            db.flush()

            # 1. Save EC2 findings
            for rec in report["ec2_findings"].get("recommendations", []):
                finding = EC2Finding(
                    scan_run_id=scan_run.id,
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

            # 2. Save EBS findings - unattached volumes
            for vol in (
                report["ebs_findings"]
                .get("findings", {})
                .get("unattached_volumes", {})
                .get("items", [])
            ):
                finding = EBSFinding(
                    scan_run_id=scan_run.id,
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

            # (Step 3: Optimizations & Snapshots omitted as requested)

            db.commit()
            return scan_run.id

        except Exception as e:
            db.rollback()
            print(f"❌ Error saving to database: {e}")
            raise
        finally:
            db.close()


if __name__ == "__main__":
    """Run full cost optimization scan"""

    # Check if database is available
    try:
        db = SessionLocal()
        db.execute(text("SELECT 1"))
        db.close()
        print("✅ Database connection successful\n")
    except Exception as e:
        print(f"⚠️  Warning: Database not available: {e}")
        print("Run 'docker-compose up -d postgres' to start database")
        print("Continuing with scan (results won't be saved)...\n")

    # FIX 2: Profile Name Handling
    # This prevents the crash by falling back to 'default' if 'AWS_PROFILE' isn't set
    profile = os.getenv("AWS_PROFILE", "default")

    # Run scanner with corrected region
    scanner = MasterScanner(region="eu-west-2", profile_name=profile)

    results = scanner.scan(save_to_db=True)

    # Save comprehensive report to JSON
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    filename = f"cost_optimization_report_{timestamp}.json"

    with open(filename, "w") as f:
        json.dump(results, f, indent=2)

    print(f"\n✅ Full report saved to: {filename}")
