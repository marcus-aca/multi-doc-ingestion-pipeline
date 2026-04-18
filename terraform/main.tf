provider "aws" {
  region = var.aws_region
}

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

data "archive_file" "upload_event_handler" {
  type        = "zip"
  source_file = "${path.module}/../src/lambdas/upload_event_handler/app.py"
  output_path = "${path.module}/build/upload_event_handler.zip"
}

data "archive_file" "completion_trigger" {
  type        = "zip"
  source_file = "${path.module}/../src/lambdas/completion_trigger/app.py"
  output_path = "${path.module}/build/completion_trigger.zip"
}

data "archive_file" "submission_validator" {
  type        = "zip"
  source_file = "${path.module}/../src/lambdas/submission_validator/app.py"
  output_path = "${path.module}/build/submission_validator.zip"
}

data "archive_file" "raw_file_resolver" {
  type        = "zip"
  source_file = "${path.module}/../src/lambdas/raw_file_resolver/app.py"
  output_path = "${path.module}/build/raw_file_resolver.zip"
}

data "archive_file" "preprocessor" {
  type        = "zip"
  source_file = "${path.module}/../src/lambdas/preprocessor/app.py"
  output_path = "${path.module}/build/preprocessor.zip"
}

data "archive_file" "canonical_resolver" {
  type        = "zip"
  source_file = "${path.module}/../src/lambdas/canonical_resolver/app.py"
  output_path = "${path.module}/build/canonical_resolver.zip"
}

data "archive_file" "submission_document_attacher" {
  type        = "zip"
  source_file = "${path.module}/../src/lambdas/submission_document_attacher/app.py"
  output_path = "${path.module}/build/submission_document_attacher.zip"
}

data "archive_file" "submission_readiness_checker" {
  type        = "zip"
  source_file = "${path.module}/../src/lambdas/submission_readiness_checker/app.py"
  output_path = "${path.module}/build/submission_readiness_checker.zip"
}

data "archive_file" "ready_callback" {
  type        = "zip"
  source_file = "${path.module}/../src/lambdas/ready_callback/app.py"
  output_path = "${path.module}/build/ready_callback.zip"
}

data "archive_file" "kb_coordinator" {
  type        = "zip"
  source_file = "${path.module}/../src/lambdas/kb_coordinator/app.py"
  output_path = "${path.module}/build/kb_coordinator.zip"
}

data "archive_file" "query_api" {
  type        = "zip"
  source_file = "${path.module}/../src/lambdas/query_api/app.py"
  output_path = "${path.module}/build/query_api.zip"
}

data "archive_file" "ops_monitor" {
  type        = "zip"
  source_file = "${path.module}/../src/lambdas/ops_monitor/app.py"
  output_path = "${path.module}/build/ops_monitor.zip"
}

locals {
  resource_prefix = "${var.name_prefix}-${var.environment}"

  common_tags = merge(
    {
      Project     = "multi-doc-ingestion-pipeline"
      Environment = var.environment
      ManagedBy   = "terraform"
    },
    var.tags
  )

  document_bucket_name = lower(
    "${var.name_prefix}-${var.environment}-docs-${data.aws_caller_identity.current.account_id}-${data.aws_region.current.name}"
  )

  vector_bucket_name = lower(
    "${var.name_prefix}-${var.environment}-vectors-${data.aws_caller_identity.current.account_id}-${replace(data.aws_region.current.name, "-", "")}"
  )

  vector_index_name = lower("${var.name_prefix}-${var.environment}-index-v2")

  knowledge_base_name                = "${replace(var.name_prefix, "-", "_")}_${var.environment}_kb_v2"
  data_source_name                   = "${replace(var.name_prefix, "-", "_")}_${var.environment}_ds_v3"
  knowledge_base_log_group_name      = "/aws/bedrock/knowledge-bases/${local.resource_prefix}"
  knowledge_base_log_delivery_source = substr("${replace(var.name_prefix, "-", "_")}_${var.environment}_kb_src_v2", 0, 60)
  knowledge_base_log_delivery_dest   = substr("${replace(var.name_prefix, "-", "_")}_${var.environment}_kb_dst_v2", 0, 60)

  embedding_model_arn = "arn:aws:bedrock:${var.aws_region}::foundation-model/${var.embedding_model_id}"

  knowledge_base_id  = try(aws_cloudformation_stack.bedrock_kb.outputs["KnowledgeBaseId"], "")
  knowledge_base_arn = try(aws_cloudformation_stack.bedrock_kb.outputs["KnowledgeBaseArn"], "*")
  data_source_id     = try(aws_cloudformation_stack.bedrock_kb.outputs["DataSourceId"], "")
  vector_bucket_arn  = "arn:aws:s3vectors:${var.aws_region}:${data.aws_caller_identity.current.account_id}:bucket/${local.vector_bucket_name}"
  vector_index_arn   = "${local.vector_bucket_arn}/index/${local.vector_index_name}"

  sonnet_model_arn = "arn:aws:bedrock:${var.aws_region}::foundation-model/${var.sonnet_model_id}"

  lambda_log_groups = {
    upload_event_handler         = "/aws/lambda/${local.resource_prefix}-upload-event-handler"
    preprocessor                 = "/aws/lambda/${local.resource_prefix}-preprocessor"
    kb_coordinator               = "/aws/lambda/${local.resource_prefix}-kb-coordinator"
    query_api                    = "/aws/lambda/${local.resource_prefix}-query-api"
    ops_monitor                  = "/aws/lambda/${local.resource_prefix}-ops-monitor"
    completion_trigger           = "/aws/lambda/${local.resource_prefix}-completion-trigger"
    submission_validator         = "/aws/lambda/${local.resource_prefix}-submission-validator"
    raw_file_resolver            = "/aws/lambda/${local.resource_prefix}-raw-file-resolver"
    canonical_resolver           = "/aws/lambda/${local.resource_prefix}-canonical-resolver"
    submission_document_attacher = "/aws/lambda/${local.resource_prefix}-submission-document-attacher"
    submission_readiness_checker = "/aws/lambda/${local.resource_prefix}-submission-readiness-checker"
    ready_callback               = "/aws/lambda/${local.resource_prefix}-ready-callback"
  }

  non_terminal_submission_statuses = ["RECEIVING", "COMPLETE", "WAITING_FOR_INDEX"]
  ingestion_run_statuses           = ["STARTED", "SUCCEEDED", "FAILED"]
}

resource "aws_cloudformation_stack" "bedrock_kb" {
  name               = "${local.resource_prefix}-bedrock-kb"
  on_failure         = "DELETE"
  timeout_in_minutes = 30

  template_body = templatefile("${path.module}/templates/bedrock-kb-s3vectors.yaml.tftpl", {
    vector_bucket_name                 = local.vector_bucket_name
    vector_index_name                  = local.vector_index_name
    knowledge_base_name                = local.knowledge_base_name
    data_source_name                   = local.data_source_name
    knowledge_base_role_arn            = aws_iam_role.bedrock_knowledge_base.arn
    embedding_model_arn                = local.embedding_model_arn
    embedding_dimensions               = var.embedding_dimensions
    source_bucket_arn                  = aws_s3_bucket.documents.arn
    source_inclusion_prefix            = "canonical/"
    knowledge_base_log_group_name      = local.knowledge_base_log_group_name
    knowledge_base_log_delivery_source = local.knowledge_base_log_delivery_source
    knowledge_base_log_delivery_dest   = local.knowledge_base_log_delivery_dest
  })

  tags = local.common_tags

  depends_on = [
    aws_s3_bucket.documents,
    aws_s3_bucket_server_side_encryption_configuration.documents,
    aws_iam_role_policy.bedrock_knowledge_base,
  ]
}

