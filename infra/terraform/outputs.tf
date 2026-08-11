output "app_url" {
  description = "Live URL of the deployed app"
  value       = digitalocean_app.halcyon.live_url
}

output "app_id" {
  value = digitalocean_app.halcyon.id
}

output "database_connection_uri" {
  description = "Postgres connection URI (for manual psql access, e.g. to inspect the jobs table during the demo)"
  value       = digitalocean_database_cluster.postgres.uri
  sensitive   = true
}

output "spaces_bucket" {
  value = aws_s3_bucket.uploads.bucket
}
