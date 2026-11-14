# Frame and run mapping

Run from `RS-fMRI/`. Replace example paths and IDs with the same raw and processed run.

## Map censored frames

Produces `acquisition_frames.tsv` and `artifact.json` in `--output-dir`. Set `--dummy-volumes` to the actual number removed.

```sh
python pipeline/s11_atlas_bold/adapters.py frames \
  --raw-bold /DATA/bids/sub-ADNI999S9999/ses-M000/func/sub-ADNI999S9999_ses-M000_task-rest_bold.nii.gz \
  --raw-json /DATA/bids/sub-ADNI999S9999/ses-M000/func/sub-ADNI999S9999_ses-M000_task-rest_bold.json \
  --bold /DATA/xcp_d/sub-ADNI999S9999/ses-M000/func/sub-ADNI999S9999_ses-M000_task-rest_space-MNI152NLin6Asym_desc-denoised_bold.nii.gz \
  --bold-json /DATA/xcp_d/sub-ADNI999S9999/ses-M000/func/sub-ADNI999S9999_ses-M000_task-rest_space-MNI152NLin6Asym_desc-denoised_bold.json \
  --outliers /DATA/xcp_d/sub-ADNI999S9999/ses-M000/func/sub-ADNI999S9999_ses-M000_task-rest_outliers.tsv \
  --dummy-volumes 0 --output-dir /DATA/audit/run-001/acquisition-map
```

## Link processed BOLD to source inclusion

Produces `linked_run.tsv` and `artifact.json` in `--output-dir`.

```sh
python pipeline/s11_atlas_bold/adapters.py link-run \
  --inclusion /DATA/qc/step9b --image-id 999999999 \
  --raw-bold /DATA/bids/sub-ADNI999S9999/ses-M000/func/sub-ADNI999S9999_ses-M000_task-rest_bold.nii.gz \
  --raw-json /DATA/bids/sub-ADNI999S9999/ses-M000/func/sub-ADNI999S9999_ses-M000_task-rest_bold.json \
  --bold /DATA/xcp_d/sub-ADNI999S9999/ses-M000/func/sub-ADNI999S9999_ses-M000_task-rest_space-MNI152NLin6Asym_desc-denoised_bold.nii.gz \
  --bold-json /DATA/xcp_d/sub-ADNI999S9999/ses-M000/func/sub-ADNI999S9999_ses-M000_task-rest_space-MNI152NLin6Asym_desc-denoised_bold.json \
  --preprocessed-json /DATA/fmriprep/sub-ADNI999S9999/ses-M000/func/sub-ADNI999S9999_ses-M000_task-rest_space-MNI152NLin6Asym_desc-preproc_bold.json \
  --output-dir /DATA/audit/run-001/bids-link
```

Pass these **directories** to extraction as `--frame-map` and `--run-link`. Use matching-space files throughout; the examples above use MNI152NLin6Asym.
