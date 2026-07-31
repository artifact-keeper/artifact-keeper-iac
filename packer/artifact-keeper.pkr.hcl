packer {
  required_plugins {
    amazon = {
      version = ">= 1.3.0"
      source  = "github.com/hashicorp/amazon"
    }
  }
}

# -----------------------------------------------------------------------------
# Variables
# -----------------------------------------------------------------------------

variable "artifact_keeper_version" {
  type        = string
  default     = "1.6.0"
  description = "Backend image tag to bake into the AMI (the compose stack's web image is pinned separately in aws-scripts/docker-compose.yml)."
}

variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "instance_type" {
  type    = string
  default = "t3.medium"
}

variable "ami_regions" {
  type        = list(string)
  default     = []
  description = "Additional regions to copy the AMI to. Empty = only build region."
}

# -----------------------------------------------------------------------------
# Source: Amazon EBS (Ubuntu 24.04 LTS)
# -----------------------------------------------------------------------------

source "amazon-ebs" "artifact-keeper" {
  ami_name        = "artifact-keeper-${var.artifact_keeper_version}-{{timestamp}}"
  ami_description = "Artifact Keeper ${var.artifact_keeper_version} - open-source artifact registry with PostgreSQL, OpenSearch, and Trivy."
  instance_type   = var.instance_type
  region          = var.aws_region
  ami_regions     = var.ami_regions

  source_ami_filter {
    filters = {
      name                = "ubuntu/images/hvm-ssd-gp3/ubuntu-noble-24.04-amd64-server-*"
      root-device-type    = "ebs"
      virtualization-type = "hvm"
    }
    most_recent = true
    owners      = ["099720109477"] # Canonical
  }

  ssh_username = "ubuntu"

  launch_block_device_mappings {
    device_name           = "/dev/sda1"
    volume_size           = 30
    volume_type           = "gp3"
    delete_on_termination = true
  }

  tags = {
    Name        = "artifact-keeper-${var.artifact_keeper_version}"
    Application = "artifact-keeper"
    Version     = var.artifact_keeper_version
    OS          = "ubuntu-24.04"
    ManagedBy   = "packer"
  }
}

# -----------------------------------------------------------------------------
# Build
# -----------------------------------------------------------------------------

build {
  sources = ["source.amazon-ebs.artifact-keeper"]

  # Create destination directory first
  provisioner "shell" {
    inline = ["mkdir -p /tmp/ak-scripts"]
  }

  # Upload scripts and compose file
  provisioner "file" {
    source      = "${path.root}/../aws-scripts/"
    destination = "/tmp/ak-scripts"
  }

  # Install Docker and pull images
  provisioner "shell" {
    environment_vars = [
      "ARTIFACT_KEEPER_VERSION=${var.artifact_keeper_version}",
      "DEBIAN_FRONTEND=noninteractive",
    ]
    execute_command = "chmod +x {{ .Path }}; sudo -E {{ .Path }}"
    scripts = [
      "${path.root}/../aws-scripts/01-docker.sh",
      "${path.root}/../aws-scripts/02-artifact-keeper.sh",
      "${path.root}/../aws-scripts/99-cleanup.sh",
    ]
  }
}