resource "aws_s3_bucket" "documents" {
  bucket        = local.document_bucket_name
  force_destroy = true

  tags = merge(local.common_tags, {
    Name = local.document_bucket_name
  })
}

resource "aws_s3_bucket_server_side_encryption_configuration" "documents" {
  bucket = aws_s3_bucket.documents.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "documents" {
  bucket = aws_s3_bucket.documents.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_lifecycle_configuration" "documents" {
  bucket = aws_s3_bucket.documents.id

  rule {
    id     = "expire-ingestion-prefix"
    status = "Enabled"

    filter {
      prefix = "ingestion/"
    }

    expiration {
      days = var.ingestion_retention_days
    }
  }

  rule {
    id     = "expire-processed-prefix"
    status = "Enabled"

    filter {
      prefix = "processed/"
    }

    expiration {
      days = var.processed_retention_days
    }
  }
}

resource "aws_s3_object" "prefix_markers" {
  for_each = {
    ingestion = "ingestion/.keep"
    processed = "processed/.keep"
  }

  bucket       = aws_s3_bucket.documents.id
  key          = each.value
  content      = ""
  content_type = "text/plain"

  tags = local.common_tags
}

resource "aws_dynamodb_table" "submission_registry" {
  name         = "${local.resource_prefix}-submission-registry"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "submissionId"

  attribute {
    name = "submissionId"
    type = "S"
  }

  point_in_time_recovery {
    enabled = true
  }

  tags = merge(local.common_tags, {
    Name = "${local.resource_prefix}-submission-registry"
  })
}

resource "aws_dynamodb_table" "raw_file_registry" {
  name         = "${local.resource_prefix}-raw-file-registry"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "rawFileHash"

  attribute {
    name = "rawFileHash"
    type = "S"
  }

  point_in_time_recovery {
    enabled = true
  }

  tags = merge(local.common_tags, {
    Name = "${local.resource_prefix}-raw-file-registry"
  })
}

resource "aws_dynamodb_table" "document_registry" {
  name         = "${local.resource_prefix}-document-registry"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "documentId"

  attribute {
    name = "documentId"
    type = "S"
  }

  attribute {
    name = "canonicalHash"
    type = "S"
  }

  attribute {
    name = "businessDocumentKey"
    type = "S"
  }

  global_secondary_index {
    name            = "canonicalHash-index"
    hash_key        = "canonicalHash"
    projection_type = "ALL"
  }

  global_secondary_index {
    name            = "businessDocumentKey-index"
    hash_key        = "businessDocumentKey"
    projection_type = "ALL"
  }

  point_in_time_recovery {
    enabled = true
  }

  tags = merge(local.common_tags, {
    Name = "${local.resource_prefix}-document-registry"
  })
}

resource "aws_dynamodb_table" "ingestion_run" {
  name         = "${local.resource_prefix}-ingestion-run"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "ingestionRunId"

  attribute {
    name = "ingestionRunId"
    type = "S"
  }

  point_in_time_recovery {
    enabled = true
  }

  tags = merge(local.common_tags, {
    Name = "${local.resource_prefix}-ingestion-run"
  })
}

resource "aws_cloudwatch_log_group" "lambda" {
  for_each = local.lambda_log_groups

  name              = each.value
  retention_in_days = 14

  tags = merge(local.common_tags, {
    Name = each.value
  })
}

resource "aws_cloudwatch_log_group" "step_functions" {
  name              = "/aws/states/${local.resource_prefix}-submission-orchestration"
  retention_in_days = 14

  tags = merge(local.common_tags, {
    Name = "/aws/states/${local.resource_prefix}-submission-orchestration"
  })
}

resource "aws_sqs_queue" "manual_review_dlq" {
  name                        = "${local.resource_prefix}-manual-review-dlq.fifo"
  fifo_queue                  = true
  content_based_deduplication = true
  message_retention_seconds   = 1209600

  tags = merge(local.common_tags, {
    Name = "${local.resource_prefix}-manual-review-dlq"
  })
}

resource "aws_sqs_queue" "manual_review" {
  name                        = "${local.resource_prefix}-manual-review.fifo"
  fifo_queue                  = true
  content_based_deduplication = true
  visibility_timeout_seconds  = 60
  message_retention_seconds   = 1209600

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.manual_review_dlq.arn
    maxReceiveCount     = 5
  })

  tags = merge(local.common_tags, {
    Name = "${local.resource_prefix}-manual-review"
  })
}

resource "aws_lambda_function" "upload_event_handler" {
  function_name    = "${local.resource_prefix}-upload-event-handler"
  role             = aws_iam_role.upload_event_handler.arn
  handler          = "app.lambda_handler"
  runtime          = "python3.12"
  filename         = data.archive_file.upload_event_handler.output_path
  source_code_hash = data.archive_file.upload_event_handler.output_base64sha256
  timeout          = 30

  environment {
    variables = {
      SUBMISSION_REGISTRY_TABLE = aws_dynamodb_table.submission_registry.name
      INGESTION_PREFIX          = "ingestion/"
    }
  }

  depends_on = [
    aws_cloudwatch_log_group.lambda
  ]

  tags = merge(local.common_tags, {
    Name = "${local.resource_prefix}-upload-event-handler"
  })
}

resource "aws_lambda_function" "completion_trigger" {
  function_name    = "${local.resource_prefix}-completion-trigger"
  role             = aws_iam_role.completion_trigger.arn
  handler          = "app.lambda_handler"
  runtime          = "python3.12"
  filename         = data.archive_file.completion_trigger.output_path
  source_code_hash = data.archive_file.completion_trigger.output_base64sha256
  timeout          = 30

  environment {
    variables = {
      STATE_MACHINE_ARN = aws_sfn_state_machine.submission_orchestration.arn
    }
  }

  depends_on = [
    aws_cloudwatch_log_group.lambda
  ]

  tags = merge(local.common_tags, {
    Name = "${local.resource_prefix}-completion-trigger"
  })
}

resource "aws_lambda_function" "submission_validator" {
  function_name    = "${local.resource_prefix}-submission-validator"
  role             = aws_iam_role.submission_validator.arn
  handler          = "app.lambda_handler"
  runtime          = "python3.12"
  filename         = data.archive_file.submission_validator.output_path
  source_code_hash = data.archive_file.submission_validator.output_base64sha256
  timeout          = 30

  depends_on = [
    aws_cloudwatch_log_group.lambda
  ]

  tags = merge(local.common_tags, {
    Name = "${local.resource_prefix}-submission-validator"
  })
}

resource "aws_lambda_function" "raw_file_resolver" {
  function_name    = "${local.resource_prefix}-raw-file-resolver"
  role             = aws_iam_role.raw_file_resolver.arn
  handler          = "app.lambda_handler"
  runtime          = "python3.12"
  filename         = data.archive_file.raw_file_resolver.output_path
  source_code_hash = data.archive_file.raw_file_resolver.output_base64sha256
  timeout          = 30

  environment {
    variables = {
      DOCUMENT_BUCKET_NAME    = aws_s3_bucket.documents.id
      RAW_FILE_REGISTRY_TABLE = aws_dynamodb_table.raw_file_registry.name
      INGESTION_PREFIX        = "ingestion/"
    }
  }

  depends_on = [
    aws_cloudwatch_log_group.lambda
  ]

  tags = merge(local.common_tags, {
    Name = "${local.resource_prefix}-raw-file-resolver"
  })
}

