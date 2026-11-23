terraform {
  required_version = ">= 1.6.0, < 2.0.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}

# Die Region kommt aus variables.tf; Zugangsdaten bleiben ausserhalb von Git.
# Bei spaeteren AWS-Abfragen das Profil mit AWS_PROFILE=tictactest-lab waehlen.
provider "aws" {
  region = var.aws_region
}

# data liest vorhandene AWS-Objekte; diese Netzressourcen gehoeren nicht uns.
data "aws_vpc" "default" {
  default = true
}

data "aws_subnet" "selected" {
  vpc_id            = data.aws_vpc.default.id
  availability_zone = var.availability_zone
  default_for_az    = true
}

# Eine feste AMI pruefen, statt bei jedem Plan unbemerkt ein neues Image zu waehlen.
data "aws_ami" "server" {
  owners = ["amazon"]

  filter {
    name   = "image-id"
    values = [var.ami_id]
  }

  filter {
    name   = "architecture"
    values = ["x86_64"]
  }
}

# Nur der Public Key geht zu AWS. Der private Schluessel wird nicht von IaC gelesen.
resource "aws_key_pair" "ssh" {
  key_name   = "${var.instance_name}-ssh"
  public_key = file(pathexpand(var.ssh_public_key_path))
}

resource "aws_security_group" "ssh" {
  name        = "${var.instance_name}-ssh"
  description = "SSH access from the approved administration host only"
  vpc_id      = data.aws_vpc.default.id

  ingress {
    description = "SSH from the administration host"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = [var.ssh_allowed_cidr]
  }

  # Oeffentliches HTTP nur zum Frontend/Proxy; ttyd bleibt intern.
  ingress {
    description = "Public HTTP for the TicTacTest frontend and console proxy"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  # Ausgehende Verbindungen fuer Betriebssystem-Updates erlauben.
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name    = "${var.instance_name}-ssh"
    Project = "TicTacTest"
  }
}

resource "aws_instance" "server" {
  ami                         = data.aws_ami.server.id
  instance_type               = var.instance_type
  subnet_id                   = data.aws_subnet.selected.id
  vpc_security_group_ids      = [aws_security_group.ssh.id]
  key_name                    = aws_key_pair.ssh.key_name
  associate_public_ip_address = true
  iam_instance_profile        = data.aws_iam_instance_profile.lab.name

  # User-data changes use stop/start, but cloud-init runs this only on first boot.
  user_data                   = local.bootstrap_user_data
  user_data_replace_on_change = false

  # Kleine, verschluesselte Systemdisk; beim Loeschen der Instanz mit entfernen.
  root_block_device {
    volume_size           = 8
    volume_type           = "gp3"
    encrypted             = true
    delete_on_termination = true
  }

  metadata_options {
    http_endpoint = "enabled"
    http_tokens   = "required"
  }

  # Standardmodus vermeidet kostenpflichtige Unlimited-Zusatzcredits.
  credit_specification {
    cpu_credits = "standard"
  }

  tags = {
    Name    = var.instance_name
    Project = "TicTacTest"
  }
}
