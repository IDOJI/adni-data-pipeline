# Setup

Use Python 3.11+ and Git. Run the following once:

```sh
git clone https://github.com/IDOJI/adni-data-pipeline.git
cd adni-data-pipeline/RS-fMRI
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt -r pipeline/s5_post_clinica_qc/requirements.txt
python 04_workflow/lab.py doctor
```

For imaging, install Docker Desktop (macOS) or Docker Engine (Linux), obtain a FreeSurfer license and load the pinned container images. fMRIPrep runs inside Docker; a separate host fMRIPrep installation is unnecessary. Cloning the repository alone does not install these dependencies. Clinica/dcm2niix and R are needed only for their stages.

## Configuration

From `RS-fMRI/`, set the shared paths used in the stage examples:

```sh
export DATA=/ABS/ADNI_DATA
export ADNI_PIPELINE="$PWD/pipeline"
export PYTHONPATH="$ADNI_PIPELINE${PYTHONPATH:+:$PYTHONPATH}"
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
