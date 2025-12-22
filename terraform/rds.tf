# 1. Random Password (Secure)
resource "random_password" "db_password" {
  length  = 16
  special = false
}

# 2. Store Password in Secrets Manager (Best Practice)
resource "aws_secretsmanager_secret" "db_password" {
  name = "cco-db-password"
}

resource "aws_secretsmanager_secret_version" "db_password_val" {
  secret_id     = aws_secretsmanager_secret.db_password.id
  secret_string = random_password.db_password.result
}

# 3. Security Group for Database
resource "aws_security_group" "rds_sg" {
  name        = "cco-rds-sg"
  description = "Allow inbound from ECS Tasks"
  vpc_id      = aws_vpc.main.id

  ingress {
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.ecs_tasks_sg.id] # Only ECS can talk to DB
  }
}

# 4. The Database Instance
resource "aws_db_instance" "main" {
  identifier        = "cco-db"
  engine            = "postgres"
  engine_version    = "14"
  instance_class    = "db.t3.micro" # Free Tier Eligible
  allocated_storage = 20

  db_name  = "cost_optimiser"
  username = "postgres"
  password = random_password.db_password.result

  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [aws_security_group.rds_sg.id]

  skip_final_snapshot = true  # Don't backup when destroying (for learning)
  publicly_accessible = false # Secure: Not on the internet
}

# 5. DB Subnet Group (Where to put the DB)
resource "aws_db_subnet_group" "main" {
  name       = "cco-db-subnet-group"
  subnet_ids = [aws_subnet.public_a.id, aws_subnet.public_b.id]

  tags = { Name = "cco-db-subnet-group" }
}
