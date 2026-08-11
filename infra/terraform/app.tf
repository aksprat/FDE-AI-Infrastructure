# DO App Platform (decision #1: walked away from the pre-provisioned DOKS
# cluster — a team with no infra person and a six-week deadline shouldn't be
# upskilling on Kubernetes at the same time). Rolling deploys, health-checked
# restarts, and a managed TLS/ingress replace the SSH+docker-compose ritual
# with zero custom tooling.

locals {
  app_source_dir = "app"
}

resource "digitalocean_app" "halcyon" {
  spec {
    name   = "halcyon-labs"
    region = var.region

    # DEPLOYMENT_FAILED is only a valid rule at the app level, not inside a
    # service/worker component's alert block (decision #7 — this is the
    # native alert we rely on instead of building custom monitoring).
    alert {
      rule = "DEPLOYMENT_FAILED"
      destinations {
        emails = [var.alert_email]
      }
    }

    # Binds the externally-managed cluster from database.tf as an app
    # component, which is what exposes the ${db.DATABASE_URL} bindable
    # variable referenced by every component below.
    database {
      name         = "db"
      engine       = "PG"
      production   = true
      cluster_name = digitalocean_database_cluster.postgres.name
      db_name      = digitalocean_database_db.app.name
      db_user      = digitalocean_database_user.app.name
    }

    # Pre-deploy migration job (decision #6): the new version only goes live
    # if this exits 0. Replaces "SSH in and run it by hand."
    job {
      name               = "migrate"
      kind               = "PRE_DEPLOY"
      instance_count     = 1
      instance_size_slug = "apps-s-1vcpu-0.5gb"
      source_dir         = local.app_source_dir
      run_command        = "python migrate.py"

      github {
        repo           = var.github_repo
        branch         = var.github_branch
        deploy_on_push = false
      }

      env {
        key   = "DATABASE_URL"
        value = "$${db.DATABASE_URL}"
        scope = "RUN_TIME"
        type  = "SECRET"
      }
    }

    # API service. Native git-push-to-deploy (decision #6) — no custom
    # CI/CD pipeline; fewest new concepts for a 3-person team.
    service {
      name               = "api"
      instance_count     = 1
      instance_size_slug = "apps-s-1vcpu-0.5gb"
      http_port          = 8080
      source_dir         = local.app_source_dir
      run_command        = "uvicorn api:app --host 0.0.0.0 --port 8080"

      github {
        repo           = var.github_repo
        branch         = var.github_branch
        deploy_on_push = true
      }

      # Checks real DB connectivity (decision #6) — App Platform only cuts
      # traffic over to a new instance, and only kills the old one, once
      # this passes. A shallow 200 would make the zero-downtime story fake.
      health_check {
        http_path             = "/health"
        initial_delay_seconds = 10
        period_seconds        = 10
        timeout_seconds       = 5
        success_threshold     = 1
        failure_threshold     = 3
      }

      env {
        key   = "DATABASE_URL"
        value = "$${db.DATABASE_URL}"
        scope = "RUN_TIME"
        type  = "SECRET"
      }
      env {
        key   = "SPACES_ENDPOINT"
        value = "https://${var.region}.digitaloceanspaces.com"
      }
      env {
        key   = "SPACES_REGION"
        value = var.region
      }
      env {
        key   = "SPACES_BUCKET"
        value = aws_s3_bucket.uploads.bucket
      }
      env {
        key   = "SPACES_ACCESS_KEY"
        value = digitalocean_spaces_key.app.access_key
        type  = "SECRET"
      }
      env {
        key   = "SPACES_SECRET_KEY"
        value = digitalocean_spaces_key.app.secret_key
        type  = "SECRET"
      }

    }

    # Background worker (decisions #3, #4, #5). No autoscaling block: App
    # Platform doesn't offer it for workers, and the migration burst is a
    # known, plannable event — instance_count is bumped manually ahead of
    # it via var.worker_instance_count and scaled back down after, driven by
    # the /admin/queue-stats signal (decision #7).
    worker {
      name               = "worker"
      instance_count     = var.worker_instance_count
      instance_size_slug = "apps-s-1vcpu-0.5gb"
      source_dir         = local.app_source_dir
      run_command        = "python worker.py"

      github {
        repo           = var.github_repo
        branch         = var.github_branch
        deploy_on_push = true
      }

      env {
        key   = "DATABASE_URL"
        value = "$${db.DATABASE_URL}"
        scope = "RUN_TIME"
        type  = "SECRET"
      }
      env {
        key   = "SPACES_ENDPOINT"
        value = "https://${var.region}.digitaloceanspaces.com"
      }
      env {
        key   = "SPACES_REGION"
        value = var.region
      }
      env {
        key   = "SPACES_BUCKET"
        value = aws_s3_bucket.uploads.bucket
      }
      env {
        key   = "SPACES_ACCESS_KEY"
        value = digitalocean_spaces_key.app.access_key
        type  = "SECRET"
      }
      env {
        key   = "SPACES_SECRET_KEY"
        value = digitalocean_spaces_key.app.secret_key
        type  = "SECRET"
      }
      env {
        key   = "INFERENCE_API_KEY"
        value = var.inference_api_key
        type  = "SECRET"
      }
      env {
        key   = "INFERENCE_MODEL"
        value = var.inference_model
      }

      # 400s comfortably covers the worst case a job can take (up to 240s
      # simulated processing + up to 90s model-call deadline) so a deploy's
      # SIGTERM lets an in-flight job finish rather than relying on the
      # lease-reclaim sweep as the routine path (decision #6).
      termination {
        grace_period_seconds = 400
      }
    }
  }
}
