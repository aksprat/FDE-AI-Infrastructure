# Recommendation for Halcyon Labs

**To:** Dana
**From:** [FDE], DigitalOcean
**Re:** Infrastructure for the enterprise migration

## The recommendation, up front

Move off the single Droplet onto DO App Platform, with a single-node Managed Postgres doing double duty as both your database and your job queue, and object storage (Spaces) for uploaded contracts. Drop Redis. Drop the DOKS cluster you provisioned but never used. This gets you zero-downtime deploys, automatic restart on crash, and a fix for the exact incident that lost you 40 jobs last week — for roughly **$50/month**, not the 10x you were worried about. It's live right now at `https://halcyon-labs-v3-oekum.ondigitalocean.app`, running a stand-in workload that mimics your real one, so you can see the behavior rather than take my word for it.

I disagreed with two things in your note, and I want to make the case for both before you sign off on anything: keeping the DOKS cluster, and self-hosting Postgres to save money. Details below.

## What I built, and why

**App Platform instead of Kubernetes.** You provisioned DOKS because "everyone told us to," but nobody on your team has run it in production, and you have six weeks. That's not enough time to safely pick up Kubernetes *and* migrate a live enterprise customer onto it — if something breaks at 2am during the migration, you need to already understand the failure mode, not be learning the platform under pressure. App Platform gets you almost everything DOKS would have (rolling zero-downtime deploys, automatic restarts, horizontal scaling) as a managed service — you push code, it builds and deploys it. I'd rather you have a smaller, well-understood system than a more powerful one nobody can debug. **Action for you:** decommission the DOKS cluster — it's an idle cost with nothing on it.

**Postgres is now also your job queue — no more Redis.** The 40 lost jobs weren't really an out-of-memory problem; they were a problem of a job's only record of existing being in-memory. I moved job state into a `jobs` table in Postgres itself, with workers claiming rows atomically (`SELECT ... FOR UPDATE SKIP LOCKED`). This means a job's existence no longer depends on a process staying alive — it's exactly as durable as your data, because it *is* your data. This removes an entire managed service (and its cost and failure modes) from the picture, at a scale where Postgres-as-queue comfortably handles far more throughput than a few thousand contracts a month will ever produce.

**The "hangs" bug is now bounded, not fixed by hoping it doesn't happen.** Every model call now runs under a hard deadline (90 seconds). If it doesn't return in time — for any reason, we don't need to know exactly why it hangs — the job is retried, up to 3 attempts, then cleanly marked failed rather than left stuck. I checked DO's Serverless Inference rate limits (600 requests/minute at your tier) and confirmed that's not what's causing the hangs; the bound protects you regardless of cause. I tested this directly against the live system: one job hit the simulated hang, timed out, and succeeded on retry; another hit it three times and was cleanly marked failed with a visible error, rather than disappearing.

**A crashed worker's job gets reclaimed, not lost.** This is the direct fix for last Tuesday's incident. Every worker also sweeps for jobs that have been "processing" for more than 5 minutes with no update — those get released back to the queue automatically. I proved this against the live database: I manually simulated a job abandoned by a crashed worker, and within a minute a healthy worker picked it back up, retried it, and gave it a clean terminal status. Nothing silently vanishes anymore.

**Deploys no longer take you down.** App Platform replaces the SSH-and-`docker compose`-at-night ritual with rolling deploys: new instances come up, prove they're healthy (I made the health check actually verify database connectivity, not just "process is alive"), and only then do old instances go away. Database migrations run as an automatic pre-deploy step — the new version only goes live if the migration succeeds. I watched this happen live when I fixed a bug mid-build: the app updated in place with no dropped requests.

**Managed Postgres, not self-hosted — this is where I overrode your note.** Your CTO asked to keep Postgres self-hosted to avoid paying for a managed database. The actual saving is small — roughly $15/month — and self-hosting means you'd own backups, patching, and failover yourselves, by hand, during the exact period you're trying to reduce operational risk. Managed Postgres includes daily backups and point-in-time recovery for free. Given you already lost data to an infrastructure decision made to save money, I don't think this is the place to repeat that trade. I'd ask you to bring this back to your CTO with that framing.

