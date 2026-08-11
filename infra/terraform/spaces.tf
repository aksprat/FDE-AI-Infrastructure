# Object storage for uploaded contracts (decision #9). App Platform
# instances are ephemeral — this is the durable home for uploads, not local
# disk on a compute instance.
resource "digitalocean_spaces_bucket" "uploads" {
  name   = "halcyon-contract-uploads"
  region = var.region
  # No explicit acl: DO Spaces buckets are private by default, and setting
  # acl explicitly triggers a PutBucketAcl call that DO Spaces' S3-compatible
  # API returns 501 Not Implemented for.
}

resource "digitalocean_spaces_key" "app" {
  name = "halcyon-app-spaces-key"

  grant {
    bucket     = digitalocean_spaces_bucket.uploads.name
    permission = "readwrite"
  }
}
