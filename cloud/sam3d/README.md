# SAM 3D on a Cloud GPU

Last reviewed: 2026-10-16

Meta's two SAM 3D models, run on a rented GPU only while they work:

| Model | Gives, from one picture | Weights |
|---|---|---|
| [SAM 3D Objects](https://huggingface.co/facebook/sam-3d-objects) | each masked thing as a textured mesh (`.glb`), a Gaussian splat (`.ply`), and where it sits in the picture's camera (`.json`) | 13 GB, gated |
| [SAM 3D Body](https://huggingface.co/facebook/sam-3d-body-dinov3) | each person as a full-body mesh in the picture's camera (`.glb`) and its body, hand and shape parameters (`.npz`) | 2.8 GB, gated |

Neither runs on a laptop: SAM 3D Objects' authors ask for a 32 GB GPU. This folder is
everything needed to run them in Google Cloud for a few pence a picture. It is separate from
the engine (`src/content/`): the engine talks to it through `content/providers/sam3d.py`, by
putting pictures in a bucket and starting a job.

## How it works

```
 git push (main)                     GitHub Actions (free for a public repository)
      │                                 builds the image ─ pushes it ─ points the jobs at its digest
      ▼
 Artifact Registry ── image ──► Cloud Run job sam3d-run  (L4 GPU, 8 CPU, 32 GiB; no internet)
                                   reads  /weights  ◄── bucket <project>-sam3d-weights (read-only)
                                   reads  /work/jobs/<id>/in, writes /work/jobs/<id>/out
                                                    ◄── bucket <project>-sam3d-work (7-day expiry)
 your computer: content cloud sam3d …   uploads pictures, starts the job, waits, downloads results
```

- **One image, two jobs.** The same container is `sam3d-run` (`run <job-id>`, on a GPU) and
  `sam3d-fetch` (`fetch`, CPU only, run once to copy the weights from Hugging Face into the
  bucket). The arguments choose; nothing else differs.
- **Only the model's time is paid.** A Cloud Run job has no server waiting between runs: it
  starts, works, exits, and is billed by the second in between. Every picture of a request goes
  in one job, so the start-up (about a minute to read the weights) is paid once per batch, not
  per picture.
- **The image holds code, not weights.** The weights (16 GB) are too big for GitHub's free
  build machines, change rarely, and are licensed to you: they stay in your private bucket and
  are mounted read-only into the job.

## What it costs (us-central1, October 2026; check the [pricing page](https://cloud.google.com/run/pricing))

| | |
|---|---|
| a running job: L4 GPU $0.000187/s + 8 vCPU + 32 GiB | about $0.0004 a second: **$1.42 an hour, 2.4 cents a minute** |
| one picture with five things (estimate until measured) | 1 min start-up + under a minute a thing: about **10–15 cents** |
| the image in Artifact Registry (two kept) | about $0.10 per GB a month: **$1–3 a month** |
| the weights bucket (16 GB Standard) | **about $0.30 a month** |
| the work bucket | pennies; every job's files are deleted after 7 days |
| GitHub Actions, Secret Manager, the network, the jobs while idle | free |

Set a budget alert (Console → Billing → Budgets & alerts): $10 with alerts at 50% and 100%.

## Security: what stops what

The repository is public, so everything that matters lives in Google Cloud and in GitHub's
environment secrets, never in the code.

| Risk | What stops it |
|---|---|
| a stolen deploy key | there are none: GitHub's short-lived OIDC token is exchanged for an hour's Google token (Workload Identity Federation) |
| a fork, a pull request or another branch deploying | the workflow runs on push to `main` only; Google accepts the token only if it comes from this repository's ID and owner's ID (not its name, which can be re-registered), this workflow file, `refs/heads/main` and the `sam3d` environment, which GitHub limits to `main` |
| a compromised deploy doing more | `sam3d-deploy` can push to one registry and read and update two jobs (a custom role, `sam3dDeploy`); it cannot start them, read either bucket, or touch anything else. It signs in only after the build, so third-party code compiling never runs beside a credential |
| a bad commit on `main` deploying | the one risk the above cannot remove, since `main` is what deploys: protect `main` (Settings → Branches: require a pull request) and add yourself as the `sam3d` environment's required reviewer, so every deploy waits for your click |
| someone calling the model | a job has no address: only an account with `run.jobs.runWithOverrides` (you) can start it |
| a compromised dependency leaking data | `sam3d-run` has no route to the internet (its own network, Google APIs only), reads only the weights bucket and writes only the work bucket |
| a tampered package or download | base images pinned by digest, every Python package by hash (`requirements.lock`, `--require-hashes`), source archives and the hydra patch by checksum, git packages by commit, weights by Hugging Face revision and checked against its published hashes |
| a request reaching other files | `sam3d/request.py`: a job id and every file name must be plain names, no links, no paths, a size cap; anything unexpected is refused before a model loads (`tests/test_sam3d.py`) |
| a checkpoint config running arbitrary code | the pipeline's config may only name classes from the authors' whitelist (`sam3d_objects`, `torch`, `torchvision`, `moge`); the checkpoints themselves are pickles, which is why the revision is pinned |
| the Hugging Face token leaking | it is in Secret Manager, readable only by `sam3d-fetch`; it is never in GitHub, the image or a log, and is sent to huggingface.co only (not along redirects) |
| the container as root | it runs as user 10001 with no shell; the runtime image has no compiler, git or package cache |
| a forgotten bucket made public | public access prevention on both; uniform access; nothing in them can be shared by link |

Third-party GitHub Actions are pinned to full commit hashes, the workflow's default token has
no permissions, and checkout keeps no credentials.

## What you do (once)

1. **Hugging Face:** accept the licence on both model pages (you have), then make a token
   with read access: huggingface.co → Settings → Access Tokens → New token → type **Read**.
   Keep it to paste in step 3; never paste it into a chat.
2. **Google Cloud:** use the project you already have (or a new one). In your own terminal:
   `gcloud auth login`. Then ask the assistant to run
   `PROJECT=<id> GITHUB_REPO=<owner>/<name> cloud/sam3d/setup.sh`, or run it yourself. It
   prints the values for steps 3 and 4.
3. **The token, into Secret Manager**, in your own terminal:
   `gcloud secrets versions add hf-token --project <id> --data-file=-`, paste, Enter, Ctrl-D.
4. **GitHub:** repository → Settings → Environments → New environment `sam3d`. Under
   *Deployment branches and tags* choose *Selected branches* and add `main`. Add the five
   environment secrets setup.sh printed (`GCP_PROJECT`, `GCP_REGION`, `GCP_WIF_PROVIDER`,
   `GCP_DEPLOY_SA`, `GCP_IMAGE`). Under *Required reviewers*, add yourself: every deploy then
   waits for your click. Then Settings → Branches → add a rule for `main` requiring a pull
   request, so nothing reaches `main` (and so the cloud) without you.
5. **Push to main** (or Actions → *sam3d image* → Run workflow). The first build takes about an
   hour (it compiles the CUDA libraries); later ones run only when this folder changes.
6. **Fetch the weights, once:**
   `gcloud run jobs execute sam3d-fetch --region us-central1 --project <id> --wait`
   (about 10 minutes, CPU only, a few pence).
7. **GPU quota:** a project gets three L4s in a region automatically on first use; if the
   first run says the quota is zero, Console → IAM & Admin → Quotas → *Total Nvidia L4 GPU
   allocation without zonal redundancy, per project per region* → request 1.

Add the three `SAM3D_*` lines setup.sh printed to `.env`.

## Running it

```bash
content cloud sam3d objects room.png --mask chair.png --mask lamp.png --out results/room
content cloud sam3d body table.png --box 120 80 610 990 --focal 1450 --out results/table
```

A mask is a black-and-white picture the size of the image, white where the thing is (the
engine's survey makes them). Body boxes and the focal length are optional: without boxes the
whole picture is one person; without a focal length the model guesses the lens. In code,
`content.providers.sam3d.make()` takes any number of pictures in one job.

## The first run will tell us

Not yet measured, because no GPU has run it:

- **memory:** the authors ask for 32 GB; the L4 has 24 GB. If SAM 3D Objects runs out of GPU
  memory, the options are an RTX PRO 6000 (96 GB, also on Cloud Run, about twice the price)
  with a CUDA 12.8 build of the image, or a Compute Engine A100.
- **downloads the checkpoints' configs ask for:** the run job has no internet, so if the
  objects pipeline's config names another model (its depth model or DINOv2's pretrained
  weights), the run fails in seconds naming it; it is then added to `models.json` (or, for a
  torch.hub backbone, `HUB` in `sam3d/__main__.py`) and fetched like the rest.

## Changing it

| To | Change |
|---|---|
| update a model | its revision in `models.json`, then push and run `sam3d-fetch` again |
| add or update a Python package | `requirements.in`, then the `uv pip compile` line at its top |
| use another GPU | `GPU_TYPE` in setup.sh (`gcloud run jobs update sam3d-run --gpu-type …`), and `TORCH_CUDA_ARCH_LIST` in the Dockerfile |
| stop paying for it entirely | delete the two jobs, the registry and the two buckets in the console |