resource "aws_lambda_function" "preprocessor" {
  function_name    = "${local.resource_prefix}-preprocessor"
  role             = aws_iam_role.preprocessor.arn
  handler          = "app.lambda_handler"
  runtime          = "python3.12"
  filename         = data.archive_file.preprocessor.output_path
  source_code_hash = data.archive_file.preprocessor.output_base64sha256
  timeout          = 30

  environment {
    variables = {
      DOCUMENT_BUCKET_NAME    = aws_s3_bucket.documents.id
      RAW_FILE_REGISTRY_TABLE = aws_dynamodb_table.raw_file_registry.name
      INGESTION_PREFIX        = "ingestion/"
      PROCESSED_PREFIX        = "processed/"
      MANUAL_REVIEW_QUEUE_URL = aws_sqs_queue.manual_review.url
    }
  }

  depends_on = [
    aws_cloudwatch_log_group.lambda
  ]

  tags = merge(local.common_tags, {
    Name = "${local.resource_prefix}-preprocessor"
  })
}

resource "aws_lambda_function" "canonical_resolver" {
  function_name    = "${local.resource_prefix}-canonical-resolver"
  role             = aws_iam_role.canonical_resolver.arn
  handler          = "app.lambda_handler"
  runtime          = "python3.12"
  filename         = data.archive_file.canonical_resolver.output_path
  source_code_hash = data.archive_file.canonical_resolver.output_base64sha256
  timeout          = 120

  environment {
    variables = {
      DOCUMENT_BUCKET_NAME      = aws_s3_bucket.documents.id
      RAW_FILE_REGISTRY_TABLE   = aws_dynamodb_table.raw_file_registry.name
      DOCUMENT_REGISTRY_TABLE   = aws_dynamodb_table.document_registry.name
      PROCESSED_PREFIX          = "processed/"
      CANONICAL_PREFIX          = "canonical/"
      CANONICAL_CHUNK_MAX_CHARS = tostring(var.canonical_chunk_max_chars)
    }
  }

  depends_on = [
    aws_cloudwatch_log_group.lambda
  ]

  tags = merge(local.common_tags, {
    Name = "${local.resource_prefix}-canonical-resolver"
  })
}

resource "aws_lambda_function" "submission_document_attacher" {
  function_name    = "${local.resource_prefix}-submission-document-attacher"
  role             = aws_iam_role.submission_document_attacher.arn
  handler          = "app.lambda_handler"
  runtime          = "python3.12"
  filename         = data.archive_file.submission_document_attacher.output_path
  source_code_hash = data.archive_file.submission_document_attacher.output_base64sha256
  timeout          = 30

  environment {
    variables = {
      SUBMISSION_REGISTRY_TABLE = aws_dynamodb_table.submission_registry.name
    }
  }

  depends_on = [
    aws_cloudwatch_log_group.lambda
  ]

  tags = merge(local.common_tags, {
    Name = "${local.resource_prefix}-submission-document-attacher"
  })
}

resource "aws_lambda_function" "submission_readiness_checker" {
  function_name    = "${local.resource_prefix}-submission-readiness-checker"
  role             = aws_iam_role.submission_readiness_checker.arn
  handler          = "app.lambda_handler"
  runtime          = "python3.12"
  filename         = data.archive_file.submission_readiness_checker.output_path
  source_code_hash = data.archive_file.submission_readiness_checker.output_base64sha256
  timeout          = 30

  environment {
    variables = {
      SUBMISSION_REGISTRY_TABLE = aws_dynamodb_table.submission_registry.name
      DOCUMENT_REGISTRY_TABLE   = aws_dynamodb_table.document_registry.name
    }
  }

  depends_on = [
    aws_cloudwatch_log_group.lambda
  ]

  tags = merge(local.common_tags, {
    Name = "${local.resource_prefix}-submission-readiness-checker"
  })
}

resource "aws_lambda_function" "ready_callback" {
  function_name    = "${local.resource_prefix}-ready-callback"
  role             = aws_iam_role.ready_callback.arn
  handler          = "app.lambda_handler"
  runtime          = "python3.12"
  filename         = data.archive_file.ready_callback.output_path
  source_code_hash = data.archive_file.ready_callback.output_base64sha256
  timeout          = 30

  environment {
    variables = {
      SUBMISSION_REGISTRY_TABLE = aws_dynamodb_table.submission_registry.name
      MANUAL_REVIEW_QUEUE_URL   = aws_sqs_queue.manual_review.url
    }
  }

  depends_on = [
    aws_cloudwatch_log_group.lambda
  ]

  tags = merge(local.common_tags, {
    Name = "${local.resource_prefix}-ready-callback"
  })
}

resource "aws_lambda_function" "kb_coordinator" {
  function_name    = "${local.resource_prefix}-kb-coordinator"
  role             = aws_iam_role.kb_coordinator.arn
  handler          = "app.lambda_handler"
  runtime          = "python3.12"
  filename         = data.archive_file.kb_coordinator.output_path
  source_code_hash = data.archive_file.kb_coordinator.output_base64sha256
  timeout          = 60

  environment {
    variables = {
      DOCUMENT_REGISTRY_TABLE   = aws_dynamodb_table.document_registry.name
      INGESTION_RUN_TABLE       = aws_dynamodb_table.ingestion_run.name
      KNOWLEDGE_BASE_ID         = local.knowledge_base_id
      DATA_SOURCE_ID            = local.data_source_id
      KB_COORDINATOR_BATCH_SIZE = tostring(var.kb_coordinator_batch_size)
    }
  }

  depends_on = [
    aws_cloudwatch_log_group.lambda
  ]

  tags = merge(local.common_tags, {
    Name = "${local.resource_prefix}-kb-coordinator"
  })
}

resource "aws_lambda_function" "ops_monitor" {
  function_name    = "${local.resource_prefix}-ops-monitor"
  role             = aws_iam_role.ops_monitor.arn
  handler          = "app.lambda_handler"
  runtime          = "python3.12"
  filename         = data.archive_file.ops_monitor.output_path
  source_code_hash = data.archive_file.ops_monitor.output_base64sha256
  timeout          = 60

  environment {
    variables = {
      SUBMISSION_REGISTRY_TABLE          = aws_dynamodb_table.submission_registry.name
      DOCUMENT_REGISTRY_TABLE            = aws_dynamodb_table.document_registry.name
      INGESTION_RUN_TABLE                = aws_dynamodb_table.ingestion_run.name
      MANUAL_REVIEW_QUEUE_URL            = aws_sqs_queue.manual_review.url
      OPERATIONS_METRIC_NAMESPACE        = "MDIP/Operations"
      ENVIRONMENT                        = var.environment
      STALE_INGESTING_THRESHOLD_MINUTES  = tostring(var.stale_ingesting_threshold_minutes)
      STALE_SUBMISSION_THRESHOLD_MINUTES = tostring(var.stale_submission_threshold_minutes)
    }
  }

  depends_on = [
    aws_cloudwatch_log_group.lambda
  ]

  tags = merge(local.common_tags, {
    Name = "${local.resource_prefix}-ops-monitor"
  })
}

