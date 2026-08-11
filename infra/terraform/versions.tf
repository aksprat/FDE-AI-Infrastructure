terraform {
  required_version = ">= 1.5"
  required_providers {
    digitalocean = {
      source  = "digitalocean/digitalocean"
      version = "~> 2.27"
    }
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "digitalocean" {
  token = var.do_token

  # Spaces resources talk to the S3-compatible endpoint, not DO's v2 API, so
  # they need their own credential pair (account-level Spaces access keys),
  # separate from the do_token used for everything else.
  spaces_access_id  = var.spaces_access_id
  spaces_secret_key = var.spaces_secret_key
}

# Used only for aws_s3_bucket (see spaces.tf) — pointed at DO's
# S3-compatible endpoint, not real AWS. The region/account-id skips are
# required because this isn't a real AWS account and DO doesn't implement
# the endpoints the provider would otherwise use to validate them.
provider "aws" {
  region                      = "us-east-1"
  access_key                  = var.spaces_access_id
  secret_key                  = var.spaces_secret_key
  skip_credentials_validation = true
  skip_region_validation      = true
  skip_requesting_account_id  = true

  endpoints {
    s3 = "https://${var.region}.digitaloceanspaces.com"
  }
}
