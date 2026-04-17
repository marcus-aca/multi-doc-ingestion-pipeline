output "aws_region" {
  description = "Region used by this Terraform stack."
  value       = var.aws_region
}

output "document_bucket_name" {
  description = "S3 bucket for ingestion, processed, and canonical document prefixes."
  value       = aws_s3_bucket.documents.id
}

output "submission_registry_table_name" {
  description = "Submission registry DynamoDB table name."
  value       = aws_dynamodb_table.submission_registry.name
}

output "raw_file_registry_table_name" {
  description = "Raw file registry DynamoDB table name."
  value       = aws_dynamodb_table.raw_file_registry.name
}

output "document_registry_table_name" {
  description = "Document registry DynamoDB table name."
  value       = aws_dynamodb_table.document_registry.name
}

output "ingestion_run_table_name" {
  description = "Ingestion run DynamoDB table name."
  value       = aws_dynamodb_table.ingestion_run.name
}

output "agentcore_runtime_execution_role_arn" {
  description = "IAM role ARN for AgentCore Runtime execution."
  value       = aws_iam_role.agentcore_runtime_execution.arn
}

output "upload_event_handler_lambda_name" {
  description = "Upload event handler Lambda function name."
  value       = aws_lambda_function.upload_event_handler.function_name
}

output "completion_trigger_lambda_name" {
  description = "Completion trigger Lambda function name."
  value       = aws_lambda_function.completion_trigger.function_name
}

output "submission_validator_lambda_name" {
  description = "Submission validator Lambda function name."
  value       = aws_lambda_function.submission_validator.function_name
}

output "raw_file_resolver_lambda_name" {
  description = "Raw file resolver Lambda function name."
  value       = aws_lambda_function.raw_file_resolver.function_name
}

output "submission_orchestration_state_machine_arn" {
  description = "Step Functions state machine ARN for submission orchestration."
  value       = aws_sfn_state_machine.submission_orchestration.arn
}

output "knowledge_base_id" {
  description = "Configured Bedrock Knowledge Base ID placeholder."
  value       = var.knowledge_base_id
}

output "knowledge_base_arn" {
  description = "Resolved Bedrock Knowledge Base ARN based on the configured knowledge base ID."
  value       = local.knowledge_base_arn
}

output "agentcore_runtime_name" {
  description = "Configured AgentCore Runtime name placeholder."
  value       = var.agentcore_runtime_name
}

output "sonnet_model_id" {
  description = "Configured Claude Sonnet model ID."
  value       = var.sonnet_model_id
}

output "sonnet_model_arn" {
  description = "Resolved Claude Sonnet model ARN."
  value       = local.sonnet_model_arn
}
