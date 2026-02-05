# Monitoring Module Variables

variable "project_name" {
  description = "Name of the project"
  type        = string
}

variable "environment" {
  description = "Environment name"
  type        = string
}

variable "alert_email" {
  description = "Email address for CloudWatch alarms"
  type        = string
}

variable "lambda_function_names" {
  description = "Map of Lambda function names to monitor"
  type        = map(string)
}

variable "api_gateway_id" {
  description = "ID of the API Gateway to monitor"
  type        = string
}

# websocket_api_id - REMOVED (2026-02) - WebSocket deprecated
variable "websocket_api_id" {
  description = "DEPRECATED: ID of the WebSocket API Gateway to monitor"
  type        = string
  default     = ""
}

variable "common_tags" {
  description = "Common tags to apply to all resources"
  type        = map(string)
  default     = {}
}