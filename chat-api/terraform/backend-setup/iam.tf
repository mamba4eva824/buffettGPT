# IAM Roles and Policies for Terraform State Management
# Provides granular access control for different team roles

# Data source for current AWS account
data "aws_iam_policy_document" "terraform_state_assume_role" {
  statement {
    effect = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "AWS"
      identifiers = ["arn:aws:iam::${data.aws_caller_identity.current.account_id}:root"]
    }

    condition {
      test     = "Bool"
      variable = "aws:MultiFactorAuthPresent"
      values   = ["true"]
    }
  }
}

# Terraform Admin Role - Full access to state and infrastructure
resource "aws_iam_role" "terraform_admin" {
  name               = "${var.project_name}-terraform-admin"
  assume_role_policy = data.aws_iam_policy_document.terraform_state_assume_role.json

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-terraform-admin"
    Role = "Terraform Administrator"
  })
}

# Terraform Developer Role - Read/write state access
resource "aws_iam_role" "terraform_developer" {
  name               = "${var.project_name}-terraform-developer"
  assume_role_policy = data.aws_iam_policy_document.terraform_state_assume_role.json

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-terraform-developer"
    Role = "Terraform Developer"
  })
}

# Terraform Read-Only Role - Read-only state access
resource "aws_iam_role" "terraform_readonly" {
  name               = "${var.project_name}-terraform-readonly"
  assume_role_policy = data.aws_iam_policy_document.terraform_state_assume_role.json

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-terraform-readonly"
    Role = "Terraform Read-Only"
  })
}

# Policy for S3 state bucket access
data "aws_iam_policy_document" "terraform_state_s3" {
  # Allow listing buckets
  statement {
    effect = "Allow"
    actions = [
      "s3:ListBucket"
    ]
    resources = [aws_s3_bucket.terraform_state.arn]
  }

  # Allow read/write access to state files
  statement {
    effect = "Allow"
    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject"
    ]
    resources = ["${aws_s3_bucket.terraform_state.arn}/*"]
  }

  # Allow KMS operations for encryption
  statement {
    effect = "Allow"
    actions = [
      "kms:Decrypt",
      "kms:GenerateDataKey"
    ]
    resources = [aws_kms_key.terraform_state.arn]
  }
}

# Policy for S3 read-only access
data "aws_iam_policy_document" "terraform_state_s3_readonly" {
  # Allow listing buckets
  statement {
    effect = "Allow"
    actions = [
      "s3:ListBucket"
    ]
    resources = [aws_s3_bucket.terraform_state.arn]
  }

  # Allow read-only access to state files
  statement {
    effect = "Allow"
    actions = [
      "s3:GetObject"
    ]
    resources = ["${aws_s3_bucket.terraform_state.arn}/*"]
  }

  # Allow KMS decryption
  statement {
    effect = "Allow"
    actions = [
      "kms:Decrypt"
    ]
    resources = [aws_kms_key.terraform_state.arn]
  }
}

# Policy for DynamoDB state locking
data "aws_iam_policy_document" "terraform_state_dynamodb" {
  statement {
    effect = "Allow"
    actions = [
      "dynamodb:GetItem",
      "dynamodb:PutItem",
      "dynamodb:DeleteItem"
    ]
    resources = [aws_dynamodb_table.terraform_state_locks.arn]
  }
}

# Policy for DynamoDB read-only
data "aws_iam_policy_document" "terraform_state_dynamodb_readonly" {
  statement {
    effect = "Allow"
    actions = [
      "dynamodb:GetItem"
    ]
    resources = [aws_dynamodb_table.terraform_state_locks.arn]
  }
}

# IAM Policies
resource "aws_iam_policy" "terraform_state_s3" {
  name   = "${var.project_name}-terraform-state-s3"
  policy = data.aws_iam_policy_document.terraform_state_s3.json

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-terraform-state-s3"
  })
}

resource "aws_iam_policy" "terraform_state_s3_readonly" {
  name   = "${var.project_name}-terraform-state-s3-readonly"
  policy = data.aws_iam_policy_document.terraform_state_s3_readonly.json

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-terraform-state-s3-readonly"
  })
}

resource "aws_iam_policy" "terraform_state_dynamodb" {
  name   = "${var.project_name}-terraform-state-dynamodb"
  policy = data.aws_iam_policy_document.terraform_state_dynamodb.json

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-terraform-state-dynamodb"
  })
}

resource "aws_iam_policy" "terraform_state_dynamodb_readonly" {
  name   = "${var.project_name}-terraform-state-dynamodb-readonly"
  policy = data.aws_iam_policy_document.terraform_state_dynamodb_readonly.json

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-terraform-state-dynamodb-readonly"
  })
}

# Policy Attachments - Admin Role
resource "aws_iam_role_policy_attachment" "terraform_admin_s3" {
  role       = aws_iam_role.terraform_admin.name
  policy_arn = aws_iam_policy.terraform_state_s3.arn
}

resource "aws_iam_role_policy_attachment" "terraform_admin_dynamodb" {
  role       = aws_iam_role.terraform_admin.name
  policy_arn = aws_iam_policy.terraform_state_dynamodb.arn
}

# Policy Attachments - Developer Role
resource "aws_iam_role_policy_attachment" "terraform_developer_s3" {
  role       = aws_iam_role.terraform_developer.name
  policy_arn = aws_iam_policy.terraform_state_s3.arn
}

resource "aws_iam_role_policy_attachment" "terraform_developer_dynamodb" {
  role       = aws_iam_role.terraform_developer.name
  policy_arn = aws_iam_policy.terraform_state_dynamodb.arn
}

# Policy Attachments - Read-Only Role
resource "aws_iam_role_policy_attachment" "terraform_readonly_s3" {
  role       = aws_iam_role.terraform_readonly.name
  policy_arn = aws_iam_policy.terraform_state_s3_readonly.arn
}

resource "aws_iam_role_policy_attachment" "terraform_readonly_dynamodb" {
  role       = aws_iam_role.terraform_readonly.name
  policy_arn = aws_iam_policy.terraform_state_dynamodb_readonly.arn
}