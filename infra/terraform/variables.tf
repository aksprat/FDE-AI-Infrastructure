variable "do_token" {
  description = "DigitalOcean API token"
  type        = string
  sensitive   = true
}

variable "region" {
  description = "DigitalOcean region"
  type        = string
  default     = "nyc3"
}

variable "github_repo" {
  description = "owner/repo that App Platform builds and deploys from"
  type        = string
}

variable "github_branch" {
  description = "Branch App Platform deploys from"
  type        = string
  default     = "main"
}

variable "inference_api_key" {
  description = "API key for DO Serverless Inference (https://inference.do-ai.run)"
  type        = string
  sensitive   = true
}

variable "inference_model" {
  description = "Model name to call against DO Serverless Inference"
  type        = string
  default     = "llama3.3-70b-instruct"
}

variable "alert_email" {
  description = "Email address for App Platform's built-in alerts (decision #7 — no custom observability stack)"
  type        = string
}

variable "worker_instance_count" {
  description = "Worker replica count. Bumped manually ahead of a known bulk migration and scaled back down after (decision #5 — worker autoscaling isn't available on App Platform, and this burst is plannable, not reactive)."
  type        = number
  default     = 2
}
