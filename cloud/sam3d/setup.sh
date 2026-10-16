#!/usr/bin/env bash
# One-time Google Cloud setup for the SAM 3D jobs (README.md). Safe to run again: each step
# makes what is missing and leaves what is there. Run it signed in as the project's owner:
#
#   PROJECT=my-project GITHUB_REPO=owner/name cloud/sam3d/setup.sh
#
# Optional: REGION (us-central1: it has L4 GPUs), GPU_TYPE (nvidia-l4).
#
# Nothing it makes has a key, a public address or a project-wide role:
#   sam3d-fetch   a CPU job; reads the Hugging Face token, writes the weights bucket
#   sam3d-run     the GPU job; reads the weights bucket, reads and writes the work bucket,
#                 and has no route to the internet (its own network, Google APIs only)
#   sam3d-deploy  what GitHub Actions becomes: pushes to one registry, updates the two jobs
set -euo pipefail

: "${PROJECT:?set PROJECT to your Google Cloud project ID}"
: "${GITHUB_REPO:?set GITHUB_REPO to owner/name of the GitHub repository}"
REGION="${REGION:-us-central1}"
GPU_TYPE="${GPU_TYPE:-nvidia-l4}"
ENVIRONMENT=sam3d
WORKFLOW=.github/workflows/sam3d.yml
WEIGHTS="$PROJECT-sam3d-weights"
WORK="$PROJECT-sam3d-work"
REPO=sam3d
POOL=github
PROVIDER=sam3d
SECRET=hf-token
# Google's public sample job: a placeholder until the first GitHub build replaces it.
PLACEHOLDER=us-docker.pkg.dev/cloudrun/container/job:latest

g() { gcloud --project "$PROJECT" --quiet "$@"; }
exists() { g "$@" >/dev/null 2>&1; }
say() { printf '\n== %s\n' "$*"; }
sa() { echo "$1@$PROJECT.iam.gserviceaccount.com"; }

NUMBER=$(g projects describe "$PROJECT" --format='value(projectNumber)')
IDS=$(curl -fsS "https://api.github.com/repos/$GITHUB_REPO")
REPO_ID=$(python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])' <<<"$IDS")
OWNER_ID=$(python3 -c 'import json,sys; print(json.load(sys.stdin)["owner"]["id"])' <<<"$IDS")

say "APIs"
g services enable run.googleapis.com artifactregistry.googleapis.com iam.googleapis.com \
  iamcredentials.googleapis.com sts.googleapis.com secretmanager.googleapis.com \
  compute.googleapis.com storage.googleapis.com

say "Registry: $REPO, keeping the two newest images (storage is paid per GB)"
exists artifacts repositories describe "$REPO" --location "$REGION" ||
  g artifacts repositories create "$REPO" --location "$REGION" --repository-format docker \
    --immutable-tags --description "SAM 3D container"
cat >/tmp/sam3d-cleanup.json <<'EOF'
[
  {"name": "keep-two", "action": {"type": "Keep"}, "mostRecentVersions": {"keepCount": 2}},
  {"name": "delete-rest", "action": {"type": "Delete"}, "condition": {"tagState": "ANY"}}
]
EOF
g artifacts repositories set-cleanup-policies "$REPO" --location "$REGION" \
  --policy /tmp/sam3d-cleanup.json --no-dry-run
rm /tmp/sam3d-cleanup.json

say "Buckets: $WEIGHTS (the models), $WORK (jobs, deleted after 7 days)"
for bucket in "$WEIGHTS" "$WORK"; do
  exists storage buckets describe "gs://$bucket" ||
    g storage buckets create "gs://$bucket" --location "$REGION" --default-storage-class STANDARD \
      --uniform-bucket-level-access --public-access-prevention --soft-delete-duration 0
done
cat >/tmp/sam3d-lifecycle.json <<'EOF'
{"rule": [{"action": {"type": "Delete"}, "condition": {"age": 7}}]}
EOF
g storage buckets update "gs://$WORK" --lifecycle-file /tmp/sam3d-lifecycle.json
rm /tmp/sam3d-lifecycle.json

say "Secret: $SECRET (its value is added by you, never by this script)"
exists secrets describe "$SECRET" ||
  g secrets create "$SECRET" --replication-policy user-managed --locations "$REGION"

if [ -z "$(g secrets versions list "$SECRET" --limit 1 --format 'value(name)')" ]; then
  echo "The Hugging Face token is not there yet. In your own terminal (not a chat), run"
  echo "  gcloud secrets versions add $SECRET --project $PROJECT --data-file=-"
  echo "paste the token, press Enter, then Ctrl-D. Then run this again: it carries on here."
  exit 0
fi

say "Service accounts, each with only the roles below"
for name in sam3d-fetch sam3d-run sam3d-deploy; do
  exists iam service-accounts describe "$(sa $name)" ||
    g iam service-accounts create "$name" --display-name "$name"
done
g secrets add-iam-policy-binding "$SECRET" --member "serviceAccount:$(sa sam3d-fetch)" \
  --role roles/secretmanager.secretAccessor >/dev/null
g storage buckets add-iam-policy-binding "gs://$WEIGHTS" --member "serviceAccount:$(sa sam3d-fetch)" \
  --role roles/storage.objectAdmin >/dev/null
g storage buckets add-iam-policy-binding "gs://$WEIGHTS" --member "serviceAccount:$(sa sam3d-run)" \
  --role roles/storage.objectViewer >/dev/null
