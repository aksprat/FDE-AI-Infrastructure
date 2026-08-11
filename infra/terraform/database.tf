# Single-node Managed Postgres (decisions #2 and #8): daily backups and
# point-in-time recovery are included at no extra cost. No standby node for
# now — an explicitly accepted availability tradeoff (data isn't at risk
# without it, some downtime on a primary failure is), to be revisited once
# the enterprise SLA is actually signed.
#
# This cluster is also the job queue (decision #3) — there is deliberately
# no separate Redis/broker to operate.
resource "digitalocean_database_cluster" "postgres" {
  name       = "halcyon-postgres"
  engine     = "pg"
  version    = "16"
  size       = "db-s-1vcpu-1gb"
  region     = var.region
  node_count = 1
}

resource "digitalocean_database_db" "app" {
  cluster_id = digitalocean_database_cluster.postgres.id
  name       = "halcyon"
}

resource "digitalocean_database_user" "app" {
  cluster_id = digitalocean_database_cluster.postgres.id
  name       = "halcyon_app"
}

# Locked down to the App Platform app itself rather than left publicly
# reachable on the internet.
resource "digitalocean_database_firewall" "postgres" {
  cluster_id = digitalocean_database_cluster.postgres.id

  rule {
    type  = "app"
    value = digitalocean_app.halcyon.id
  }
}