resource "aws_lambda_function" "query_api" {
  function_name    = "${local.resource_prefix}-query-api"
  role             = aws_iam_role.query_api.arn
  handler          = "app.lambda_handler"
  runtime          = "python3.12"
  filename         = data.archive_file.query_api.output_path
  source_code_hash = data.archive_file.query_api.output_base64sha256
  timeout          = 30
  memory_size      = 256

  environment {
    variables = {
      SUBMISSION_REGISTRY_TABLE     = aws_dynamodb_table.submission_registry.name
      KNOWLEDGE_BASE_ID             = local.knowledge_base_id
      SONNET_MODEL_ID               = var.sonnet_model_id
      SONNET_INFERENCE_PROFILE_ID   = var.sonnet_inference_profile_id
      QUERY_API_DEFAULT_MAX_RESULTS = "5"
      QUERY_API_MAX_SNIPPET_CHARS   = "1200"
      QUERY_API_MAX_MODEL_SNIPPETS  = "4"
      QUERY_API_MAX_TOKENS          = "400"
    }
  }

  depends_on = [
    aws_cloudwatch_log_group.lambda
  ]

  tags = merge(local.common_tags, {
    Name = "${local.resource_prefix}-query-api"
  })
}

resource "aws_cloudwatch_event_rule" "kb_coordinator_schedule" {
  name                = "${local.resource_prefix}-kb-coordinator-schedule"
  description         = "Periodic KB ingestion-job coordination for pending canonical docs."
  schedule_expression = var.kb_coordinator_schedule_expression
}

resource "aws_cloudwatch_event_rule" "ops_monitor_schedule" {
  name                = "${local.resource_prefix}-ops-monitor-schedule"
  description         = "Periodic operational monitoring for stale pipeline items and manual review routing."
  schedule_expression = var.ops_monitor_schedule_expression
}

resource "aws_cloudwatch_event_target" "kb_coordinator_schedule" {
  rule      = aws_cloudwatch_event_rule.kb_coordinator_schedule.name
  target_id = "kb-coordinator"
  arn       = aws_lambda_function.kb_coordinator.arn
}

resource "aws_cloudwatch_event_target" "ops_monitor_schedule" {
  rule      = aws_cloudwatch_event_rule.ops_monitor_schedule.name
  target_id = "ops-monitor"
  arn       = aws_lambda_function.ops_monitor.arn
}

resource "aws_lambda_permission" "allow_eventbridge_kb_coordinator" {
  statement_id  = "AllowExecutionFromEventBridgeKbCoordinator"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.kb_coordinator.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.kb_coordinator_schedule.arn
}

resource "aws_lambda_permission" "allow_eventbridge_ops_monitor" {
  statement_id  = "AllowExecutionFromEventBridgeOpsMonitor"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.ops_monitor.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.ops_monitor_schedule.arn
}

resource "aws_lambda_permission" "allow_s3_upload_events" {
  statement_id  = "AllowExecutionFromS3IngestionBucket"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.upload_event_handler.function_name
  principal     = "s3.amazonaws.com"
  source_arn    = aws_s3_bucket.documents.arn
}

resource "aws_sfn_state_machine" "submission_orchestration" {
  name     = "${local.resource_prefix}-submission-orchestration"
  role_arn = aws_iam_role.step_functions.arn

  definition = jsonencode({
    Comment = "Phase 11 submission orchestration through canonical resolution and readiness"
    StartAt = "LoadSubmissionState"
    States = {
      LoadSubmissionState = {
        Type     = "Task"
        Resource = "arn:aws:states:::aws-sdk:dynamodb:getItem"
        Parameters = {
          TableName = aws_dynamodb_table.submission_registry.name
          Key = {
            submissionId = {
              "S.$" = "$.submissionId"
            }
          }
        }
        ResultPath = "$.loadSubmissionResult"
        Next       = "ValidateManifestAndFilesPresent"
      }
      ValidateManifestAndFilesPresent = {
        Type     = "Task"
        Resource = "arn:aws:states:::lambda:invoke"
        Parameters = {
          FunctionName = aws_lambda_function.submission_validator.arn
          Payload = {
            "submissionId.$"    = "$.submissionId"
            "expectedFileIds.$" = "$.expectedFileIds"
            "submissionItem.$"  = "$.loadSubmissionResult.Item"
          }
        }
        ResultSelector = {
          "validation.$" = "$.Payload"
        }
        ResultPath = "$.validationResult"
        Next       = "ValidationSucceeded?"
      }
      "ValidationSucceeded?" = {
        Type = "Choice"
        Choices = [
          {
            Variable      = "$.validationResult.validation.isValid"
            BooleanEquals = true
            Next          = "DetectRawDuplicateFiles"
          }
        ]
        Default = "SubmissionInvalid"
      }
      DetectRawDuplicateFiles = {
        Type      = "Map"
        ItemsPath = "$.expectedFileIds"
        ItemSelector = {
          "submissionId.$" = "$.submissionId"
          "fileId.$"       = "$$.Map.Item.Value"
          "retryCount"     = 0
        }
        ResultPath = "$.rawFileResults"
        Iterator = {
          StartAt = "ResolveRawFile"
          States = {
            ResolveRawFile = {
              Type     = "Task"
              Resource = "arn:aws:states:::lambda:invoke"
              Parameters = {
                FunctionName = aws_lambda_function.raw_file_resolver.arn
                Payload = {
                  "submissionId.$" = "$.submissionId"
                  "fileId.$"       = "$.fileId"
                }
              }
              ResultSelector = {
                "resolution.$" = "$.Payload"
              }
              ResultPath = "$.rawFileCheck"
              Next       = "RawFileResolved?"
            }
            "RawFileResolved?" = {
              Type = "Choice"
              Choices = [
                {
                  Variable      = "$.rawFileCheck.resolution.ownershipClaimed"
                  BooleanEquals = true
                  Next          = "PreprocessOwnedRawFile"
                },
                {
                  Variable     = "$.rawFileCheck.resolution.rawFileStatus"
                  StringEquals = "RESOLVED"
                  Next         = "ReuseResolvedRawFile"
                },
                {
                  Variable        = "$.retryCount"
                  NumericLessThan = 3
                  Next            = "WaitForRawFileResolution"
                }
              ]
              Default = "RawFileStillProcessing"
            }
            WaitForRawFileResolution = {
              Type    = "Wait"
              Seconds = 2
              Next    = "IncrementRawFileRetryCount"
            }
            IncrementRawFileRetryCount = {
              Type = "Pass"
              Parameters = {
                "submissionId.$" = "$.submissionId"
                "fileId.$"       = "$.fileId"
                "retryCount.$"   = "States.MathAdd($.retryCount, 1)"
              }
              Next = "ResolveRawFile"
            }
            PreprocessOwnedRawFile = {
              Type     = "Task"
              Resource = "arn:aws:states:::lambda:invoke"
              Parameters = {
                FunctionName = aws_lambda_function.preprocessor.arn
                Payload = {
                  "submissionId.$" = "$.submissionId"
                  "fileId.$"       = "$.fileId"
                  "rawFileHash.$"  = "$.rawFileCheck.resolution.rawFileHash"
                }
              }
              ResultSelector = {
                "preprocessing.$" = "$.Payload"
              }
              ResultPath = "$.preprocessResult"
              Next       = "ResolveCanonicalDocument"
            }
            ResolveCanonicalDocument = {
              Type     = "Task"
              Resource = "arn:aws:states:::lambda:invoke"
              Parameters = {
                FunctionName = aws_lambda_function.canonical_resolver.arn
                Payload = {
                  "submissionId.$"          = "$.submissionId"
                  "fileId.$"                = "$.fileId"
                  "rawFileHash.$"           = "$.rawFileCheck.resolution.rawFileHash"
                  "processedS3Key.$"        = "$.preprocessResult.preprocessing.processedS3Key"
                  "canonicalHash.$"         = "$.preprocessResult.preprocessing.canonicalHash"
                  "businessDocumentKey.$"   = "$.preprocessResult.preprocessing.businessDocumentKey"
                  "sourceVersion.$"         = "$.preprocessResult.preprocessing.sourceVersion"
                  "sourceUpdatedAt.$"       = "$.preprocessResult.preprocessing.sourceUpdatedAt"
                  "normalizationStrategy.$" = "$.preprocessResult.preprocessing.normalizationStrategy"
                  "extractedMetadata.$"     = "$.preprocessResult.preprocessing.extractedMetadata"
                }
              }
              ResultSelector = {
                "canonical.$" = "$.Payload"
              }
              ResultPath = "$.canonicalResult"
              Next       = "OwnedRawFileComplete"
            }
            OwnedRawFileComplete = {
              Type = "Pass"
              Parameters = {
                "resolution.$"    = "$.rawFileCheck.resolution"
                "preprocessing.$" = "$.preprocessResult.preprocessing"
                "canonical.$"     = "$.canonicalResult.canonical"
              }
              End = true
            }
            ReuseResolvedRawFile = {
              Type = "Pass"
              Parameters = {
                "resolution.$" = "$.rawFileCheck.resolution"
                "canonical" = {
                  "action"                 = "canonical_document_reused_from_raw_resolution"
                  "documentId.$"           = "$.rawFileCheck.resolution.documentId"
                  "canonicalHash.$"        = "$.rawFileCheck.resolution.canonicalHash"
                  "reusedExistingDocument" = true
                }
              }
              End = true
            }
            RawFileStillProcessing = {
              Type  = "Fail"
              Error = "RawFileStillProcessing"
              Cause = "Raw file was still processing after retry attempts."
            }
          }
        }
        Next = "AttachSubmissionDocuments"
      }
      AttachSubmissionDocuments = {
        Type     = "Task"
        Resource = "arn:aws:states:::lambda:invoke"
        Parameters = {
          FunctionName = aws_lambda_function.submission_document_attacher.arn
          Payload = {
            "submissionId.$"   = "$.submissionId"
            "rawFileResults.$" = "$.rawFileResults"
          }
        }
        ResultSelector = {
          "attachment.$" = "$.Payload"
        }
        ResultPath = "$.attachmentResult"
        Next       = "CheckSubmissionReadiness"
      }
      CheckSubmissionReadiness = {
        Type     = "Task"
        Resource = "arn:aws:states:::lambda:invoke"
        Parameters = {
          FunctionName = aws_lambda_function.submission_readiness_checker.arn
          Payload = {
            "submissionId.$" = "$.submissionId"
            "documentIds.$"  = "$.attachmentResult.attachment.documentIds"
          }
        }
        ResultSelector = {
          "readiness.$" = "$.Payload"
        }
        ResultPath = "$.readinessResult"
        Next       = "SubmissionReady?"
      }
      "SubmissionReady?" = {
        Type = "Choice"
        Choices = [
          {
            Variable      = "$.readinessResult.readiness.hasFailures"
            BooleanEquals = true
            Next          = "SubmissionIndexingFailed"
          },
          {
            Variable      = "$.readinessResult.readiness.isReady"
            BooleanEquals = true
            Next          = "SendReadyCallback"
          }
        ]
        Default = "WaitForDocumentIndexing"
      }
      WaitForDocumentIndexing = {
        Type    = "Wait"
        Seconds = 10
        Next    = "CheckSubmissionReadiness"
      }
      SubmissionIndexingFailed = {
        Type  = "Fail"
        Error = "SubmissionIndexingFailed"
        Cause = "One or more referenced documents failed knowledge base ingestion."
      }
      SendReadyCallback = {
        Type     = "Task"
        Resource = "arn:aws:states:::lambda:invoke"
        Parameters = {
          FunctionName = aws_lambda_function.ready_callback.arn
          Payload = {
            "submissionId.$" = "$.submissionId"
            "status"         = "READY"
            "readyAt.$"      = "$.readinessResult.readiness.readyAt"
            "documentIds.$"  = "$.attachmentResult.attachment.documentIds"
          }
        }
        ResultSelector = {
          "callback.$" = "$.Payload"
        }
        ResultPath = "$.callbackResult"
        Next       = "Success"
      }
      SubmissionInvalid = {
        Type  = "Fail"
        Error = "SubmissionInvalid"
        Cause = "Submission does not exist or expected files are missing."
      }
      Success = {
        Type = "Succeed"
      }
    }
  })

  logging_configuration {
    log_destination        = "${aws_cloudwatch_log_group.step_functions.arn}:*"
    include_execution_data = true
    level                  = "ALL"
  }

  tags = merge(local.common_tags, {
    Name = "${local.resource_prefix}-submission-orchestration"
  })
}

