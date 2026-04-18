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

variable "agentcore_runtime_name" {
  description = "AgentCore Runtime name placeholder for IAM scoping."
  type        = string
  default     = "mdip-poc-runtime"
}

variable "embedding_model_id" {
  description = "Bedrock embedding model used by the knowledge base."
  type        = string
  default     = "amazon.titan-embed-text-v2:0"
}

variable "embedding_dimensions" {
  description = "Embedding dimensions for the knowledge base vector index."
  type        = number
  default     = 256
}

variable "sonnet_model_id" {
  description = "Bedrock model ID for Claude Sonnet."
  type        = string
  default     = "anthropic.claude-sonnet-4-6"
}

variable "sonnet_inference_profile_id" {
  description = "Bedrock inference profile ID used to invoke Claude Sonnet 4.6."
  type        = string
  default     = "us.anthropic.claude-sonnet-4-6"
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

variable "canonical_chunk_max_chars" {
  description = "Maximum character count per canonical markdown chunk file before splitting."
  type        = number
  default     = 10000
}

variable "kb_coordinator_batch_size" {
  description = "Maximum number of canonical documents the KB coordinator will ingest per run."
  type        = number
  default     = 10
}

variable "kb_coordinator_schedule_expression" {
  description = "EventBridge schedule expression for the KB coordinator."
  type        = string
  default     = "rate(5 minutes)"
}

variable "ops_monitor_schedule_expression" {
  description = "EventBridge schedule expression for the operational monitor."
  type        = string
  default     = "rate(5 minutes)"
}

variable "stale_ingesting_threshold_minutes" {
  description = "Age threshold in minutes before an INGESTING document is considered stuck."
  type        = number
  default     = 15
}

variable "stale_submission_threshold_minutes" {
  description = "Age threshold in minutes before a non-terminal submission is considered stuck."
  type        = number
  default     = 15
}

variable "tags" {
  description = "Additional tags to apply to resources."
  type        = map(string)
  default     = {}
}
