variable "aws_region" {
  description = "AWS Region to deploy resources"
  default     = "eu-west-2" # London
}

variable "my_ip" {
  description = "Home IP Address (CIDR format) for security whitelist"
  type        = string
  sensitive   = true
  # Example usage in CLI: -var="my_ip=82.12.34.56/32"
}
