"""
EC2 Cost Scanner
Identifies underutilized EC2 instances and calculates potential savings.

Learning Objectives:
1. AWS API pagination handling
2. CloudWatch metrics analysis
3. Cost calculation logic
4. Business rule implementation
"""

import os
import statistics
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import boto3


# Learning: Using dataclass for clean data structures
@dataclass
class EC2Instance:
    """Represents an EC2 instance with cost data"""

    id: str
    name: str
    type: str
    state: str
    launch_time: datetime
    region: str
    avg_cpu: float
    max_cpu: float
    monthly_cost: float


class EC2Scanner:
    """
    Scans EC2 instances for cost optimization opportunities.
    """

    def __init__(self, region: str = "eu-west-1", profile_name: str = None):
        """
        Initialize AWS clients.

        Learning: boto3 Session allows using different AWS profiles.
        Useful for scanning multiple AWS accounts.
        """
        session = boto3.Session(profile_name=profile_name, region_name=region)

        self.ec2 = session.client("ec2")
        self.cloudwatch = session.client("cloudwatch")
        self.ce = session.client("ce")  # Cost Explorer
        self.region = region

        # Pricing data (simplified - in production, use AWS Price List API)
        self.pricing = self._load_pricing()

    def _load_pricing(self) -> Dict[str, float]:
        """
        Load EC2 pricing data.

        Learning: Real production code would call AWS Price List API.
        For learning, we'll use hardcoded values for common types.

        Pricing is per hour, Linux, On-Demand,
        Source: https://aws.amazon.com/ec2/pricing/on-demand/
        """
        return {
            # T3 family (burstable)
            "t3.nano": 0.0059,
            "t3.micro": 0.0118,
            "t3.small": 0.0236,
            "t3.medium": 0.0472,
            "t3.large": 0.0944,
            "t3.xlarge": 0.1888,
            "t3.2xlarge": 0.3776,
            # T2 family (older burstable)
            "t2.micro": 0.0132,
            "t2.small": 0.0264,
            "t2.medium": 0.0528,
            "t2.large": 0.1056,
            # M5 family (general purpose)
            "m5.large": 0.111,
            "m5.xlarge": 0.222,
            "m5.2xlarge": 0.444,
            "m5.4xlarge": 0.888,
            # C5 family (compute optimized)
            "c5.large": 0.101,
            "c5.xlarge": 0.202,
            "c5.2xlarge": 0.404,
            # R5 family (memory optimized)
            "r5.large": 0.148,
            "r5.xlarge": 0.296,
            "r5.2xlarge": 0.592,
        }

    def get_all_instances(self) -> List[Dict]:
        """
        Retrieve all EC2 instances from the AWS account.

        Learning Point: AWS API Pagination
        ===================================
        AWS APIs return max 1000 items per request.
        Use paginators to get ALL resources.
        """
        instances = []

        # Create paginator (handles pagination automatically)
        paginator = self.ec2.get_paginator("describe_instances")

        print("Fetching EC2 instances...")

        # Iterate through pages
        for page_num, page in enumerate(paginator.paginate(), 1):
            print(f"  Processing page {page_num}...")

            for reservation in page["Reservations"]:
                for instance in reservation["Instances"]:
                    # Only analyze running instances
                    # (Stopped instances already save money!)
                    if instance["State"]["Name"] == "running":
                        instances.append(
                            {
                                "id": instance["InstanceId"],
                                "type": instance["InstanceType"],
                                "launch_time": instance["LaunchTime"],
                                "state": instance["State"]["Name"],
                                "name": self._extract_name_tag(instance),
                                "tags": instance.get("Tags", []),
                            }
                        )

        print(f"Found {len(instances)} running instances\n")
        return instances

    def _extract_name_tag(self, instance: Dict) -> str:
        """
        Extract the 'Name' tag from an instance.

        Learning: AWS tags are key-value pairs for organizing resources.
        Name tag is conventional but not required.
        """
        tags = instance.get("Tags", [])
        for tag in tags:
            if tag["Key"] == "Name":
                return tag["Value"]
        return f"Unnamed-{instance['InstanceId']}"

    def get_cpu_metrics(self, instance_id: str, days: int = 7) -> Dict:
        """
        Retrieve CPU utilization metrics from CloudWatch.

        Learning Point: CloudWatch Metrics
        ==================================
        CloudWatch stores metrics as time-series data:
        - Namespace: Service category (AWS/EC2, AWS/RDS, etc.)
        - MetricName: Specific metric (CPUUtilization, NetworkIn, etc.)
        - Dimensions: Identify specific resource (InstanceId)
        - Period: Aggregation interval (60s, 300s, 3600s)
        - Statistics: How to aggregate (Average, Maximum, Sum)

        "Analyze CloudWatch CPUUtilization metric over 7-14 days.
                 If average < 5% and max < 20%, it's likely idle."
        """
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(days=days)

        try:
            response = self.cloudwatch.get_metric_statistics(
                Namespace="AWS/EC2",
                MetricName="CPUUtilization",
                Dimensions=[{"Name": "InstanceId", "Value": instance_id}],
                StartTime=start_time,
                EndTime=end_time,
                Period=3600,  # 1 hour intervals
                Statistics=["Average", "Maximum"],
            )

            # Handle case where no data is available
            if not response["Datapoints"]:
                return {"avg": 0, "max": 0, "datapoints": 0, "status": "no_data"}

            datapoints = response["Datapoints"]
            averages = [dp["Average"] for dp in datapoints]
            maximums = [dp["Maximum"] for dp in datapoints]

            return {
                "avg": round(statistics.mean(averages), 2),
                "max": round(max(maximums), 2),
                "min": round(min(averages), 2),
                "datapoints": len(datapoints),
                "status": "ok",
            }

        except Exception as e:
            print(f"Error fetching metrics for {instance_id}: {e}")
            return {"avg": 0, "max": 0, "datapoints": 0, "status": "error"}

    def calculate_monthly_cost(self, instance_type: str) -> float:
        """
        Calculate monthly cost for an instance type.

        Learning: Cost Calculation Logic
        ================================
        - Hourly rate × 730 hours/month (365 days ÷ 12 months × 24 hours)
        - This is On-Demand pricing (highest cost)
        - Reserved Instances and Savings Plans would be cheaper
        """
        hourly_rate = self.pricing.get(instance_type, 0.10)  # Default fallback
        monthly_hours = 730  # Average hours per month
        return round(hourly_rate * monthly_hours, 2)

    def calculate_savings_scenarios(self, instance_type: str, avg_cpu: float) -> Dict:
        """
        Calculate potential savings from different actions.

        Learning: Business Logic
        ========================
        Three main cost reduction strategies:

        1. Schedule (Stop during off-hours)
           - Business hours: 8am-6pm, Mon-Fri = ~50 hours/week
           - 24/7 operation: 168 hours/week
           - Savings: ~70% by stopping nights/weekends

        2. Downsize (Move to smaller instance)
           - If avg CPU < 10%, likely oversized
           - Drop one size (e.g., t3.large → t3.medium)
           - Savings: ~50%

        3. Terminate (Delete if truly unused)
           - If avg CPU < 2%, might be abandoned
           - Savings: 100%

        "How would I automate EC2 scheduling?"
        "Lambda function + EventBridge rules to stop/start
        instances on schedule. Tag instances with 'Schedule: BusinessHours'"
        """
        current_cost = self.calculate_monthly_cost(instance_type)

        # Scenario 1: Schedule (business hours only)
        business_hours_monthly = 50 * 4.33 * self.pricing.get(instance_type, 0.10)
        schedule_savings = current_cost - business_hours_monthly

        # Scenario 2: Downsize (move to smaller instance)
        smaller_type = self._get_smaller_instance_type(instance_type)
        if smaller_type:
            smaller_cost = self.calculate_monthly_cost(smaller_type)
            downsize_savings = current_cost - smaller_cost
        else:
            downsize_savings = 0
            smaller_type = instance_type

        # Scenario 3: Terminate
        terminate_savings = current_cost

        return {
            "current_monthly_cost": current_cost,
            "scenarios": {
                "schedule": {
                    "monthly_savings": round(schedule_savings, 2),
                    "annual_savings": round(schedule_savings * 12, 2),
                    "description": "Stop during nights/weekends (business hours only)",
                },
                "downsize": {
                    "monthly_savings": round(downsize_savings, 2),
                    "annual_savings": round(downsize_savings * 12, 2),
                    "new_type": smaller_type,
                    "description": f"Downsize to {smaller_type}",
                },
                "terminate": {
                    "monthly_savings": round(terminate_savings, 2),
                    "annual_savings": round(terminate_savings * 12, 2),
                    "description": "Terminate if no longer needed",
                },
            },
        }

    def _get_smaller_instance_type(self, instance_type: str) -> Optional[str]:
        """
        Get the next smaller instance in the same family.

        Learning: EC2 Instance Families
        ===============================
        Format: <family><generation>.<size>
        Example: t3.large
        - Family: t (burstable)
        - Generation: 3
        - Size: large

        Sizes (smallest to largest):
        nano < micro < small < medium < large < xlarge < 2xlarge < 4xlarge...
        """
        size_order = [
            "nano",
            "micro",
            "small",
            "medium",
            "large",
            "xlarge",
            "2xlarge",
            "4xlarge",
            "8xlarge",
        ]

        parts = instance_type.split(".")
        if len(parts) != 2:
            return None

        family, size = parts

        try:
            current_index = size_order.index(size)
            if current_index > 0:
                new_size = size_order[current_index - 1]
                return f"{family}.{new_size}"
        except ValueError:
            pass

        return None

    def generate_recommendation(self, instance: Dict, cpu_metrics: Dict) -> Dict:
        """
        Generate actionable recommendation based on metrics.

        Learning: Decision Logic
        ========================
        Severity levels based on waste amount:
        - Critical: >$100/month potential savings
        - High: $50-$100/month
        - Medium: $20-$50/month
        - Low: <$20/month
        """
        avg_cpu = cpu_metrics["avg"]
        max_cpu = cpu_metrics["max"]

        savings = self.calculate_savings_scenarios(instance["type"], avg_cpu)

        # Determine severity and primary recommendation
        if avg_cpu < 2:
            severity = "critical"
            recommended_action = "terminate"
            reason = f"Extremely low CPU usage ({avg_cpu}%). Likely abandoned."
        elif avg_cpu < 5:
            severity = "high"
            recommended_action = "schedule"
            reason = (
                f"Very low CPU usage ({avg_cpu}%). Consider scheduling or downsizing."
            )
        elif avg_cpu < 10:
            severity = "medium"
            recommended_action = "downsize"
            reason = f"Low CPU usage ({avg_cpu}%). Likely oversized."
        elif avg_cpu < 20:
            severity = "low"
            recommended_action = "schedule"
            reason = f"Moderate CPU usage ({avg_cpu}%). Could benefit from scheduling."
        else:
            severity = "info"
            recommended_action = "none"
            reason = f"CPU usage acceptable ({avg_cpu}%)."

        return {
            "instance_id": instance["id"],
            "instance_name": instance["name"],
            "instance_type": instance["type"],
            "region": self.region,
            "metrics": {
                "avg_cpu": avg_cpu,
                "max_cpu": max_cpu,
                "min_cpu": cpu_metrics.get("min", 0),
                "datapoints": cpu_metrics["datapoints"],
            },
            "costs": savings,
            "recommendation": {
                "severity": severity,
                "action": recommended_action,
                "reason": reason,
                "primary_savings": savings["scenarios"][recommended_action][
                    "monthly_savings"
                ],
                "annual_impact": savings["scenarios"][recommended_action][
                    "annual_savings"
                ],
            },
            "all_scenarios": savings["scenarios"],
        }

    def scan(self) -> Dict:
        """
        Main scanning method - orchestrates the entire analysis.

        Learning: This is the public interface to the scanner.
        Clean API design: caller doesn't need to know implementation details.
        """
        print("=" * 70)
        print("STARTING EC2 COST OPTIMIZATION SCAN")
        print("=" * 70)

        # Step 1: Get all instances
        instances = self.get_all_instances()

        if not instances:
            return {
                "status": "success",
                "instances_scanned": 0,
                "recommendations": [],
                "total_potential_savings": 0,
            }

        # Step 2: Analyze each instance
        recommendations = []

        for i, instance in enumerate(instances, 1):
            print(
                f"[{i}/{len(instances)}] Analyzing {instance['name']} ({instance['id']})..."
            )

            # Get CloudWatch metrics
            cpu_metrics = self.get_cpu_metrics(instance["id"])

            # Generate recommendation
            recommendation = self.generate_recommendation(instance, cpu_metrics)
            recommendations.append(recommendation)

            print(f"  CPU: {cpu_metrics['avg']}% avg, {cpu_metrics['max']}% max")
            print(f"  Severity: {recommendation['recommendation']['severity'].upper()}")
            print(
                f"  Potential savings: ${recommendation['recommendation']['primary_savings']}/month\n"
            )

        # Step 3: Calculate totals
        total_monthly_savings = sum(
            r["recommendation"]["primary_savings"]
            for r in recommendations
            if r["recommendation"]["severity"] in ["critical", "high", "medium"]
        )

        total_annual_savings = total_monthly_savings * 12

        # Step 4: Sort by potential savings (highest first)
        recommendations.sort(
            key=lambda x: x["recommendation"]["primary_savings"], reverse=True
        )

        print("=" * 70)
        print("SCAN COMPLETE")
        print("=" * 70)
        print(f"Instances scanned: {len(instances)}")
        print(f"Recommendations generated: {len(recommendations)}")
        print(f"Total potential monthly savings: ${total_monthly_savings:,.2f}")
        print(f"Total potential annual savings: ${total_annual_savings:,.2f}")
        print("=" * 70)

        return {
            "status": "success",
            "scan_date": datetime.utcnow().isoformat(),
            "region": self.region,
            "instances_scanned": len(instances),
            "recommendations": recommendations,
            "summary": {
                "critical": sum(
                    1
                    for r in recommendations
                    if r["recommendation"]["severity"] == "critical"
                ),
                "high": sum(
                    1
                    for r in recommendations
                    if r["recommendation"]["severity"] == "high"
                ),
                "medium": sum(
                    1
                    for r in recommendations
                    if r["recommendation"]["severity"] == "medium"
                ),
                "low": sum(
                    1
                    for r in recommendations
                    if r["recommendation"]["severity"] == "low"
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
    Test the scanner locally before integrating with API.

    Run with: python -m backend.scanner.ec2_scanner
    """
    import json

    # Industry preferred: Use env vars or default profile to avoid 'ProfileNotFound'
    profile = os.getenv("AWS_PROFILE", "default")

    # Initialize scanner
    scanner = EC2Scanner(region="eu-west-2", profile_name=profile)

    # Run scan
    results = scanner.scan()

    # Save results to JSON file
    with open("ec2_scan_results.json", "w") as f:
        json.dump(results, f, indent=2)

    print("\nResults saved to ec2_scan_results.json")

    # Print top 5 recommendations
    print("\n" + "=" * 70)
    print("TOP 5 COST SAVINGS OPPORTUNITIES")
    print("=" * 70)

    for i, rec in enumerate(results["recommendations"][:5], 1):
        print(f"\n{i}. {rec['instance_name']} ({rec['instance_type']})")
        print(f"   Instance ID: {rec['instance_id']}")
        print(f"   CPU Usage: {rec['metrics']['avg_cpu']}% avg")
        print(f"   Current Cost: ${rec['costs']['current_monthly_cost']}/month")
        print(f"   Recommendation: {rec['recommendation']['action'].upper()}")
        print(
            f"   Potential Savings: ${rec['recommendation']['primary_savings']}/month"
        )
        print(f"   Annual Impact: ${rec['recommendation']['annual_impact']}/year")
        print(f"   Reason: {rec['recommendation']['reason']}")
