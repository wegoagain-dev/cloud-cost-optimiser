# assigning this to public subnets, avoiding the need for nat gateway but we are relying on security groups to keep us safe

# 1. ECS Cluster
resource "aws_ecs_cluster" "main" {
  name = "cco-cluster"
}

# 2. Security Group for Tasks (Allow traffic only from ALB)
resource "aws_security_group" "ecs_tasks_sg" {
  name        = "cco-ecs-tasks-sg"
  description = "Allow inbound from ALB only"
  vpc_id      = aws_vpc.main.id

  ingress {
    from_port       = 0
    to_port         = 0
    protocol        = "-1"
    security_groups = [aws_security_group.alb_sg.id] # Only ALB can talk to tasks
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"] # Needed to pull Docker images & talk to AWS API
  }
}

# 3. Log Group (So you can see print() statements)
resource "aws_cloudwatch_log_group" "cco_logs" {
  name              = "/ecs/cloud-cost-optimiser"
  retention_in_days = 7
}

# 4. Backend Task Definition
resource "aws_ecs_task_definition" "backend" {
  family                   = "cco-backend"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = "256" # 0.25 vCPU (Free Tier friendly)
  memory                   = "512" # 0.5 GB

  execution_role_arn = aws_iam_role.execution_role.arn
  task_role_arn      = aws_iam_role.task_role.arn

  container_definitions = jsonencode([
    {
      name      = "backend"
      image     = "${aws_ecr_repository.backend.repository_url}:latest"
      essential = true
      portMappings = [{
        containerPort = 8000
        hostPort      = 8000
      }]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.cco_logs.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "backend"
        }
      }
      environment = [
        # We will add DB credentials here
        { name = "DEMO_MODE", value = "false" },
        # The Connection String
        {
          name  = "DATABASE_URL",
          value = "postgresql://postgres:${random_password.db_password.result}@${aws_db_instance.main.endpoint}/cost_optimiser"
        }
      ]
    }
  ])
}

# 5. Frontend Task Definition
resource "aws_ecs_task_definition" "frontend" {
  family                   = "cco-frontend"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = "256"
  memory                   = "512"

  execution_role_arn = aws_iam_role.execution_role.arn

  container_definitions = jsonencode([
    {
      name      = "frontend"
      image     = "${aws_ecr_repository.frontend.repository_url}:latest"
      essential = true
      portMappings = [{
        containerPort = 80
        hostPort      = 80
      }]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.cco_logs.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "frontend"
        }
      }
    }
  ])
}

# 6. Backend Service
resource "aws_ecs_service" "backend" {
  name            = "cco-backend-service"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.backend.arn
  desired_count   = 1
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = [aws_subnet.public_a.id, aws_subnet.public_b.id]
    security_groups  = [aws_security_group.ecs_tasks_sg.id]
    assign_public_ip = true # Required for pulling images in public subnet
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.backend.arn
    container_name   = "backend"
    container_port   = 8000
  }
}

# 7. Frontend Service
resource "aws_ecs_service" "frontend" {
  name            = "cco-frontend-service"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.frontend.arn
  desired_count   = 1
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = [aws_subnet.public_a.id, aws_subnet.public_b.id]
    security_groups  = [aws_security_group.ecs_tasks_sg.id]
    assign_public_ip = true
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.frontend.arn
    container_name   = "frontend"
    container_port   = 80
  }
}
