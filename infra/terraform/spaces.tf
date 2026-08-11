# Object storage for uploaded contracts (decision #9). App Platform
# instances are ephemeral — this is the durable home for uploads, not local
# disk on a compute instance.
resource "digitalocean_spaces_bucket" "uploads" {
  name   = "halcyon-contract-uploads"
  region = var.region
  acl    = "private"
}

resource "digitalocean_spaces_key" "app" {
  name = "halcyon-app-spaces-key"

  grant {
    bucket     = digitalocean_spaces_bucket.uploads.name
    permission = "readwrite"
  }
}
