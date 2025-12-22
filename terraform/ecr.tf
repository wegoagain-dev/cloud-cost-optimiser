# 1. Repository for the Backend (Python API)
resource "aws_ecr_repository" "backend" {
  name                 = "cloud-cost-optimiser-backend"
  image_tag_mutability = "MUTABLE" # Allows overwriting 'latest' tag
  force_delete         = true      # Allows destroying repo even if it has images

  image_scanning_configuration {
    scan_on_push = true # Free security scan for vulnerabilities
  }
}

# 2. Repository for the Frontend (React/Nginx)
resource "aws_ecr_repository" "frontend" {
  name                 = "cloud-cost-optimiser-frontend"
  image_tag_mutability = "MUTABLE"
  force_delete         = true

  image_scanning_configuration {
    scan_on_push = true
  }
}
