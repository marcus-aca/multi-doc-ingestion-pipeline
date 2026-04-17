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

  knowledge_base_arn = var.knowledge_base_id != "" ? "arn:aws:bedrock:${var.aws_region}:${data.aws_caller_identity.current.account_id}:knowledge-base/${var.knowledge_base_id}" : "*"

  sonnet_model_arn = "arn:aws:bedrock:${var.aws_region}::foundation-model/${var.sonnet_model_id}"

  lambda_log_groups = {
    upload_event_handler = "/aws/lambda/${local.resource_prefix}-upload-event-handler"
    preprocessor         = "/aws/lambda/${local.resource_prefix}-preprocessor"
    kb_coordinator       = "/aws/lambda/${local.resource_prefix}-kb-coordinator"
    query_api            = "/aws/lambda/${local.resource_prefix}-query-api"
    completion_trigger   = "/aws/lambda/${local.resource_prefix}-completion-trigger"
    submission_validator = "/aws/lambda/${local.resource_prefix}-submission-validator"
    raw_file_resolver    = "/aws/lambda/${local.resource_prefix}-raw-file-resolver"
  }
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
    canonical = "canonical/.keep"
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
    Comment = "Phase 6 submission orchestration with raw file dedupe"
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
                  Next          = "FileResolutionComplete"
                },
                {
                  Variable     = "$.rawFileCheck.resolution.rawFileStatus"
                  StringEquals = "RESOLVED"
                  Next         = "FileResolutionComplete"
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
            FileResolutionComplete = {
              Type = "Pass"
              Parameters = {
                "resolution.$" = "$.rawFileCheck.resolution"
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
        Next = "Success"
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

resource "aws_iam_role_policy_attachment" "lambda_basic_execution" {
  for_each = {
    upload_event_handler = aws_iam_role.upload_event_handler.name
    preprocessor         = aws_iam_role.preprocessor.name
    kb_coordinator       = aws_iam_role.kb_coordinator.name
    query_api            = aws_iam_role.query_api.name
    completion_trigger   = aws_iam_role.completion_trigger.name
    submission_validator = aws_iam_role.submission_validator.name
    raw_file_resolver    = aws_iam_role.raw_file_resolver.name
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
}

data "aws_iam_policy_document" "kb_coordinator" {
  statement {
    effect = "Allow"
    actions = [
      "s3:GetObject",
      "s3:ListBucket"
    ]
    resources = [
      aws_s3_bucket.documents.arn,
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
      "bedrock:IngestKnowledgeBaseDocuments",
      "bedrock:GetKnowledgeBaseDocuments",
      "bedrock:ListKnowledgeBaseDocuments",
      "bedrock:DeleteKnowledgeBaseDocuments"
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
