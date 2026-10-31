# Step 8.A — motion censoring 이후 잔여 시간

## Purpose

기존 로컬 `paper_motion_qc.py`를 독립 Custom Step으로 가져왔습니다. 원본 s8이 계산하지 않는 motion 제외 후 잔여 시간을 검사하며 [Rutherford et al. v3](https://arxiv.org/pdf/2602.03278v3)의 30%·300초 기준을 별도로 평가합니다.

## Input

- 원본 BIDS의 각 run에 대응하는 4D `*_bold.nii.gz`와 JSON `RepetitionTime`.
- fMRIPrep `*_desc-confounds_timeseries.tsv`의 FD 및 non-steady-state 지시 열.
- 현재 구현은 `sub-*/ses-*/func/` 및 run/acq가 일치하는 직접 JSON을 사용합니다. session 없는 BIDS·상속 JSON·multi-echo 변형은 확장 검증 전 자동 지원으로 간주하지 않습니다.

## Processing

실제 NIfTI frame 수·시간 단위·TR과 JSON·confounds를 대조합니다. FD >0.5 mm 시점 비율 ≤30%, 남은 저움직임 시간 ≥300초를 계산합니다. 첫 undefined FD는 원본 도구와 같이 0으로 처리하고 non-steady-state 제외는 별도 민감도 결과로 보존합니다.

## Output

`paper_motion_summary.tsv`, 원래 frame index를 가진 run별 mask, 입력 hash·기준·결과를 담은 `paper_motion_provenance.json`. 영상의 시점은 삭제하지 않습니다. 원본 포함표에 자동 병합하지 않으며, MRIQC·Euler·coverage·시각 QC 판정을 대신하지 않습니다.

## Execution

root README의 `python 02_custom/s8a_motion_duration_qc/run.py --bids-root ... --derivatives-root ... --output-dir ...` 사용. 출력은 입력 tree와 겹치지 않는 새 폴더여야 합니다.

## Validation

정확히 300초·30% 경계, motion과 초기 시점 중복, 결측 FD, TR/행 수 불일치, 원본 불변 및 재실행 덮어쓰기 방지를 합성 영상으로 검증합니다. 실제 전체 코호트 연구 포함 판정은 미완료입니다.

## Dependencies

Python 3.11+, NumPy, pandas, NiBabel. 초기 복사본의 hash는 `03_config/imported_sources.json`에 기록했습니다.
