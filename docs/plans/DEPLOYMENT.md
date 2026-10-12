# Deployment Plan — Docker on a GCP VM

How Techlead reaches production: GitHub Actions builds the Docker images, pushes them to Artifact Registry, and
rolls them out on a single Compute Engine VM with Docker Compose. One VM keeps it cheap and easy to reason about;
moving to Cloud Run or GKE later reuses the same images.

```
push to main ──► CI (ruff, mypy, pytest, frontend build, docker build)
                  │ success
                  ▼
                 Deploy (.github/workflows/deploy.yml)
                  1. log in to GCP (Workload Identity Federation, no JSON key)
                  2. build backend / worker / frontend images, tag = commit SHA
                  3. push to <region>-docker.pkg.dev/<project>/techlead
                  4. IAP SSH to the VM: copy compose.prod.yaml + nginx.conf, compose pull, up -d
                  5. smoke test: GET http://localhost/api/v1/health on the VM
```

---

# 1. Runtime Layout on the VM

```
/opt/techlead/
├── compose.prod.yaml   copied by every deploy
├── nginx.conf          copied by every deploy (ops/nginx/nginx.conf)
└── .env                created once by hand; never in Git or GitHub
```

| Service  | Image                      | Exposed       | Notes                                              |
|----------|----------------------------|---------------|----------------------------------------------------|
| nginx    | nginx:1.27-alpine          | :80 (public)  | `/api/` → backend, everything else → frontend      |
| backend  | `techlead/backend:<sha>`   | internal only | Dockerfile target `api`, no CrewAI                 |
| worker   | `techlead/worker:<sha>`    | none          | Dockerfile target `worker`, runs AI analysis jobs  |
| frontend | `techlead/frontend:<sha>`  | internal only | Vite dev server for now (see §6)                   |

Every service has `restart: unless-stopped`, so the stack comes back after a VM reboot.

---

# 2. One-Time GCP Setup

```bash
PROJECT=<project-id> REGION=<region> GH=MedviJenka/techlead

# Image registry
gcloud artifacts repositories create techlead --repository-format=docker --location=$REGION

# Deploy identity used by GitHub Actions
gcloud iam service-accounts create gh-deployer
SA=gh-deployer@$PROJECT.iam.gserviceaccount.com
for role in artifactregistry.writer compute.instanceAdmin.v1 iap.tunnelResourceAccessor iam.serviceAccountUser; do
  gcloud projects add-iam-policy-binding $PROJECT --member=serviceAccount:$SA --role=roles/$role
done

# Workload Identity Federation: only this repository may impersonate gh-deployer
gcloud iam workload-identity-pools create github --location=global
gcloud iam workload-identity-pools providers create-oidc github --location=global \
  --workload-identity-pool=github --issuer-uri=https://token.actions.githubusercontent.com \
  --attribute-mapping=google.subject=assertion.sub,attribute.repository=assertion.repository \
  --attribute-condition="assertion.repository=='$GH'"
POOL=$(gcloud iam workload-identity-pools describe github --location=global --format='value(name)')
gcloud iam service-accounts add-iam-policy-binding $SA --role=roles/iam.workloadIdentityUser \
  --member="principalSet://iam.googleapis.com/$POOL/attribute.repository/$GH"

# SSH only through IAP; port 22 is not open to the internet
gcloud compute firewall-rules create allow-iap-ssh --allow=tcp:22 --source-ranges=35.235.240.0/20
```

---

# 3. One-Time VM Setup

1. Install Docker Engine with the compose plugin.
2. Grant the VM's own service account `roles/artifactregistry.reader`.
3. `gcloud auth configure-docker <region>-docker.pkg.dev` (as the user the deploy SSHes in as).
4. `sudo mkdir -p /opt/techlead && sudo chown $USER /opt/techlead`.
5. Create `/opt/techlead/.env` from the production values:
   * `OPENAI_API_KEY`, `OPENAI_MODEL` (gpt-5.5 for lead analysis)
   * `SUPABASE_PROJECT_URL`, `SUPABASE_SECRET_KEY`, `SUPABASE_PUBLISHABLE_KEY`
   * `CORS_ORIGINS` set to the VM's public address or domain
   * WhatsApp settings when the channel is live
6. Allow inbound HTTP (tcp:80) to the VM.

---

# 4. GitHub Configuration

Repository **variables** (none of these are secrets):

| Variable           | Example                                                                         |
|--------------------|---------------------------------------------------------------------------------|
| `GCP_PROJECT`      | `techlead-prod`                                                                 |
| `GCP_REGION`       | `europe-west1`                                                                  |
| `GCP_ZONE`         | `europe-west1-b`                                                                |
| `GCP_VM`           | `techlead-vm`                                                                   |
| `GCP_DEPLOY_SA`    | `gh-deployer@techlead-prod.iam.gserviceaccount.com`                             |
| `GCP_WIF_PROVIDER` | `projects/<number>/locations/global/workloadIdentityPools/github/providers/github` |

Create a `production` environment (Settings → Environments). Adding required reviewers there turns every
deploy into a manual approval.

---

# 5. Operating It

* **Deploy:** merge to `main`; the deploy starts when CI succeeds. Manual: Actions → Deploy → Run workflow.
* **Rollback:** images are tagged by commit SHA. On the VM:
  `REGISTRY=... TAG=<previous sha> docker compose -f compose.prod.yaml up -d`.
* **Logs:** `docker compose -f compose.prod.yaml logs -f backend worker`.
* **Database migrations:** `db/*.sql` are applied by hand in the Supabase SQL editor *before* merging code that
  depends on them. Deploys never change the schema.
* **Concurrency:** only one deploy runs at a time (`concurrency: deploy-production`).

---

# 6. Known Gaps (next steps)

1. **Production frontend image** — `frontend/Dockerfile` runs the Vite dev server. Replace with a multi-stage build
   (`npm run build` → static files served by nginx) and drop the frontend container.
2. **HTTPS** — put the VM behind a domain with TLS (Caddy/certbot, or a Google HTTPS load balancer).
3. **Zero-downtime** — `up -d` restarts containers in place, so a deploy has a few seconds of downtime.
4. **Image cleanup** — add an Artifact Registry cleanup policy (keep the last ~10 tags).
5. **Migrations in the pipeline** — once there is a migration tool, run it as a deploy step before `up -d`.
