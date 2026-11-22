# Deployment

The reference setup is one VM and one small Cloud Run service. It is meant to be cheap and simple, not highly available.

```
Browser ──HTTPS──► Cloud Run "front door" (Caddy)  ──Direct VPC egress──►  VM :8000
                                                                           ├─ api
                                                                           ├─ worker
                                                                           └─ postgres (container)
```

- **VM** (Compute Engine): runs [`docker-compose.prod.yml`](docker-compose.prod.yml): a one-shot `migrate` service, `api`, `worker` and Postgres. Data lives in `./data` and the Postgres volume.
- **Front door** ([`frontdoor/`](frontdoor/)): a stateless Caddy proxy on Cloud Run that gives the app a public HTTPS URL without a domain. The app itself cannot run on Cloud Run because the worker is always on and shares disk with the API.
- **Images**: built by [`../cloudbuild.yaml`](../cloudbuild.yaml) and pushed to Artifact Registry, tagged with the git SHA.

## First-time setup

1. Create the VM and an Artifact Registry repository, and note the Cloud Run front door URL you will use.
2. On the VM, copy [`.env.prod.example`](.env.prod.example) to `.env` (mode 600) and fill it in. Generate secrets with `openssl rand -hex 32`.
3. Put the GitHub App private key at `secrets/app.pem` if you use the GitHub App.
4. Deploy the front door from `frontdoor/` with its Dockerfile.

## Deploy a new version

```bash
gcloud builds submit                  # from the repository root: builds and pushes the image
./deploy.sh <git-sha>                 # on the VM: pulls that tag, runs migrations, restarts, checks /readyz
```

`./deploy.sh` with no argument redeploys the image named in `.env`.

## Backups

[`backup.sh`](backup.sh) dumps the Postgres database. Run it from cron on the VM and copy the output off the machine.

## Public demo mode

Setting `PUBLIC_VIEWER=true` and `DEV_VIEWER_LOGIN=<name>` lets anyone with the URL view every analysis without GitHub login. Use it only when nothing in the database is sensitive.

## Static site

The read-only demo on GitHub Pages needs none of this. See [web/README.md](../web/README.md#static-demo-github-pages).
