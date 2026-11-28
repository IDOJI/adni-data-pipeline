# Setup

Use Python 3.11+ and Git. Run the following once:

```sh
git clone https://github.com/IDOJI/adni-data-pipeline.git
cd adni-data-pipeline/RS-fMRI
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt -r pipeline/s5_post_clinica_qc/requirements.txt -r pipeline/s14_fc_harmonization/requirements.txt
python 04_workflow/lab.py doctor
```

For imaging, install Docker Desktop (macOS) or Docker Engine (Linux), obtain a FreeSurfer license and load the pinned container images. fMRIPrep runs inside Docker; a separate host fMRIPrep installation is unnecessary. Cloning the repository alone does not install these dependencies. Clinica/dcm2niix and R are needed only for their stages.

Return to the [four-stage guide](../README.md#setup) to set your study path. The local study publisher uses the macOS clone-copy command on a compatible volume. [Platform notes](platform_execution.md)

## Paths for a manual run

In an activated shell under `RS-fMRI/`, edit the first two values. `DATA` holds your own input; `RESULTS` is a new private folder under an existing writable parent. Use absolute paths without commas or colons. Keep the results outside the repository, input tree and source TemplateFlow cache. On Docker Desktop share the drives and allocate memory for the selected profile (7.B requests 16 GiB, 7.A requests 24 GiB).

```sh
export DATA="/absolute/path/to/your/input-folder"
export RESULTS="/absolute/path/to/your/new-results-folder"
export CFG="$RESULTS/pair/verified-config.yaml"
export CASE="$RESULTS/pair/processing"
export ADNI_PIPELINE="$PWD/pipeline"
export PYTHONPATH="$ADNI_PIPELINE${PYTHONPATH:+:$PYTHONPATH}"
```

Create the output folder once. On resuming, reactivate the environment and repeat only the exports above with the original values.

```sh
mkdir -m 700 "$RESULTS"
```

Both imaging routes expect your `$DATA/license.txt` and a resident `$DATA/templateflow/` cache. `CFG` and `CASE` are used by the verified ADNI route. The ordinary BIDS route reads `$DATA/bids/`. Keep original scans, private configurations, derivatives and working directories outside Git.

<details>
<summary>Load the Docker images for imaging</summary>

Load the pinned Docker images once. This block reads their digests from the repository. It adds the version tags needed by the session runner and stops if an existing tag points at another image. These are large downloads.

```sh
python - <<'PY'
import json, subprocess
from pathlib import Path
batch = json.loads(Path("03_config/local_batch.seeded.example.json").read_text())
xcp = json.loads(Path("03_config/xcpd_linc.seeded.example.json").read_text())
for reference in [*batch["pinned_images"].values(), xcp["image"]]:
    subprocess.run(["docker", "pull", "--platform", "linux/amd64", reference], check=True)
for stage, reference in batch["pinned_images"].items():
    tag = batch["preprocessing_template"]["images"][stage]
    inspect = subprocess.run(["docker", "image", "inspect", tag], capture_output=True, text=True)
    if inspect.returncode:
        subprocess.run(["docker", "tag", reference, tag], check=True)
    item = json.loads(subprocess.check_output(["docker", "image", "inspect", tag], text=True))[0]
    resolved = next((d for d in item["RepoDigests"] if d.split("@")[0] == reference.split("@")[0]), None)
    if resolved != reference or (item["Os"], item["Architecture"]) != ("linux", "amd64"):
        raise SystemExit(f"Check the local image for {tag} before processing")
    print(stage, resolved)
PY
```

</details>

## Read a Docker preview

The stage command you paste invokes the repository's runner. Its preview shows the longer command for your selected case. Before the container image name, the options configure Docker. After the image, the program receives its inputs, output directory, `participant` analysis level and processing options. In Step 10 the image first runs a small Python check of the selected BOLD and atlas, then passes those options to XCP-D.

| Execution option | How to read it |
|---|---|
| Docker `run` or `create`, `--name`, `--label` | Start a container or prepare it for a separate start. Names and labels tie it to the run record. A dry run only shows the plan. |
| `--platform linux/amd64`, image `@sha256:…`, `--pull never`, `--rm` | Select the image architecture and exact build. Where present, `--pull never` uses the installed image and `--rm` removes the exited container. Mounted output and work directories persist. |
| `--mount` or `-v`, `--env` or `-e`, `--entrypoint` | Connect host files to container paths (`readonly` or `:ro` protects input). Environment variables locate TemplateFlow, set seeds and limit numerical threads. An entry point selects the program that starts inside the image. Edit host paths in the private config. |
| Docker `--cpus`, `--memory` | Set the container's CPU quota and memory limit. These values apply to one container. |
| Application `--nprocs`, `--omp-nthreads`, `--mem-mb` | Set the workflow CPU budget, threads available to an individual threaded operation, and memory budget for scheduling tasks. With `--omp-nthreads 1`, independent workflow tasks can still run concurrently. |
| `-w` or `--work-dir`, `--stop-on-first-crash`, `--notrack` | Set the intermediate work directory, stop the workflow on its first crash, and disable usage reporting. The derivatives go to the separate output mount. |

For a new participant, change the input paths and labels in your private configuration. To reproduce a published profile, keep its scientific settings. For a planned change in denoising model, output space or censoring threshold, use a fresh results and work directory so that the two analyses can be compared.

## Configuration

After setting `DATA` and `RESULTS` above, make your private lab configuration:

```sh
mkdir -p "$DATA/config"
cp 03_config/lab_config.example.yaml "$DATA/config/lab.yaml"
```

Edit `lab.yaml` with your data/scratch/container/license paths. Then generate a new configuration directory:

```sh
python 04_workflow/lab.py prepare-config \
  --lab-config "$DATA/config/lab.yaml" --output-dir "$DATA/config/run-001"
export PIPELINE_CONFIG="$DATA/config/run-001/pipeline.yaml"
export ADNI_CONFIG="$PIPELINE_CONFIG"
```

This YAML supports DICOM/Clinica and shared tools. Local Docker imaging uses the separate [batch JSON](local_batch.md). See [host requirements](platform_execution.md) and [seed settings](seed_reproducibility.md).