g storage buckets add-iam-policy-binding "gs://$WORK" --member "serviceAccount:$(sa sam3d-run)" \
  --role roles/storage.objectUser >/dev/null
g artifacts repositories add-iam-policy-binding "$REPO" --location "$REGION" \
  --member "serviceAccount:$(sa sam3d-deploy)" --role roles/artifactregistry.writer >/dev/null
for name in sam3d-fetch sam3d-run; do
  g iam service-accounts add-iam-policy-binding "$(sa $name)" \
    --member "serviceAccount:$(sa sam3d-deploy)" --role roles/iam.serviceAccountUser >/dev/null
done

say "Network: the run job's, with Google APIs reachable and nothing else"
exists compute networks describe sam3d ||
  g compute networks create sam3d --subnet-mode custom
exists compute networks subnets describe sam3d --region "$REGION" ||
  g compute networks subnets create sam3d --network sam3d --region "$REGION" \
    --range 10.8.0.0/26 --enable-private-ip-google-access

say "Jobs (a placeholder image until GitHub builds the real one)"
if ! exists run jobs describe sam3d-fetch --region "$REGION"; then
  g run jobs create sam3d-fetch --region "$REGION" --image "$PLACEHOLDER" \
    --service-account "$(sa sam3d-fetch)" --cpu 2 --memory 4Gi --task-timeout 3600 \
    --max-retries 0 --args fetch --set-env-vars "WEIGHTS_BUCKET=$WEIGHTS" \
    --set-secrets "HF_TOKEN=$SECRET:latest"
fi
if ! exists run jobs describe sam3d-run --region "$REGION"; then
  g run jobs create sam3d-run --region "$REGION" --image "$PLACEHOLDER" \
    --service-account "$(sa sam3d-run)" --cpu 8 --memory 32Gi \
    --gpu 1 --gpu-type "$GPU_TYPE" --no-gpu-zonal-redundancy \
    --task-timeout 3600 --max-retries 0 \
    --network sam3d --subnet sam3d --vpc-egress all-traffic \
    --add-volume "name=weights,type=cloud-storage,bucket=$WEIGHTS,readonly=true" \
    --add-volume-mount volume=weights,mount-path=/weights \
    --add-volume "name=work,type=cloud-storage,bucket=$WORK,mount-options=uid=10001;gid=10001" \
    --add-volume-mount volume=work,mount-path=/work
fi
# Read and update the two jobs, nothing more: run.developer would also let GitHub start them.
exists iam roles describe sam3dDeploy ||
  g iam roles create sam3dDeploy --title "SAM 3D deploy" --permissions run.jobs.get,run.jobs.update
for job in sam3d-fetch sam3d-run; do
  g run jobs add-iam-policy-binding "$job" --region "$REGION" \
    --member "serviceAccount:$(sa sam3d-deploy)" --role "projects/$PROJECT/roles/sam3dDeploy" >/dev/null
done

say "GitHub sign-in: only $GITHUB_REPO's $WORKFLOW, on main, in the '$ENVIRONMENT' environment"
exists iam workload-identity-pools describe "$POOL" --location global ||
  g iam workload-identity-pools create "$POOL" --location global --display-name "GitHub Actions"
CONDITION="assertion.repository_id == '$REPO_ID' && assertion.repository_owner_id == '$OWNER_ID'"
CONDITION+=" && assertion.ref == 'refs/heads/main' && assertion.environment == '$ENVIRONMENT'"
CONDITION+=" && assertion.workflow_ref == '$GITHUB_REPO/$WORKFLOW@refs/heads/main'"
MAPPING="google.subject=assertion.sub,attribute.repository_id=assertion.repository_id"
if exists iam workload-identity-pools providers describe "$PROVIDER" --location global --workload-identity-pool "$POOL"; then
  g iam workload-identity-pools providers update-oidc "$PROVIDER" --location global \
    --workload-identity-pool "$POOL" --attribute-condition "$CONDITION" --attribute-mapping "$MAPPING"
else
  g iam workload-identity-pools providers create-oidc "$PROVIDER" --location global \
    --workload-identity-pool "$POOL" --issuer-uri https://token.actions.githubusercontent.com \
    --attribute-condition "$CONDITION" --attribute-mapping "$MAPPING"
fi
PRINCIPAL="principal://iam.googleapis.com/projects/$NUMBER/locations/global/workloadIdentityPools/$POOL"
PRINCIPAL+="/subject/repo:$GITHUB_REPO:environment:$ENVIRONMENT"
g iam service-accounts add-iam-policy-binding "$(sa sam3d-deploy)" \
  --member "$PRINCIPAL" --role roles/iam.workloadIdentityUser >/dev/null

say "Done. Values for GitHub (Settings → Environments → $ENVIRONMENT → Environment secrets)"
cat <<EOF
GCP_PROJECT       $PROJECT
GCP_REGION        $REGION
GCP_WIF_PROVIDER  projects/$NUMBER/locations/global/workloadIdentityPools/$POOL/providers/$PROVIDER
GCP_DEPLOY_SA     $(sa sam3d-deploy)
GCP_IMAGE         $REGION-docker.pkg.dev/$PROJECT/$REPO/sam3d

For the engine (.env on your computer):
SAM3D_PROJECT=$PROJECT
SAM3D_REGION=$REGION
SAM3D_BUCKET=$WORK

Still yours to do (README.md, "What you do"): the GitHub environment '$ENVIRONMENT', limited
to the main branch, with the secrets above.
EOF
