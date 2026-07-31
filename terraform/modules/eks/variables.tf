# =============================================================================
# EXAMPLE CONFIGURATION - Getting Started Template
# =============================================================================
# This file is provided as a starting point for deployments. It should be
# reviewed and modified to match your specific infrastructure requirements,
# security policies, and operational needs before use in production.
# =============================================================================

variable "cluster_name" {
  description = "Name of the EKS cluster"
  type        = string
}

variable "kubernetes_version" {
  description = "Kubernetes version for the EKS cluster"
  type        = string
  default     = "1.31"
}

variable "enabled_cluster_log_types" {
  description = "List of EKS cluster log types to enable (api, audit, authenticator, controllerManager, scheduler)"
  type        = list(string)
  default     = ["api", "audit", "authenticator", "controllerManager", "scheduler"]
}

variable "vpc_id" {
  description = "ID of the VPC where the cluster will be deployed"
  type        = string
}

variable "subnet_ids" {
  description = "List of subnet IDs for the EKS cluster and node groups"
  type        = list(string)
}

variable "endpoint_public_access" {
  description = "Whether the EKS API server endpoint is publicly accessible"
  type        = bool
  default     = true
}

variable "endpoint_public_access_cidrs" {
  description = "CIDR blocks allowed to reach the public API server endpoint when endpoint_public_access is true. Defaults to fully open for backwards compatibility; restrict this to operator/VPN ranges in real deployments."
  type        = list(string)
  default     = ["0.0.0.0/0"]
}

variable "secrets_encryption_key_arn" {
  description = "ARN of a customer-managed KMS key used for envelope encryption of Kubernetes secrets (EKS encryption_config). Empty (the default) leaves envelope encryption off. Enabling it on an existing cluster is irreversible — the key must not be deleted afterwards."
  type        = string
  default     = ""
}

variable "node_groups" {
  description = "Map of managed node group configurations"
  type = map(object({
    instance_types = list(string)
    desired_size   = number
    min_size       = number
    max_size       = number
    capacity_type  = optional(string, "ON_DEMAND")
    disk_size      = optional(number, 50)
    labels         = optional(map(string), {})
  }))
  default = {
    default = {
      instance_types = ["t3.large"]
      desired_size   = 2
      min_size       = 1
      max_size       = 5
    }
  }
}

variable "tags" {
  description = "Additional tags to apply to all resources"
  type        = map(string)
  default     = {}
}
