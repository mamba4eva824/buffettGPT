# S3 Module Outputs

output "models_bucket_name" {
  description = "Name of the S3 bucket for ML models"
  value       = aws_s3_bucket.models.bucket
}

output "models_bucket_arn" {
  description = "ARN of the S3 bucket for ML models"
  value       = aws_s3_bucket.models.arn
}

output "models_bucket_id" {
  description = "ID of the S3 bucket for ML models"
  value       = aws_s3_bucket.models.id
}