resource "aws_s3_bucket_notification" "documents" {
  bucket = aws_s3_bucket.documents.id

  lambda_function {
    lambda_function_arn = aws_lambda_function.upload_event_handler.arn
    events              = ["s3:ObjectCreated:*"]
    filter_prefix       = "ingestion/"
  }

  depends_on = [aws_lambda_permission.allow_s3_upload_events]
}

data "aws_iam_policy_document" "lambda_assume_role" {
  statement {
    effect = "Allow"

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }

    actions = ["sts:AssumeRole"]
  }
}

data "aws_iam_policy_document" "states_assume_role" {
  statement {
    effect = "Allow"

    principals {
      type        = "Service"
      identifiers = ["states.amazonaws.com"]
    }

    actions = ["sts:AssumeRole"]
  }
}

data "aws_iam_policy_document" "agentcore_runtime_assume_role" {
  statement {
    sid    = "AssumeRolePolicy"
    effect = "Allow"

    principals {
      type        = "Service"
      identifiers = ["bedrock-agentcore.amazonaws.com"]
    }

    actions = ["sts:AssumeRole"]

    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [data.aws_caller_identity.current.account_id]
    }

    condition {
      test     = "ArnLike"
      variable = "aws:SourceArn"
      values   = ["arn:aws:bedrock-agentcore:${var.aws_region}:${data.aws_caller_identity.current.account_id}:*"]
    }
  }
}

data "aws_iam_policy_document" "bedrock_knowledge_base_assume_role" {
  statement {
    effect = "Allow"

    principals {
      type        = "Service"
      identifiers = ["bedrock.amazonaws.com"]
    }

    actions = ["sts:AssumeRole"]

    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [data.aws_caller_identity.current.account_id]
    }

    condition {
      test     = "ArnLike"
      variable = "AWS:SourceArn"
      values   = ["arn:aws:bedrock:${var.aws_region}:${data.aws_caller_identity.current.account_id}:knowledge-base/*"]
    }
  }
}

resource "aws_iam_role" "upload_event_handler" {
  name               = "${local.resource_prefix}-upload-event-handler-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
  tags               = local.common_tags
}

resource "aws_iam_role" "completion_trigger" {
  name               = "${local.resource_prefix}-completion-trigger-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
  tags               = local.common_tags
}

resource "aws_iam_role" "submission_validator" {
  name               = "${local.resource_prefix}-submission-validator-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
  tags               = local.common_tags
}

resource "aws_iam_role" "raw_file_resolver" {
  name               = "${local.resource_prefix}-raw-file-resolver-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
  tags               = local.common_tags
}

resource "aws_iam_role" "canonical_resolver" {
  name               = "${local.resource_prefix}-canonical-resolver-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
  tags               = local.common_tags
}

resource "aws_iam_role" "submission_document_attacher" {
  name               = "${local.resource_prefix}-submission-document-attacher-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
  tags               = local.common_tags
}

resource "aws_iam_role" "submission_readiness_checker" {
  name               = "${local.resource_prefix}-submission-readiness-checker-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
  tags               = local.common_tags
}

resource "aws_iam_role" "ready_callback" {
  name               = "${local.resource_prefix}-ready-callback-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
  tags               = local.common_tags
}

