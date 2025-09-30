bucket         = "buffett-chat-terraform-state-430118826061"
key            = "staging/terraform.tfstate"
region         = "us-east-1"
encrypt        = true
kms_key_id     = "arn:aws:kms:us-east-1:430118826061:key/d964f8d5-fe43-45c3-9193-3fe8a7d6e12b"
dynamodb_table = "buffett-chat-terraform-state-locks"