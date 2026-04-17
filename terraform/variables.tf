variable "aws_region" {
  description = "AWS region for all resources."
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Deployment environment name."
  type        = string
  default     = "dev"
}

variable "name_prefix" {
  description = "Short prefix used in resource names."
  type        = string
  default     = "mdip-poc"
}

variable "knowledge_base_id" {
  description = "Optional Bedrock Knowledge Base ID. Leave empty until the KB is created."
  type        = string
  default     = ""
}

variable "agentcore_runtime_name" {
  description = "AgentCore Runtime name placeholder for IAM scoping."
  type        = string
  default     = "mdip-poc-runtime"
}

variable "sonnet_model_id" {
  description = "Bedrock model ID for Claude Sonnet."
  type        = string
  default     = "anthropic.claude-sonnet-4-6"
}

variable "ingestion_retention_days" {
  description = "Retention for ingestion/ prefix objects."
  type        = number
  default     = 14
}

variable "processed_retention_days" {
  description = "Retention for processed/ prefix objects."
  type        = number
  default     = 3
}

variable "tags" {
  description = "Additional tags to apply to resources."
  type        = map(string)
  default     = {}
}