resource "aws_iam_role" "preprocessor" {
  name               = "${local.resource_prefix}-preprocessor-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
  tags               = local.common_tags
}

resource "aws_iam_role" "kb_coordinator" {
  name               = "${local.resource_prefix}-kb-coordinator-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
  tags               = local.common_tags
}

resource "aws_iam_role" "query_api" {
  name               = "${local.resource_prefix}-query-api-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
  tags               = local.common_tags
}

resource "aws_iam_role" "ops_monitor" {
  name               = "${local.resource_prefix}-ops-monitor-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
  tags               = local.common_tags
}

resource "aws_iam_role" "step_functions" {
  name               = "${local.resource_prefix}-step-functions-role"
  assume_role_policy = data.aws_iam_policy_document.states_assume_role.json
  tags               = local.common_tags
}

resource "aws_iam_role" "agentcore_runtime_execution" {
  name               = "${local.resource_prefix}-agentcore-runtime-execution-role"
  assume_role_policy = data.aws_iam_policy_document.agentcore_runtime_assume_role.json
  tags               = local.common_tags
}

resource "aws_iam_role" "bedrock_knowledge_base" {
  name               = "${local.resource_prefix}-bedrock-knowledge-base-role"
  assume_role_policy = data.aws_iam_policy_document.bedrock_knowledge_base_assume_role.json
  tags               = local.common_tags
}

resource "aws_iam_role_policy_attachment" "lambda_basic_execution" {
  for_each = {
    upload_event_handler         = aws_iam_role.upload_event_handler.name
    preprocessor                 = aws_iam_role.preprocessor.name
    kb_coordinator               = aws_iam_role.kb_coordinator.name
    query_api                    = aws_iam_role.query_api.name
    ops_monitor                  = aws_iam_role.ops_monitor.name
    completion_trigger           = aws_iam_role.completion_trigger.name
    submission_validator         = aws_iam_role.submission_validator.name
    raw_file_resolver            = aws_iam_role.raw_file_resolver.name
    canonical_resolver           = aws_iam_role.canonical_resolver.name
    submission_document_attacher = aws_iam_role.submission_document_attacher.name
    submission_readiness_checker = aws_iam_role.submission_readiness_checker.name
    ready_callback               = aws_iam_role.ready_callback.name
  }

  role       = each.value
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

data "aws_iam_policy_document" "upload_event_handler" {
  statement {
    effect = "Allow"
    actions = [
      "dynamodb:GetItem",
      "dynamodb:PutItem",
      "dynamodb:UpdateItem",
      "dynamodb:DescribeTable"
    ]
    resources = [aws_dynamodb_table.submission_registry.arn]
  }
}

data "aws_iam_policy_document" "completion_trigger" {
  statement {
    effect = "Allow"
    actions = [
      "states:StartExecution"
    ]
    resources = [aws_sfn_state_machine.submission_orchestration.arn]
  }
}

data "aws_iam_policy_document" "raw_file_resolver" {
  statement {
    effect = "Allow"
    actions = [
      "s3:GetObject",
      "s3:ListBucket"
    ]
    resources = [
      aws_s3_bucket.documents.arn,
      "${aws_s3_bucket.documents.arn}/ingestion/*"
    ]
  }

  statement {
    effect = "Allow"
    actions = [
      "dynamodb:GetItem",
      "dynamodb:PutItem",
      "dynamodb:UpdateItem",
      "dynamodb:DescribeTable"
    ]
    resources = [aws_dynamodb_table.raw_file_registry.arn]
  }
}

data "aws_iam_policy_document" "canonical_resolver" {
  statement {
    effect = "Allow"
    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:ListBucket"
    ]
    resources = [
      aws_s3_bucket.documents.arn,
      "${aws_s3_bucket.documents.arn}/processed/*",
      "${aws_s3_bucket.documents.arn}/canonical/*"
    ]
  }

  statement {
    effect = "Allow"
    actions = [
      "dynamodb:GetItem",
      "dynamodb:PutItem",
      "dynamodb:UpdateItem",
      "dynamodb:Query",
      "dynamodb:DescribeTable"
    ]
    resources = [
      aws_dynamodb_table.raw_file_registry.arn,
      aws_dynamodb_table.document_registry.arn,
      "${aws_dynamodb_table.document_registry.arn}/index/*"
    ]
  }
}

data "aws_iam_policy_document" "submission_document_attacher" {
  statement {
    effect = "Allow"
    actions = [
      "dynamodb:GetItem",
      "dynamodb:UpdateItem",
      "dynamodb:DescribeTable"
    ]
    resources = [aws_dynamodb_table.submission_registry.arn]
  }
}

data "aws_iam_policy_document" "submission_readiness_checker" {
  statement {
    effect = "Allow"
    actions = [
      "dynamodb:GetItem",
      "dynamodb:UpdateItem",
      "dynamodb:DescribeTable"
    ]
    resources = [
      aws_dynamodb_table.submission_registry.arn,
      aws_dynamodb_table.document_registry.arn
    ]
  }
}

data "aws_iam_policy_document" "ready_callback" {
  statement {
    effect = "Allow"
    actions = [
      "dynamodb:GetItem",
      "dynamodb:UpdateItem",
      "dynamodb:DescribeTable"
    ]
    resources = [aws_dynamodb_table.submission_registry.arn]
  }

  statement {
    effect = "Allow"
    actions = [
      "sqs:SendMessage"
    ]
    resources = [aws_sqs_queue.manual_review.arn]
  }
}


data "aws_iam_policy_document" "preprocessor" {
  statement {
    effect = "Allow"
    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:ListBucket"
    ]
    resources = [
      aws_s3_bucket.documents.arn,
      "${aws_s3_bucket.documents.arn}/ingestion/*",
      "${aws_s3_bucket.documents.arn}/processed/*",
      "${aws_s3_bucket.documents.arn}/canonical/*"
    ]
  }

  statement {
    effect = "Allow"
    actions = [
      "dynamodb:GetItem",
      "dynamodb:PutItem",
      "dynamodb:UpdateItem",
      "dynamodb:Query",
      "dynamodb:DescribeTable"
    ]
    resources = [
      aws_dynamodb_table.submission_registry.arn,
      aws_dynamodb_table.raw_file_registry.arn,
      aws_dynamodb_table.document_registry.arn,
      "${aws_dynamodb_table.document_registry.arn}/index/*"
    ]
  }

  statement {
    effect = "Allow"
    actions = [
      "sqs:SendMessage"
    ]
    resources = [aws_sqs_queue.manual_review.arn]
  }
}

data "aws_iam_policy_document" "kb_coordinator" {
  statement {
    effect = "Allow"
    actions = [
      "dynamodb:GetItem",
      "dynamodb:PutItem",
      "dynamodb:UpdateItem",
      "dynamodb:Query",
      "dynamodb:Scan",
      "dynamodb:DescribeTable"
    ]
    resources = [
      aws_dynamodb_table.document_registry.arn,
      aws_dynamodb_table.ingestion_run.arn,
      "${aws_dynamodb_table.document_registry.arn}/index/*"
    ]
  }

  statement {
    effect = "Allow"
    actions = [
      "bedrock:StartIngestionJob",
      "bedrock:GetIngestionJob"
    ]
    resources = [local.knowledge_base_arn]
  }
}

