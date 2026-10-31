# Step 9.A — 임상정보 연결 검증

## Purpose

Research의 실제 날짜·진단 동률·원자료 보존 규칙을 원본 후속 임상 검증으로 적용합니다. Step 8 포함표를 run 단위로 보존하며 원본 Step 9의 표기/시점 가정을 분석용 진단으로 그대로 사용하지 않습니다.

## Input

- `--included`: Step 8의 TSV/CSV, 필수 `sub,ses`; `task,run,acq,echo,dir,rec` 등 실제 BIDS 식별 열 보존.
- `--scan-links`: 참가자·세션과 실제 `Image_ID,Scan_Date`를 연결하는 fMRI conversion mastersheet 또는 명시적 CSV. `Subject_ID,VISCODE` 또는 `sub,ses` 지원. `bl/mNN`만 Clinica `ses-MNNN`로 정규화하며 날짜를 방문코드로 추정하지 않음.
- 한 세션에 여러 run이면 각 run의 정확한 Image ID 대응을 제공해야 함. 여러 날짜/phase/영상 후보 또는 같은 ID의 여러 run 재사용은 자동 첫 행 선택 없이 hold.
- UID는 원본 `dicom_SeriesInstanceUID`와 `SERIES_UID/SeriesInstanceUID`를 지원하며, 같은 영상의 서로 다른 UID 또는 UID 열 간 충돌도 hold.
- `--dxsum`: `PTID` 또는 `RID`, `PHASE,EXAMDATE,DIAGNOSIS`, 선택 `HAS_QC_ERROR,DXMDUE,DXDDUE`.
- `--ptdemog`: `PTID` 또는 `RID`, `VISDATE`, 선택 `PTEDUCAT,PTHAND,PTETHCAT,PTRACCAT,PTDOB`, legacy/ADNI4 sex 열 또는 `PTGENDER`.
- 선택 `--apoe`: `PTID/RID,GENOTYPE`; `--adsl`,`--dm`: numeric `SUBJID` 또는 RID, `SEX`(Male/Female 또는 M/F). RDS 입력은 지원하지 않으며 명시적 CSV export가 필요.

## Processing

- 실제 날짜를 유일하게 확인한 뒤 유효 DXSUM의 최근접 행 **전부** 연결. 진단 충돌은 hold, 동일 임상평가의 여러 영상 사용은 허용.
- `--max-dx-days 28`은 Research의 초기 정책이며 연구별로 변경 가능. `--dx-direction past`는 촬영 전 평가만 허용. 날짜 차이·부호·미래 방문 사용·phase 불일치 기록.
- `1=CN`, `2=MCI`, `3=Dementia`; `DXMDUE/DXDDUE` 일치 근거가 있는 경우에만 임상 AD/other 의심 원인 추가. ADNI1 dementia의 later-phase 원인 매핑 제외, 생물학적 AD 추정 제외.
- PTDEMOG 최근접 동률 원본 모두 보존. 교육·손잡이·인종·민족·성별·APOE가 결측/상충하면 미확인 표시, 이 이유만으로 run 제외하지 않음.
- Scan-link Age를 별도 출처로 기록하고 PTDOB의 월 단위 근사 나이·출생정보 충돌을 대조. 과거 RDS snapshot의 최초 PTDOB 선택은 재현하지 않음.

## Output

`clinical_validation.tsv`: 모든 입력 run과 pass/hold·사유. `clinically_validated_sessions.tsv`: 임상 연결 조건을 통과한 부분집합. `clinical_source_rows.tsv`: 연결된 원본 행 전체를 원본 row 번호와 JSON으로 보존. `clinical_source_eligibility.tsv`: QC error·무효 날짜/진단 제외 근거. `artifact.json`: 입력/출력/code hash와 정책.

모든 결과의 `ANALYSIS_READY=False` 유지. **임상 pass는 MRI 품질·물리 파일·시각 QC 통과가 아닙니다.** 이 부분집합은 원본 및 Custom QC 판정과 함께 연구 포함표를 만들 때 사용합니다.

## Execution

```sh
python 02_custom/s9a_validate_clinical/run.py \
  --included /ABSOLUTE/PATH/ADNI_DATA/qc/final/included_reviewed_sessions.tsv \
  --scan-links /ABSOLUTE/PATH/ADNI_DATA/qc/step5a/data/anchor_plus_dicom_nifti_struct.csv \
  --dxsum /ABSOLUTE/PATH/ADNI_DATA/LONI_download/clindata/DXSUM.csv \
  --ptdemog /ABSOLUTE/PATH/ADNI_DATA/LONI_download/clindata/PTDEMOG.csv \
  --max-dx-days 28 --dx-direction nearest \
  --output-dir /ABSOLUTE/PATH/ADNI_DATA/qc/step9a
```

APOE/ADSL/DM을 제공하지 않으면 해당 검증 미수행 상태를 보존합니다. 단일 촬영일·최신 방문·AD-only·complete-case 코호트를 강제하지 않습니다.

## Validation

합성 run으로 진단·날짜 동률, 상충 진단, 오래된 평가, 과거 평가만 사용, source QC error, 임상 방문 재사용, 다중 run/영상 식별, PTID/RID 충돌, 교육/APOE 결측·성별 충돌, 원본 불변과 덮어쓰기 방지 검사.

## Dependencies

Python 3.11+ 표준 라이브러리. 공식 진단 정의: [ADNI DXSUM](https://adni.loni.usc.edu/quick-start-guide-asset/diagnostic.html). 출처: Research의 `2026-10-30-preserve-all-v1` 임상 규칙을 CSV/run 기반으로 이식한 구현이며 기존 R 임상 모듈 전체와 수치적 동등성을 주장하지 않습니다.