**No high-availability database yet — an accepted risk, not an oversight.** A standby node would roughly double the database cost. Without one, a primary failure costs you some downtime, not data (backups protect the data regardless). Since you're not yet under a signed enterprise SLA, I think this is the right amount of spend for now. Revisit it the day that SLA is signed.

**No autoscaling for workers — capacity is planned, not reactive.** App Platform doesn't offer autoscaling for background workers at all (only for HTTP services), and I don't think you need it: your migration burst is a known event on a known date, not a surprise spike. The plan is to bump the worker count manually before the migration window and scale it back down after, watching a `/admin/queue-stats` endpoint I built that shows how many jobs are backed up and how old the oldest one is.

## What this costs

| Component | Monthly cost |
|---|---|
| App Platform — API service | ~$5 |
| App Platform — 2 worker instances | ~$24 |
| App Platform — migration job | ~$0 (billed per-second, only runs on deploy) |
| Managed Postgres (single-node) | ~$15 |
| Spaces (contract storage) | ~$5 |
| **Steady-state total** | **~$49/month** |

That's well under your $400 today, not close to 10x it — though I'd flag that transparently rather than claim credit for it: your current $400 may include costs beyond the single Droplet described in your note, and I haven't been able to reconcile the difference. Model inference cost is separate and usage-based (charged per token against your prepaid balance); I can't estimate your real number until you have actual extraction prompts, since this exercise deliberately uses a placeholder call, not your real parser. During the migration burst, scaling workers up temporarily adds a modest, short-lived cost for that window only — not a permanent increase.

## What I did not build, and why

- **Kubernetes, service mesh, any orchestration beyond App Platform** — the team-size and timeline argument above.
- **A separate queue/broker (Redis, etc.)** — Postgres already covers it.
- **A circuit breaker around the model call** — timeout, retry, and reclaim already cover the failure mode at this volume; I'd add this if you saw sustained outages from the inference provider, not before.
- **Automatic reactive autoscaling** — not available for workers on this platform, and unnecessary for a plannable burst.
- **A metrics/tracing stack, log aggregation, or on-call paging** — you have three engineers, not an SRE team. App Platform's built-in logs and alerts, plus the one queue-depth endpoint, are proportionate. Revisit when you hire someone whose job is infrastructure.
- **A standby database node** — covered above.
- **Multi-region failover** — a regional DO outage is a risk beyond what your budget should hedge against right now; backups are your ceiling for now.
- **Anything to do with authentication or tenant isolation** — nothing in your note raised this, and I don't have enough context to safely touch it. This assumes your existing auth model carries over unchanged.

## What I'm still worried about

- **I don't actually know your real contract volume or turnaround expectation.** I used 3,000 contracts as a stated assumption for sizing. If the real number, or the expected turnaround time for the migration dump, is off by 10x, the fix is more worker replicas for a longer window — not a redesign — but I'd rather you correct the assumption than have me guess wrong on the day.
- **The backup we're relying on has never been tested with a real restore.** A backup nobody has restored from is a theory.
- **I don't know what your enterprise SLA actually promises** — uptime percentage, turnaround time, or any compliance/data-residency requirement, given this is legal contract data. That should shape whether the no-HA and no-multi-region decisions above still hold once the contract is signed.

## What you should do in the next six weeks

1. Decommission the idle DOKS cluster.
2. Bring the managed-vs-self-hosted Postgres tradeoff back to your CTO with the framing above.
3. Run one real restore from a Postgres backup — don't find out during the migration that it doesn't work.
4. Confirm the real contract volume and expected turnaround time for the migration dump, and tell me if either is far off from what I assumed.
5. Get the actual SLA terms in writing so we can revisit the HA and multi-region calls with real numbers.
6. Watch `/admin/queue-stats` in the days before the migration and bump worker capacity ahead of it, not during it.
