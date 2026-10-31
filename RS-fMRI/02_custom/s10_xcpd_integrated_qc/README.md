# Step 10 — S8 수집·XCP-D·통합 영상 QC

## Purpose

참조한 ADNI 일부 데이터 전처리 스레드의 S8 → XCP-D → 정량 QC → 검증 후 외장 보관 기능입니다. LLM/API 없이 Python·Docker 반복 처리로 동작하며 전체 코호트와 사람의 검토가 준비될 때까지 최종화는 보류합니다. 코드 설치가 실행 중인 서비스를 자동 전환하거나 새 계산을 시작하지 않습니다.

## Input

- 외부 JSON: [xcpd_linc.example.json](../../03_config/xcpd_linc.example.json)을 복사해 root/license/templateflow를 수정. `repo=null`은 이 저장소의 고정 upstream submodule을 뜻하며 다른 checkout으로 대체할 수 없음.
- `<root>/results/<PTID>/EPI_YYYYMMDD_MT1_YYYYMMDD/{fmriprep,mriqc,pair_metadata.json}`: 참조 스레드의 게시 완료 pair layout. 해당 fMRIPrep에는 기능·해부학 영상, mask/reference/transform, confounds JSON/TSV, HTML, sessionwise FreeSurfer log가 필요.
- `pair_metadata.json`: subject/PTID/pair_id, 실제 epi_date/mt1_date·영상 ID, execution_session_label, `delivery_status=processing_complete_QC_pending`, 실제 `execution_identity`의 mriqc/fmriprep 시작 시각·runner hash·image 필요.
- `<root>/runs/<subject>/logs/*_{mriqc,fmriprep}_sub-*_ses-*/run.json`: 정상 종료·입력 불변과 게시 identity를 대조하는 실제 증빙. 기록 없이 폴더만 복사해 완료로 가장하지 않음.
- 평면형 upstream Slurm derivatives를 이 pair layout으로 자동 변환하는 adapter와 S6/S7 queue scheduler는 이번 통합에 포함하지 않음. 현재 스레드의 queue는 별도 운영 실행기로 계속 동작. 7.A의 FreeSurfer 없는 volume 결과도 S10에 바로 투입하지 않음.

## Processing

고정 XCP-D 26.2.0 image digest, linc/nifti, MNI152NLin6Asym/res-2, 36P/GSR, FD 0.3 mm, 최소 240초, 4S256(256 ROI), 0.01–0.08 Hz, smoothing 6 mm, dummy 0, despike·LINC/ABCC QC 사용. 세부 설정은 JSON과 실제 xcp_d.toml을 대조합니다. 8.A의 300초 기준과 다른 검사이며 서로 대체하지 않습니다.

1. S6/S7 완료 증빙을 확인한 뒤 pinned upstream의 S8 motion·Euler 함수를 재사용하고 MRIQC IQM 수집.
2. 개별 motion 실패·필수 지표 누락·명시 제외 차단. cohort Euler/MRIQC만 대기인 경우 `allow_deferred_cohort_candidates=true`일 때 잠정 XCP-D 후보로 허용하되 pass로 기록하지 않음.
3. 실제 PyBIDS 선택을 subject/session/task/run/acq/dir/echo/rec 전체로 확인. 명시하지 않은 run은 null로 선택, 임의 run-01 생성 없음.
4. 입력 read-only·hash 보존, 첫 pilot 검증 후 순차 확대, 실패 attempt·부분 결과·기존 Docker 재연결 지원. 출력 BOLD/ROI/FC/coverage·motion/censor/LINC QC·HTML·ALFF/ReHo 및 실행 설정 대조.
5. 인간 review 열은 기존 판정과 revision을 보존. `collect/watch`는 최종화하지 않음. 별도의 cohort 완료·현재 MRIQC flag 입력·필요한 사람 검토 후 영상 QC만 최종화.

## Output

`<root>/postprocessing/<config_id>/`: `final_qc_master.tsv`, `pending_review.tsv`, `visual_review.tsv`, counts/distributions/report, pilot/status 및 configuration. 실제 검증된 attempt는 pair별 `s10/<config_id>/runs/`에 보존합니다.