data "aws_iam_policy_document" "query_api" {
  statement {
    effect = "Allow"
    actions = [
      "dynamodb:GetItem",
      "dynamodb:Query",
      "dynamodb:DescribeTable"
    ]
    resources = [
      aws_dynamodb_table.submission_registry.arn,
      aws_dynamodb_table.document_registry.arn,
      "${aws_dynamodb_table.document_registry.arn}/index/*"
    ]
  }

  statement {
    effect = "Allow"
    actions = [
      "bedrock:Retrieve",
      "bedrock:RetrieveAndGenerate",
      "bedrock:InvokeModel",
      "bedrock:InvokeModelWithResponseStream"
    ]
    resources = ["*"]
  }
}

data "aws_iam_policy_document" "ops_monitor" {
  statement {
    effect = "Allow"
    actions = [
      "dynamodb:Scan",
      "dynamodb:DescribeTable"
    ]
    resources = [
      aws_dynamodb_table.submission_registry.arn,
      aws_dynamodb_table.document_registry.arn,
      aws_dynamodb_table.ingestion_run.arn
    ]
  }

  statement {
    effect = "Allow"
    actions = [
      "cloudwatch:PutMetricData"
    ]
    resources = ["*"]
  }

  statement {
    effect = "Allow"
    actions = [
      "sqs:SendMessage"
    ]
    resources = [aws_sqs_queue.manual_review.arn]
  }
}

data "aws_iam_policy_document" "step_functions" {
  statement {
    effect = "Allow"
    actions = [
      "lambda:InvokeFunction"
    ]
    resources = [
      "arn:aws:lambda:${var.aws_region}:${data.aws_caller_identity.current.account_id}:function:${local.resource_prefix}-*"
    ]
  }

  statement {
    effect = "Allow"
    actions = [
      "dynamodb:GetItem",
      "dynamodb:PutItem",
      "dynamodb:UpdateItem",
      "dynamodb:Query",
      "dynamodb:DescribeTable"
    ]
    resources = [
      aws_dynamodb_table.submission_registry.arn,
      aws_dynamodb_table.raw_file_registry.arn,
      aws_dynamodb_table.document_registry.arn,
      aws_dynamodb_table.ingestion_run.arn,
      "${aws_dynamodb_table.document_registry.arn}/index/*"
    ]
  }

  statement {
    effect = "Allow"
    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:ListBucket"
    ]
    resources = [
      aws_s3_bucket.documents.arn,
      "${aws_s3_bucket.documents.arn}/*"
    ]
  }

  statement {
    effect = "Allow"
    actions = [
      "logs:CreateLogDelivery",
      "logs:GetLogDelivery",
      "logs:UpdateLogDelivery",
      "logs:DeleteLogDelivery",
      "logs:ListLogDeliveries",
      "logs:PutResourcePolicy",
      "logs:DescribeResourcePolicies",
      "logs:DescribeLogGroups"
    ]
    resources = ["*"]
  }
}

data "aws_iam_policy_document" "agentcore_runtime_execution" {
  statement {
    effect = "Allow"
    actions = [
      "logs:DescribeLogStreams",
      "logs:CreateLogGroup"
    ]
    resources = [
      "arn:aws:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:log-group:/aws/bedrock-agentcore/runtimes/*"
    ]
  }

  statement {
    effect  = "Allow"
    actions = ["logs:DescribeLogGroups"]
    resources = [
      "arn:aws:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:log-group:*"
    ]
  }

  statement {
    effect = "Allow"
    actions = [
      "logs:CreateLogStream",
      "logs:PutLogEvents"
    ]
    resources = [
      "arn:aws:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:log-group:/aws/bedrock-agentcore/runtimes/*:log-stream:*"
    ]
  }

  statement {
    effect = "Allow"
    actions = [
      "xray:PutTraceSegments",
      "xray:PutTelemetryRecords",
      "xray:GetSamplingRules",
      "xray:GetSamplingTargets"
    ]
    resources = ["*"]
  }

  statement {
    effect    = "Allow"
    actions   = ["cloudwatch:PutMetricData"]
    resources = ["*"]

    condition {
      test     = "StringEquals"
      variable = "cloudwatch:namespace"
      values   = ["bedrock-agentcore"]
    }
  }

  statement {
    effect = "Allow"
    actions = [
      "bedrock-agentcore:GetWorkloadAccessToken",
      "bedrock-agentcore:GetWorkloadAccessTokenForJWT",
      "bedrock-agentcore:GetWorkloadAccessTokenForUserId"
    ]
    resources = [
      "arn:aws:bedrock-agentcore:${var.aws_region}:${data.aws_caller_identity.current.account_id}:workload-identity-directory/default",
      "arn:aws:bedrock-agentcore:${var.aws_region}:${data.aws_caller_identity.current.account_id}:workload-identity-directory/default/workload-identity/${var.agentcore_runtime_name}-*"
    ]
  }

  statement {
    effect = "Allow"
    actions = [
      "bedrock:InvokeModel",
      "bedrock:InvokeModelWithResponseStream",
      "bedrock:Retrieve",
      "bedrock:RetrieveAndGenerate"
    ]
    resources = [
      local.sonnet_model_arn,
      local.knowledge_base_arn
    ]
  }
}

data "aws_iam_policy_document" "bedrock_knowledge_base" {
  statement {
    effect = "Allow"
    actions = [
      "bedrock:ListFoundationModels",
      "bedrock:ListCustomModels"
    ]
    resources = ["*"]
  }

  statement {
    effect = "Allow"
    actions = [
      "bedrock:InvokeModel"
    ]
    resources = [local.embedding_model_arn]
  }

  statement {
    effect = "Allow"
    actions = [
      "s3:ListBucket"
    ]
    resources = [aws_s3_bucket.documents.arn]

    condition {
      test     = "StringEquals"
      variable = "aws:ResourceAccount"
      values   = [data.aws_caller_identity.current.account_id]
    }
  }

  statement {
    effect = "Allow"
    actions = [
      "s3:GetObject"
    ]
    resources = ["${aws_s3_bucket.documents.arn}/canonical/*"]

    condition {
      test     = "StringEquals"
      variable = "aws:ResourceAccount"
      values   = [data.aws_caller_identity.current.account_id]
    }
  }

  statement {
    effect = "Allow"
    actions = [
      "s3vectors:PutVectors",
      "s3vectors:GetVectors",
      "s3vectors:DeleteVectors",
      "s3vectors:QueryVectors",
      "s3vectors:GetIndex"
    ]
    resources = [local.vector_index_arn]
  }
}

resource "aws_iam_role_policy" "upload_event_handler" {
  name   = "${local.resource_prefix}-upload-event-handler-policy"
  role   = aws_iam_role.upload_event_handler.id
  policy = data.aws_iam_policy_document.upload_event_handler.json
}

resource "aws_iam_role_policy" "completion_trigger" {
  name   = "${local.resource_prefix}-completion-trigger-policy"
  role   = aws_iam_role.completion_trigger.id
  policy = data.aws_iam_policy_document.completion_trigger.json
}

resource "aws_iam_role_policy" "raw_file_resolver" {
  name   = "${local.resource_prefix}-raw-file-resolver-policy"
  role   = aws_iam_role.raw_file_resolver.id
  policy = data.aws_iam_policy_document.raw_file_resolver.json
}

resource "aws_iam_role_policy" "canonical_resolver" {
  name   = "${local.resource_prefix}-canonical-resolver-policy"
  role   = aws_iam_role.canonical_resolver.id
  policy = data.aws_iam_policy_document.canonical_resolver.json
}

resource "aws_iam_role_policy" "submission_document_attacher" {
  name   = "${local.resource_prefix}-submission-document-attacher-policy"
  role   = aws_iam_role.submission_document_attacher.id
  policy = data.aws_iam_policy_document.submission_document_attacher.json
}

