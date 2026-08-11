# Object storage for uploaded contracts (decision #9). App Platform
# instances are ephemeral — this is the durable home for uploads, not local
# disk on a compute instance.
#
# Bucket creation deliberately goes through the AWS provider, not
# digitalocean_spaces_bucket: DO Spaces' S3-compatible API returns
# 501 Not Implemented for PutBucketAcl, and the native resource issues that
# call unconditionally on creation regardless of whether `acl` is set,
# making it unusable for creating new buckets right now. aws_s3_bucket
# doesn't touch ACLs unless a separate aws_s3_bucket_acl resource is added,
# so it never hits the broken call. This is a documented, common workaround
# for DO Spaces + Terraform.
resource "aws_s3_bucket" "uploads" {
  bucket = "halcyon-contract-uploads"
}

resource "digitalocean_spaces_key" "app" {
  name = "halcyon-app-spaces-key"

  grant {
    bucket     = aws_s3_bucket.uploads.bucket
    permission = "readwrite"
  }
}