`clinical_scan_links.tsv`는 실제 epi_image_id/epi_date와 run identity를 9.A 입력으로 내보냅니다. `finalizations/<timestamp>/final_included_runs.tsv`와 같은 폴더의 link 표를 9.A에 전달합니다. `ANALYSIS_READY=False`이며 S10 final은 **영상 QC 범위**입니다. 3.A source QC·8.A의 연구별 기준·9.A 임상정보와의 최종 교집합은 별도 연구 포함 판정입니다.

`archive_ready.json`은 보관 가능 증빙이며 연구 포함 확정이 아닙니다. 외장 이동기는 해당 config_id와 근거 파일 hash, 실제 volume UUID·복사본을 확인한 다음에만 공간을 회수합니다.

## Execution

`RS-fMRI/`에서 실제 외부 config를 지정합니다. 현재 운영 worker와 같은 root에서 중복 pilot/watch를 실행하지 않습니다.

```sh
python 02_custom/s10_xcpd_integrated_qc/pipeline.py --config /ABSOLUTE/PATH/xcpd.local.json preflight
python 02_custom/s10_xcpd_integrated_qc/pipeline.py --config /ABSOLUTE/PATH/xcpd.local.json dry-run
python 02_custom/s10_xcpd_integrated_qc/pipeline.py --config /ABSOLUTE/PATH/xcpd.local.json pilot
python 02_custom/s10_xcpd_integrated_qc/pipeline.py --config /ABSOLUTE/PATH/xcpd.local.json watch
# 필요한 경우 별도 터미널에서 수집. 실제 영상 검토 후 visual_review.tsv는 연구자가 편집.
python 02_custom/s10_xcpd_integrated_qc/pipeline.py --config /ABSOLUTE/PATH/xcpd.local.json collect
# 실패 새 attempt / 계산 재실행 없이 검증만 다시 수행
python 02_custom/s10_xcpd_integrated_qc/pipeline.py --config /ABSOLUTE/PATH/xcpd.local.json retry-failed
python 02_custom/s10_xcpd_integrated_qc/pipeline.py --config /ABSOLUTE/PATH/xcpd.local.json revalidate
# 코호트 준비 후에만 명시적으로 실행. watch는 이 명령을 호출하지 않음.
python 02_custom/s10_xcpd_integrated_qc/pipeline.py --config /ABSOLUTE/PATH/xcpd.local.json finalize --cohort-complete --mriqc-flags /ABSOLUTE/PATH/current-cohort-flags.tsv
```

`slurm`은 array 파일 생성만 하며 `sbatch` 제출은 하지 않습니다. CIFTI/Apptainer는 별도 실행 검증 대상입니다.

외장 이동은 별도 명령입니다. [예시 설정](../../03_config/offload.example.json)의 실제 UUID·runtime·검증된 config_id를 먼저 채웁니다. **아래 명령은 복사 및 검증 후 로컬 사본 회수를 수행합니다.** 이번 코드 통합에서는 실제 데이터 이동을 실행하지 않습니다.

```sh
python 02_custom/s10_xcpd_integrated_qc/offload_completed.py --root /ABSOLUTE/PATH/ADNI_DATA/pair_runtime --settings /ABSOLUTE/PATH/offload.local.json --once
```

## Validation

`05_tests/test_xcpd_integrated.py`, `test_xcpd_offload.py`, `test_xcpd_consolidation.py`에 입력·누락/실패·null BIDS 선택·실제 설정/ROI/censoring 대조·재연결·pilot gate·인간 검토 보존·외장 단절/손상/복구·9.A 연결 검사를 포함합니다. 실제 진행 중 pilot의 성공 여부는 기존 runtime의 증빙으로만 판단합니다. [검증 범위](../../06_docs/validation.md).

## Dependencies

Python 3.11+, [requirements](../../requirements.txt), pinned upstream S8, Docker/기존 XCP-D 26.2.0 image와 atlas/template cache. [공식 CLI](https://xcp-d.readthedocs.io/en/26.2.0/usage.html), [공식 mode 설정](https://xcp-d.readthedocs.io/en/26.2.0/workflows.html), [통합·전환 경계](../../06_docs/xcpd_consolidation.md).