resource "aws_iam_role_policy" "submission_readiness_checker" {
  name   = "${local.resource_prefix}-submission-readiness-checker-policy"
  role   = aws_iam_role.submission_readiness_checker.id
  policy = data.aws_iam_policy_document.submission_readiness_checker.json
}

resource "aws_iam_role_policy" "ready_callback" {
  name   = "${local.resource_prefix}-ready-callback-policy"
  role   = aws_iam_role.ready_callback.id
  policy = data.aws_iam_policy_document.ready_callback.json
}


resource "aws_iam_role_policy" "preprocessor" {
  name   = "${local.resource_prefix}-preprocessor-policy"
  role   = aws_iam_role.preprocessor.id
  policy = data.aws_iam_policy_document.preprocessor.json
}

resource "aws_iam_role_policy" "kb_coordinator" {
  name   = "${local.resource_prefix}-kb-coordinator-policy"
  role   = aws_iam_role.kb_coordinator.id
  policy = data.aws_iam_policy_document.kb_coordinator.json
}

resource "aws_iam_role_policy" "query_api" {
  name   = "${local.resource_prefix}-query-api-policy"
  role   = aws_iam_role.query_api.id
  policy = data.aws_iam_policy_document.query_api.json
}

resource "aws_iam_role_policy" "ops_monitor" {
  name   = "${local.resource_prefix}-ops-monitor-policy"
  role   = aws_iam_role.ops_monitor.id
  policy = data.aws_iam_policy_document.ops_monitor.json
}

resource "aws_iam_role_policy" "step_functions" {
  name   = "${local.resource_prefix}-step-functions-policy"
  role   = aws_iam_role.step_functions.id
  policy = data.aws_iam_policy_document.step_functions.json
}

resource "aws_iam_role_policy" "agentcore_runtime_execution" {
  name   = "${local.resource_prefix}-agentcore-runtime-execution-policy"
  role   = aws_iam_role.agentcore_runtime_execution.id
  policy = data.aws_iam_policy_document.agentcore_runtime_execution.json
}

resource "aws_iam_role_policy" "bedrock_knowledge_base" {
  name   = "${local.resource_prefix}-bedrock-knowledge-base-policy"
  role   = aws_iam_role.bedrock_knowledge_base.id
  policy = data.aws_iam_policy_document.bedrock_knowledge_base.json
}

resource "aws_cloudwatch_metric_alarm" "submission_orchestration_failed" {
  alarm_name          = "${local.resource_prefix}-submission-orchestration-failed"
  alarm_description   = "Alerts when submission orchestration executions fail."
  namespace           = "AWS/States"
  metric_name         = "ExecutionsFailed"
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"

  dimensions = {
    StateMachineArn = aws_sfn_state_machine.submission_orchestration.arn
  }
}

resource "aws_cloudwatch_metric_alarm" "kb_coordinator_errors" {
  alarm_name          = "${local.resource_prefix}-kb-coordinator-errors"
  alarm_description   = "Alerts when the KB coordinator Lambda returns invocation errors."
  namespace           = "AWS/Lambda"
  metric_name         = "Errors"
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"

  dimensions = {
    FunctionName = aws_lambda_function.kb_coordinator.function_name
  }
}

resource "aws_cloudwatch_metric_alarm" "documents_stuck_ingesting" {
  alarm_name          = "${local.resource_prefix}-documents-stuck-ingesting"
  alarm_description   = "Alerts when documents remain in INGESTING beyond the configured threshold."
  namespace           = "MDIP/Operations"
  metric_name         = "DocumentsStuckInIngesting"
  statistic           = "Maximum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"

  dimensions = {
    Environment = var.environment
  }
}

resource "aws_cloudwatch_metric_alarm" "submissions_stuck_non_terminal" {
  alarm_name          = "${local.resource_prefix}-submissions-stuck-non-terminal"
  alarm_description   = "Alerts when submissions remain in RECEIVING, COMPLETE, or WAITING_FOR_INDEX beyond the configured threshold."
  namespace           = "MDIP/Operations"
  metric_name         = "SubmissionsStuckNonTerminal"
  statistic           = "Maximum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"

  dimensions = {
    Environment = var.environment
  }
}

resource "aws_cloudwatch_dashboard" "operations" {
  dashboard_name = "${local.resource_prefix}-operations"

  dashboard_body = jsonencode({
    widgets = [
      {
        "type"   = "text"
        "x"      = 0
        "y"      = 0
        "width"  = 24
        "height" = 1
        "properties" = {
          "markdown" = "# ${local.resource_prefix} Operations"
        }
      },
      {
        "type"   = "metric"
        "x"      = 0
        "y"      = 1
        "width"  = 12
        "height" = 6
        "properties" = {
          "region" = var.aws_region
          "title"  = "Submissions By Status"
          "view"   = "timeSeries"
          "stat"   = "Maximum"
          "period" = 300
          "metrics" = [
            ["MDIP/Operations", "SubmissionCount", "Environment", var.environment, "Status", "RECEIVING", { "label" = "RECEIVING" }],
            [".", "SubmissionCount", ".", ".", "Status", "COMPLETE", { "label" = "COMPLETE" }],
            [".", "SubmissionCount", ".", ".", "Status", "WAITING_FOR_INDEX", { "label" = "WAITING_FOR_INDEX" }],
            [".", "SubmissionCount", ".", ".", "Status", "READY", { "label" = "READY" }],
            [".", "SubmissionCount", ".", ".", "Status", "FAILED", { "label" = "FAILED" }]
          ]
        }
      },
      {
        "type"   = "metric"
        "x"      = 12
        "y"      = 1
        "width"  = 12
        "height" = 6
        "properties" = {
          "region" = var.aws_region
          "title"  = "Ingestion Runs By Status"
          "view"   = "timeSeries"
          "stat"   = "Maximum"
          "period" = 300
          "metrics" = [
            ["MDIP/Operations", "IngestionRunCount", "Environment", var.environment, "Status", "STARTED", { "label" = "STARTED" }],
            [".", "IngestionRunCount", ".", ".", "Status", "SUCCEEDED", { "label" = "SUCCEEDED" }],
            [".", "IngestionRunCount", ".", ".", "Status", "FAILED", { "label" = "FAILED" }]
          ]
        }
      },
      {
        "type"   = "metric"
        "x"      = 0
        "y"      = 7
        "width"  = 12
        "height" = 6
        "properties" = {
          "region" = var.aws_region
          "title"  = "Callback Failures And Manual Review Queue"
          "view"   = "timeSeries"
          "stat"   = "Maximum"
          "period" = 300
          "metrics" = [
            ["MDIP/Operations", "CallbackFailureCount", "Environment", var.environment, { "label" = "Callback Failures" }],
            ["AWS/SQS", "ApproximateNumberOfMessagesVisible", "QueueName", aws_sqs_queue.manual_review.name, { "label" = "Manual Review Queue Visible" }]
          ]
        }
      },
      {
        "type"   = "metric"
        "x"      = 12
        "y"      = 7
        "width"  = 12
        "height" = 6
        "properties" = {
          "region" = var.aws_region
          "title"  = "Stuck Pipeline Items"
          "view"   = "timeSeries"
          "stat"   = "Maximum"
          "period" = 300
          "metrics" = [
            ["MDIP/Operations", "DocumentsStuckInIngesting", "Environment", var.environment, { "label" = "Documents Stuck Ingesting" }],
            [".", "SubmissionsStuckNonTerminal", ".", ".", { "label" = "Submissions Stuck Non-Terminal" }],
            [".", "ManualReviewItemsQueued", ".", ".", { "label" = "Manual Review Items Queued" }]
          ]
        }
      }
    ]
  })
}
