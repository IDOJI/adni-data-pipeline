# Historical local S10 source reference

These four Python source/test files preserve the standalone S10 implementation as found at checkout retirement. They are reference sources, not a second active postprocessing pipeline. Use [Custom Step 10](../../pipeline/s10_xcpd_integrated_qc/README.md) for current execution.

The standalone pipeline had local changes after its first import. The [retirement manifest](../../03_config/s10_local_reference.json) records the exact original and exported hashes; three files are byte-identical and the historical test uses synthetic participant/date examples. Original private configuration and exact originals are in the verified backup outside this repository. No historical settings or result identities were rewritten.

These sources expect the historical external configuration and surrounding deployment. Python syntax and source/export hashes were checked; the reference files are outside default test collection, and no imaging was run. Preserve the original statMIND attribution and repository GPL license when reusing this code.
