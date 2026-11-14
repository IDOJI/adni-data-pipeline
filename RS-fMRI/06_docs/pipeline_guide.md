# Adding or updating a stage

1. Place code in `pipeline/s<step>_<name>/`.
2. Keep the stage README to **What**, **Output** and **Run**: describe the input/action, name the output files, then give the shortest complete command.
3. State the working directory and required configuration. Label commands that preview, execute imaging, run continuously or modify inputs.
4. Update the [step table](../README.md#steps-and-commands). Link to one command source instead of copying it into several guides.
5. Preserve input/output contracts and relevant QC conditions. Keep private data, configuration and results outside Git.

New local imaging examples use the seeded entry points. Keep the distinct 7.A aCompCor and S10 36P/GSR profiles explicit. Do not present planned features as runnable commands.

After a code change, run `python -m pytest -q` and `python 04_workflow/lab.py doctor` from `RS-fMRI/`. Use a separate checkout for changes while an existing deployment is running.
