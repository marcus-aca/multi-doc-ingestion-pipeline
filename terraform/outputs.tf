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

output "preprocessor_lambda_name" {
  description = "Preprocessor Lambda function name."
  value       = aws_lambda_function.preprocessor.function_name
}

output "kb_coordinator_lambda_name" {
  description = "KB coordinator Lambda function name."
  value       = aws_lambda_function.kb_coordinator.function_name
}

output "query_api_lambda_name" {
  description = "Scoped query Lambda function name."
  value       = aws_lambda_function.query_api.function_name
}

output "canonical_resolver_lambda_name" {
  description = "Canonical resolver Lambda function name."
  value       = aws_lambda_function.canonical_resolver.function_name
}

output "submission_document_attacher_lambda_name" {
  description = "Submission document attacher Lambda function name."
  value       = aws_lambda_function.submission_document_attacher.function_name
}

output "submission_readiness_checker_lambda_name" {
  description = "Submission readiness checker Lambda function name."
  value       = aws_lambda_function.submission_readiness_checker.function_name
}

output "ready_callback_lambda_name" {
  description = "Ready callback Lambda function name."
  value       = aws_lambda_function.ready_callback.function_name
}

output "submission_orchestration_state_machine_arn" {
  description = "Step Functions state machine ARN for submission orchestration."
  value       = aws_sfn_state_machine.submission_orchestration.arn
}

output "knowledge_base_id" {
  description = "Provisioned Bedrock Knowledge Base ID."
  value       = local.knowledge_base_id
}

output "knowledge_base_arn" {
  description = "Provisioned Bedrock Knowledge Base ARN."
  value       = local.knowledge_base_arn
}

output "knowledge_base_data_source_id" {
  description = "Provisioned Bedrock Knowledge Base data source ID."
  value       = local.data_source_id
}

output "knowledge_base_log_group_name" {
  description = "CloudWatch Logs log group used for Bedrock Knowledge Base application logs."
  value       = aws_cloudformation_stack.bedrock_kb.outputs["KnowledgeBaseLogGroupName"]
}

output "knowledge_base_log_delivery_id" {
  description = "CloudWatch Logs delivery ID for the Bedrock Knowledge Base application logs."
  value       = aws_cloudformation_stack.bedrock_kb.outputs["KnowledgeBaseLogDeliveryId"]
}

output "knowledge_base_stack_name" {
  description = "CloudFormation stack name that provisions the Bedrock Knowledge Base and S3 Vectors storage."
  value       = aws_cloudformation_stack.bedrock_kb.name
}

output "vector_bucket_name" {
  description = "S3 Vectors bucket name used by the knowledge base."
  value       = aws_cloudformation_stack.bedrock_kb.outputs["VectorBucketName"]
}

output "vector_index_name" {
  description = "S3 Vectors index name used by the knowledge base."
  value       = aws_cloudformation_stack.bedrock_kb.outputs["VectorIndexName"]
}

output "embedding_model_id" {
  description = "Configured embedding model ID for the Bedrock Knowledge Base."
  value       = var.embedding_model_id
}

output "embedding_dimensions" {
  description = "Configured embedding dimensions for the Bedrock Knowledge Base."
  value       = var.embedding_dimensions
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

output "manual_review_queue_url" {
  description = "FIFO SQS queue URL for manual review items."
  value       = aws_sqs_queue.manual_review.url
}

output "manual_review_queue_arn" {
  description = "FIFO SQS queue ARN for manual review items."
  value       = aws_sqs_queue.manual_review.arn
}

output "operations_dashboard_name" {
  description = "CloudWatch dashboard name for operational monitoring."
  value       = aws_cloudwatch_dashboard.operations.dashboard_name
}
