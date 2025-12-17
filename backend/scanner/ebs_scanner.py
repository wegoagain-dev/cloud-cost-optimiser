"""
EBS Cost Scanner
Identifies unused EBS volumes and expensive snapshots.

Region: eu-west-2 (London)
"""

import os
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import boto3


@dataclass
class VolumeRecommendation:
    """Data class for volume recommendations"""

    volume_id: str
    size_gb: int
    volume_type: str
    monthly_cost: float
    recommendation: str
    severity: str
    potential_savings: float


class EBSScanner:
    """
    Scans EBS volumes and snapshots for cost optimization.
    """

    def __init__(self, region: str = "eu-west-2", profile_name: str = None):
        """Initialize AWS clients"""
        session = boto3.Session(profile_name=profile_name, region_name=region)

        self.ec2 = session.client("ec2")
        self.cloudwatch = session.client("cloudwatch")
        self.region = region

        # London is approx 20% more expensive than us-east-1
        self.volume_pricing = {
            "gp3": 0.096,  # US: 0.08
            "gp2": 0.12,  # US: 0.10
            "io1": 0.14,  # US: 0.125
            "io2": 0.14,  # US: 0.125
            "st1": 0.054,  # US: 0.045
            "sc1": 0.018,  # US: 0.015
            "standard": 0.06,  # Magnetic (deprecated)
        }

        self.snapshot_pricing = 0.053  # London snapshot price

    def get_all_volumes(self) -> List[Dict]:
        """Retrieve all EBS volumes."""
        volumes = []
        paginator = self.ec2.get_paginator("describe_volumes")

        print(f"Fetching EBS volumes for {self.region}...")

        for page in paginator.paginate():
            for volume in page["Volumes"]:
                volumes.append(
                    {
                        "id": volume["VolumeId"],
                        "size": volume["Size"],
                        "type": volume["VolumeType"],
                        "state": volume["State"],
                        "created": volume["CreateTime"],
                        "attachments": volume["Attachments"],
                        "tags": volume.get("Tags", []),
                        "encrypted": volume.get("Encrypted", False),
                        "iops": volume.get("Iops"),
                        "throughput": volume.get("Throughput"),
                    }
                )

        print(f"Found {len(volumes)} volumes\n")
        return volumes

    def find_unattached_volumes(self) -> List[Dict]:
        """Find volumes not attached to any instance."""
        all_volumes = self.get_all_volumes()
        unattached = []

        for volume in all_volumes:
            if volume["state"] == "available":  # Not attached
                age_days = (
                    datetime.now(volume["created"].tzinfo) - volume["created"]
                ).days

                monthly_cost = self._calculate_volume_cost(
                    volume["size"], volume["type"]
                )

                # Determine severity based on age and cost
                if age_days > 90:
                    severity = "critical"
                elif age_days > 30:
                    severity = "high"
                elif age_days > 7:
                    severity = "medium"
                else:
                    severity = "low"

                unattached.append(
                    {
                        "volume_id": volume["id"],
                        "size_gb": volume["size"],
                        "type": volume["type"],
                        "created_date": volume["created"].strftime("%Y-%m-%d"),
                        "age_days": age_days,
                        "monthly_cost": monthly_cost,
                        "annual_cost": round(monthly_cost * 12, 2),
                        "severity": severity,
                        "recommendation": self._get_unattached_recommendation(age_days),
                        "name": self._extract_name_tag(volume["tags"]),
                    }
                )

        return unattached

    def find_low_activity_volumes(self, days: int = 7) -> List[Dict]:
        """Find attached volumes with no I/O activity."""
        all_volumes = self.get_all_volumes()
        low_activity = []

        # Only check attached volumes
        attached_volumes = [v for v in all_volumes if v["state"] == "in-use"]

        print(f"Checking I/O activity for {len(attached_volumes)} attached volumes...")

        for volume in attached_volumes:
            io_stats = self._get_volume_io_stats(volume["id"], days)

            # If total I/O is extremely low, flag it
            total_io = io_stats["total_read_ops"] + io_stats["total_write_ops"]

            if total_io < 100:  # Less than 100 operations in a week
                monthly_cost = self._calculate_volume_cost(
                    volume["size"], volume["type"]
                )

                low_activity.append(
                    {
                        "volume_id": volume["id"],
                        "size_gb": volume["size"],
                        "type": volume["type"],
                        "instance_id": volume["attachments"][0]["InstanceId"]
                        if volume["attachments"]
                        else None,
                        "io_stats": io_stats,
                        "monthly_cost": monthly_cost,
                        "severity": "medium",
                        "recommendation": "Volume has no I/O activity. Verify if still needed.",
                        "name": self._extract_name_tag(volume["tags"]),
                    }
                )

        return low_activity

    def _get_volume_io_stats(self, volume_id: str, days: int) -> Dict:
        """Get I/O statistics for a volume"""
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(days=days)

        try:
            # Get read operations
            read_response = self.cloudwatch.get_metric_statistics(
                Namespace="AWS/EBS",
                MetricName="VolumeReadOps",
                Dimensions=[{"Name": "VolumeId", "Value": volume_id}],
                StartTime=start_time,
                EndTime=end_time,
                Period=86400,  # Daily
                Statistics=["Sum"],
            )

            # Get write operations
            write_response = self.cloudwatch.get_metric_statistics(
                Namespace="AWS/EBS",
                MetricName="VolumeWriteOps",
                Dimensions=[{"Name": "VolumeId", "Value": volume_id}],
                StartTime=start_time,
                EndTime=end_time,
                Period=86400,  # Daily
                Statistics=["Sum"],
            )

            total_reads = sum(dp["Sum"] for dp in read_response.get("Datapoints", []))
            total_writes = sum(dp["Sum"] for dp in write_response.get("Datapoints", []))

            return {
                "total_read_ops": int(total_reads),
                "total_write_ops": int(total_writes),
                "avg_read_ops_per_day": int(total_reads / days) if days > 0 else 0,
                "avg_write_ops_per_day": int(total_writes / days) if days > 0 else 0,
            }

        except Exception as e:
            print(f"  Warning: Could not fetch I/O stats for {volume_id}: {e}")
            return {
                "total_read_ops": 0,
                "total_write_ops": 0,
                "avg_read_ops_per_day": 0,
                "avg_write_ops_per_day": 0,
            }

    def find_old_snapshots(self, age_threshold_days: int = 180) -> List[Dict]:
        """Find snapshots older than threshold."""
        print(f"Fetching snapshots (this may take a while)...")

        # Only get snapshots owned by this account
        snapshots = self.ec2.describe_snapshots(OwnerIds=["self"])["Snapshots"]

        print(f"Found {len(snapshots)} snapshots, analyzing age...\n")

        old_snapshots = []
        total_old_size = 0

        for snapshot in snapshots:
            age_days = (
                datetime.now(snapshot["StartTime"].tzinfo) - snapshot["StartTime"]
            ).days

            if age_days > age_threshold_days:
                size_gb = snapshot["VolumeSize"]
                monthly_cost = size_gb * self.snapshot_pricing

                # Determine if snapshot is part of an AMI (don't delete those!)
                description = snapshot.get("Description", "").lower()
                is_ami_snapshot = (
                    "ami" in description or "created by createimage" in description
                )

                old_snapshots.append(
                    {
                        "snapshot_id": snapshot["SnapshotId"],
                        "volume_id": snapshot.get("VolumeId", "N/A"),
                        "size_gb": size_gb,
                        "created_date": snapshot["StartTime"].strftime("%Y-%m-%d"),
                        "age_days": age_days,
                        "monthly_cost": round(monthly_cost, 2),
                        "annual_cost": round(monthly_cost * 12, 2),
                        "description": snapshot.get("Description", "No description"),
                        "is_ami_snapshot": is_ami_snapshot,
                        "severity": "low" if is_ami_snapshot else "medium",
                        "recommendation": self._get_snapshot_recommendation(
                            age_days, is_ami_snapshot
                        ),
                        "tags": snapshot.get("Tags", []),
                    }
                )

                total_old_size += size_gb

        return old_snapshots

    def find_volume_type_optimizations(self) -> List[Dict]:
        """Find volumes using expensive types that could be cheaper."""
        all_volumes = self.get_all_volumes()
        optimizations = []

        for volume in all_volumes:
            current_type = volume["type"]
            size_gb = volume["size"]
            current_cost = self._calculate_volume_cost(size_gb, current_type)

            # Check for gp2 -> gp3 migration (easy win)
            if current_type == "gp2":
                new_type = "gp3"
                new_cost = self._calculate_volume_cost(size_gb, new_type)
                savings = current_cost - new_cost

                optimizations.append(
                    {
                        "volume_id": volume["id"],
                        "current_type": current_type,
                        "recommended_type": new_type,
                        "size_gb": size_gb,
                        "current_monthly_cost": current_cost,
                        "new_monthly_cost": new_cost,
                        "monthly_savings": round(savings, 2),
                        "annual_savings": round(savings * 12, 2),
                        "reason": "gp3 is newer, faster, and cheaper than gp2",
                        "risk": "Low - gp3 performs better than gp2",
                        "severity": "medium",
                    }
                )

            # Check for io2 on low-IOPS volumes
            elif current_type in ["io1", "io2"]:
                provisioned_iops = volume.get("iops", 0)

                if provisioned_iops < 10000:
                    new_type = "gp3"
                    new_cost = self._calculate_volume_cost(size_gb, new_type)
                    savings = current_cost - new_cost

                    optimizations.append(
                        {
                            "volume_id": volume["id"],
                            "current_type": current_type,
                            "recommended_type": new_type,
                            "size_gb": size_gb,
                            "current_monthly_cost": current_cost,
                            "new_monthly_cost": new_cost,
                            "monthly_savings": round(savings, 2),
                            "annual_savings": round(savings * 12, 2),
                            "reason": f"Low IOPS ({provisioned_iops}). gp3 can handle this workload.",
                            "risk": "Medium - Verify performance requirements",
                            "severity": "high",
                        }
                    )

        return optimizations

    def analyze_snapshot_lifecycle(self) -> Dict:
        """Analyze snapshot retention patterns."""
        snapshots = self.ec2.describe_snapshots(OwnerIds=["self"])["Snapshots"]

        # Group snapshots by volume
        by_volume = defaultdict(list)

        for snapshot in snapshots:
            volume_id = snapshot.get("VolumeId", "unknown")
            by_volume[volume_id].append(snapshot)

        # Analyze each volume's snapshots
        analysis = {
            "total_snapshots": len(snapshots),
            "total_size_gb": sum(s["VolumeSize"] for s in snapshots),
            "total_monthly_cost": sum(
                s["VolumeSize"] * self.snapshot_pricing for s in snapshots
            ),
            "volumes_with_snapshots": len(by_volume),
            "avg_snapshots_per_volume": len(snapshots) / len(by_volume)
            if by_volume
            else 0,
            "age_distribution": self._calculate_age_distribution(snapshots),
            "recommendations": [],
        }

        # Find volumes with excessive snapshots
        for volume_id, vol_snapshots in by_volume.items():
            if len(vol_snapshots) > 30:
                analysis["recommendations"].append(
                    {
                        "volume_id": volume_id,
                        "snapshot_count": len(vol_snapshots),
                        "recommendation": f"Volume has {len(vol_snapshots)} snapshots. Implement lifecycle policy.",
                        "severity": "medium",
                    }
                )

        return analysis

    def _calculate_age_distribution(self, snapshots: List[Dict]) -> Dict:
        """Calculate how many snapshots fall into age buckets"""
        buckets = {
            "0-30 days": 0,
            "31-90 days": 0,
            "91-180 days": 0,
            "181-365 days": 0,
            "1-2 years": 0,
            "2+ years": 0,
        }

        for snapshot in snapshots:
            age_days = (
                datetime.now(snapshot["StartTime"].tzinfo) - snapshot["StartTime"]
            ).days

            if age_days <= 30:
                buckets["0-30 days"] += 1
            elif age_days <= 90:
                buckets["31-90 days"] += 1
            elif age_days <= 180:
                buckets["91-180 days"] += 1
            elif age_days <= 365:
                buckets["181-365 days"] += 1
            elif age_days <= 730:
                buckets["1-2 years"] += 1
            else:
                buckets["2+ years"] += 1

        return buckets

    def _calculate_volume_cost(self, size_gb: int, volume_type: str) -> float:
        """Calculate monthly cost for a volume"""
        price_per_gb = self.volume_pricing.get(volume_type, 0.10)
        return round(size_gb * price_per_gb, 2)

    def _get_unattached_recommendation(self, age_days: int) -> str:
        if age_days > 90:
            return (
                f"CRITICAL: Unattached for {age_days} days. "
                "Create snapshot for safety, then delete volume."
            )
        elif age_days > 30:
            return (
                f"HIGH: Unattached for {age_days} days. Verify not needed, then delete."
            )
        elif age_days > 7:
            return (
                f"MEDIUM: Unattached for {age_days} days. "
                "Monitor for another week, then consider deletion."
            )
        else:
            return f"LOW: Recently unattached ({age_days} days). Continue monitoring."

    def _get_snapshot_recommendation(self, age_days: int, is_ami: bool) -> str:
        if is_ami:
            return (
                f"Part of an AMI. Age: {age_days} days. "
                "Verify AMI is still needed before deleting."
            )
        else:
            return (
                f"Standalone snapshot, {age_days} days old. "
                "If not required for compliance/recovery, consider deleting."
            )

    def _extract_name_tag(self, tags: List[Dict]) -> str:
        for tag in tags:
            if tag["Key"] == "Name":
                return tag["Value"]
        return "Unnamed"

    def scan(self) -> Dict:
        """Main scanning method."""
        print("=" * 70)
        print(f"STARTING EBS COST OPTIMIZATION SCAN ({self.region})")
        print("=" * 70)
        print()

        # 1. Find unattached volumes
        print("1. Scanning for unattached volumes...")
        unattached = self.find_unattached_volumes()
        unattached_cost = sum(v["monthly_cost"] for v in unattached)
        print(f"   Found {len(unattached)} unattached volumes")
        print(f"   Monthly waste: ${unattached_cost:,.2f}\n")

        # 2. Find old snapshots
        print("2. Scanning for old snapshots (>180 days)...")
        old_snapshots = self.find_old_snapshots(age_threshold_days=180)
        snapshot_cost = sum(s["monthly_cost"] for s in old_snapshots)
        print(f"   Found {len(old_snapshots)} old snapshots")
        print(f"   Monthly cost: ${snapshot_cost:,.2f}\n")

        # 3. Find volume type optimizations
        print("3. Analyzing volume type optimizations...")
        optimizations = self.find_volume_type_optimizations()
        optimization_savings = sum(o["monthly_savings"] for o in optimizations)
        print(f"   Found {len(optimizations)} optimization opportunities")
        print(f"   Potential monthly savings: ${optimization_savings:,.2f}\n")

        # 4. Find low-activity volumes
        print("4. Checking for low-activity volumes...")
        low_activity = self.find_low_activity_volumes(days=7)
        low_activity_cost = sum(v["monthly_cost"] for v in low_activity)
        print(f"   Found {len(low_activity)} volumes with no I/O")
        print(f"   Monthly cost (if unused): ${low_activity_cost:,.2f}\n")

        # 5. Snapshot lifecycle analysis
        print("5. Analyzing snapshot lifecycle...")
        snapshot_analysis = self.analyze_snapshot_lifecycle()
        print(f"   Total snapshots: {snapshot_analysis['total_snapshots']}")
        print(
            f"   Total snapshot cost: ${snapshot_analysis['total_monthly_cost']:,.2f}/month\n"
        )

        # Calculate totals
        total_monthly_savings = (
            unattached_cost
            + optimization_savings
            + snapshot_cost * 0.5  # Assume we can delete 50% of old snapshots
        )

        total_annual_savings = total_monthly_savings * 12

        print("=" * 70)
        print("EBS SCAN COMPLETE")
        print("=" * 70)
        print(f"Total potential monthly savings: ${total_monthly_savings:,.2f}")
        print(f"Total potential annual savings: ${total_annual_savings:,.2f}")
        print("=" * 70)

        return {
            "status": "success",
            "scan_date": datetime.utcnow().isoformat(),
            "region": self.region,
            "findings": {
                "unattached_volumes": {
                    "count": len(unattached),
                    "items": unattached,
                    "total_monthly_cost": round(unattached_cost, 2),
                },
                "old_snapshots": {
                    "count": len(old_snapshots),
                    "items": old_snapshots,
                    "total_monthly_cost": round(snapshot_cost, 2),
                },
                "volume_optimizations": {
                    "count": len(optimizations),
                    "items": optimizations,
                    "potential_monthly_savings": round(optimization_savings, 2),
                },
                "low_activity_volumes": {
                    "count": len(low_activity),
                    "items": low_activity,
                    "potential_monthly_cost": round(low_activity_cost, 2),
                },
            },
            "snapshot_analysis": snapshot_analysis,
            "summary": {
                "total_findings": len(unattached)
                + len(old_snapshots)
                + len(optimizations),
                "critical_severity": sum(
                    1 for v in unattached if v["severity"] == "critical"
                ),
                "high_severity": sum(1 for v in unattached if v["severity"] == "high"),
                "medium_severity": (
                    sum(1 for v in unattached if v["severity"] == "medium")
                    + len(optimizations)
                ),
            },
            "potential_savings": {
                "monthly": round(total_monthly_savings, 2),
                "annual": round(total_annual_savings, 2),
            },
        }


