terraform {
  required_version = ">= 1.5"
  required_providers {
    digitalocean = {
      source  = "digitalocean/digitalocean"
      version = "~> 2.27"
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
