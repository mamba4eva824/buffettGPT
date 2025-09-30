# Variables for the complete example

variable "pinecone_api_key" {
  description = "Pinecone API key (pass via tfvars or environment variable)"
  type        = string
  sensitive   = true
}