# ============================================================================
# USAGE EXAMPLE
# ============================================================================
if __name__ == "__main__":
    """
    Test the EBS scanner locally.

    Run with: python -m backend.scanner.ebs_scanner
    """
    import json

    # Industry preferred: Use env vars or default profile to avoid 'ProfileNotFound'
    profile = os.getenv("AWS_PROFILE", "default")

    # Initialize scanner
    scanner = EBSScanner(region="eu-west-2", profile_name=profile)

    # Run scan
    results = scanner.scan()

    # Save to file
    with open("ebs_scan_results.json", "w") as f:
        json.dump(results, f, indent=2)

    print("\n\nResults saved to ebs_scan_results.json")

    # Print detailed findings
    print("\n" + "=" * 70)
    print("DETAILED FINDINGS")
    print("=" * 70)

    # Top unattached volumes
    if results["findings"]["unattached_volumes"]["items"]:
        print("\nTOP 5 UNATTACHED VOLUMES (BY COST):")
        print("-" * 70)
        unattached = sorted(
            results["findings"]["unattached_volumes"]["items"],
            key=lambda x: x["monthly_cost"],
            reverse=True,
        )[:5]

        for vol in unattached:
            print(f"\n• {vol['name']} ({vol['volume_id']})")
            print(f"  Size: {vol['size_gb']} GB ({vol['type']})")
            print(f"  Age: {vol['age_days']} days")
            print(f"  Cost: ${vol['monthly_cost']}/month (${vol['annual_cost']}/year)")
            print(f"  Severity: {vol['severity'].upper()}")
            print(f"  Action: {vol['recommendation']}")

    # Volume type optimizations
    if results["findings"]["volume_optimizations"]["items"]:
        print("\n\nVOLUME TYPE OPTIMIZATIONS:")
        print("-" * 70)
        for opt in results["findings"]["volume_optimizations"]["items"]:
            print(f"\n• Volume: {opt['volume_id']}")
            print(
                f"  Current: {opt['current_type']} -> Recommended: {opt['recommended_type']}"
            )
            print(f"  Size: {opt['size_gb']} GB")
            print(
                f"  Savings: ${opt['monthly_savings']}/month (${opt['annual_savings']}/year)"
            )
            print(f"  Reason: {opt['reason']}")
            print(f"  Risk: {opt['risk']}")

    # Snapshot statistics
    print("\n\nSNAPSHOT AGE DISTRIBUTION:")
    print("-" * 70)
    age_dist = results["snapshot_analysis"]["age_distribution"]
    for age_range, count in age_dist.items():
        print(f"  {age_range:20s}: {count:4d} snapshots")

    print(
        f"\n  Total snapshot cost: ${results['snapshot_analysis']['total_monthly_cost']:,.2f}/month"
    )

    print("\n" + "=" * 70)
    print(
        f"TOTAL POTENTIAL SAVINGS: ${results['potential_savings']['monthly']:,.2f}/month"
    )
    print(f"ANNUAL IMPACT: ${results['potential_savings']['annual']:,.2f}/year")
    print("=" * 70)
