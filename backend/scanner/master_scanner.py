# backend/scanner/master_scanner.py
"""
Master Cost Optimizer Scanner
Orchestrates all individual scanners and generates comprehensive report.
"""

import json
import os
import random
import time
from datetime import datetime, timedelta
from typing import Dict

from backend.models.database import EBSFinding, EC2Finding, ScanRun, SessionLocal
from sqlalchemy import text

from .ebs_scanner import EBSScanner
from .ec2_scanner import EC2Scanner


class MasterScanner:
    """
    Orchestrates all cost optimization scanners.

    Design Pattern - Facade Pattern:
    This class provides a simple interface to complex subsystems.
    """

    def __init__(self, region: str = "eu-west-2"):
        self.region = region

        # Check for Demo Mode (env var DEMO_MODE=true)
        self.is_demo_mode = os.getenv("DEMO_MODE", "false").lower() == "true"

        # Only initialize real scanners if NOT in demo mode
        if not self.is_demo_mode:
            self.ec2_scanner = EC2Scanner(region, profile_name)
            self.ebs_scanner = EBSScanner(region, profile_name)

    def scan(self, save_to_db: bool = True) -> Dict:
        """Run all scanners (or generate demo data) and generate comprehensive report"""

        # ---------------------------------------------------------
        # DEMO MODE INTERCEPT
        # ---------------------------------------------------------
        if self.is_demo_mode:
            print(f"\n🧪 RUNNING IN DEMO MODE (Fake Data)")
            print("=" * 70)
            # Simulate scan time
            time.sleep(2)
            results = self._generate_demo_data()

            # Print fake summary for CLI user
            self._print_summary(results)

            # Save to database (so it appears in frontend)
            if save_to_db:
                try:
                    scan_run_id = self._save_to_database(results)
                    results["scan_metadata"]["scan_run_id"] = scan_run_id
                    print(
                        f"\n✅ Demo results saved to database (scan_run_id: {scan_run_id})"
                    )
                except Exception as e:
                    print(f"\n⚠️  Warning: Could not save demo data to database: {e}")

            return results

        # ---------------------------------------------------------
        # REAL SCAN LOGIC
        # ---------------------------------------------------------
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
        self._print_summary(report)

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

    def _print_summary(self, report):
        """Helper to print the CLI summary"""
        summary = report["executive_summary"]
        print("=" * 70)
        print("📊 EXECUTIVE SUMMARY")
        print("=" * 70)
        print(f"TOTAL MONTHLY SAVINGS:    ${summary['total_monthly_savings']:>10,.2f}")
        print(f"TOTAL ANNUAL SAVINGS:     ${summary['total_annual_savings']:>10,.2f}")
        print("=" * 70)
        print(f"Critical Issues:          {summary['critical_items']:>10}")
        print(f"High Priority Issues:     {summary['high_priority_items']:>10}")
        print(f"Total Recommendations:    {summary['total_recommendations']:>10}")
        print("=" * 70)

    def _generate_demo_data(self) -> Dict:
        """Generates realistic mock data for portfolio/demo purposes"""
        return {
            "scan_metadata": {
                "scan_date": datetime.utcnow().isoformat(),
                "region": self.region,
                "scanners_run": ["EC2", "EBS"],
                "scan_duration_seconds": 3,
            },
            "ec2_findings": {
                "instances_scanned": 15,
                "recommendations": [
                    {
                        "instance_id": "i-demo-web-prod",
                        "instance_name": "legacy-web-prod",
                        "instance_type": "m5.large",
                        "metrics": {
                            "avg_cpu": 2.5,
                            "max_cpu": 12.0,
                            "min_cpu": 0.5,
                            "datapoints": 1440,
                        },
                        "costs": {"current_monthly_cost": 76.00},
                        "recommendation": {
                            "action": "Rightsize",
                            "reason": "Instance is underutilized (Avg CPU < 3%). Downgrade to t3.medium.",
                            "primary_savings": 42.50,
                            "annual_impact": 510.00,
                            "severity": "high",
                        },
                        "all_scenarios": {},
                    },
                    {
                        "instance_id": "i-demo-test-worker",
                        "instance_name": "dev-test-worker",
                        "instance_type": "t3.xlarge",
                        "metrics": {
                            "avg_cpu": 0.1,
                            "max_cpu": 0.5,
                            "min_cpu": 0.0,
                            "datapoints": 1440,
                        },
                        "costs": {"current_monthly_cost": 120.00},
                        "recommendation": {
                            "action": "Terminate",
                            "reason": "Idle instance detected. CPU < 1% for 7 days.",
                            "primary_savings": 120.00,
                            "annual_impact": 1440.00,
                            "severity": "critical",
                        },
                        "all_scenarios": {},
                    },
                ],
                "summary": {"critical": 1, "high": 1},
            },
            "ebs_findings": {
                "findings": {
                    "unattached_volumes": {
                        "items": [
                            {
                                "volume_id": "vol-demo-unused",
                                "name": "old-backup-data",
                                "type": "gp2",
                                "size_gb": 500,
                                "age_days": 45,
                                "monthly_cost": 50.00,
                                "annual_cost": 600.00,
                                "recommendation": "Delete unattached volume (detached 45 days ago)",
                                "severity": "medium",
                            }
                        ]
                    },
                    "volume_optimizations": {
                        "items": [
                            {
                                "volume_id": "vol-demo-io1",
                                "current_type": "io1",
                                "recommended_type": "gp3",
                                "size_gb": 1000,
                                "current_monthly_cost": 225.00,
                                "monthly_savings": 145.00,
                                "reason": "Migrate IO1 to GP3 for 4x cost efficiency",
                                "severity": "high",
                            }
                        ]
                    },
                },
                "summary": {
                    "total_findings": 2,
                    "critical_severity": 0,
                    "high_severity": 1,
                },
            },
            "executive_summary": {
                "total_monthly_savings": 357.50,
                "total_annual_savings": 4290.00,
                "total_recommendations": 4,
                "critical_items": 1,
                "high_priority_items": 2,
            },
        }

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

            # 3. Save EBS findings - volume optimizations
            for opt in (
                report["ebs_findings"]
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

    # Run scanner (Demo Mode is checked internally)
    scanner = MasterScanner(region="eu-west-2")

    results = scanner.scan(save_to_db=True)

    # Save comprehensive report to JSON
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    filename = f"cost_optimization_report_{timestamp}.json"

    with open(filename, "w") as f:
        json.dump(results, f, indent=2)

    print(f"\n✅ Full report saved to: {filename}")
