# Step 3.A — 원본 QC·NFQ 근거 검증

## Purpose

Research 선별 과정의 원본 품질·식별 대조를 원본 Step 3 이후의 독립 검사로 추가합니다. 과거 Selection Table/RDS 없이 현재 사용자가 제공한 ADNI Study Files 원본을 읽습니다. 여기서 `MRIQC`는 ADNI Study Files 촬영 목록이며 MRIQC 프로그램의 IQM 출력과 다릅니다.

## Input

필수 `--mriqc-table`: 원본 MRIQC CSV. 선택 `--adni3-qc`, `--go2-qc`, `--deleted-scans`, 반복 `--nfq SOURCE=PATH`. 지원 schema는 Research가 사용한 MRIQC·MAYO ADNI3·GO/2·Deleted Scans·NFQ의 원본 열 이름입니다. 열 이름을 임의 추측하지 않으며 다른 릴리스 schema는 명시적으로 adapter를 확장해야 합니다.

MRIQC에는 `image_id`, `ParticipantID`, `StudyDate`, `SeriesType`, `SeriesInstanceUID`, `StudyInstanceUID`, `LONIStudy`, `LONISeries`, `SeriesNumber`, `MRIProtocolPhase`, `SeriesTime`이 필요합니다. 각 Mayo QC source의 필수 열은 `qc_registry.py::normalize`에 명시했습니다. NFQ에는 ID 또는 UID 또는 완전한 합성 식별정보와 `OVERALLQC`를 사용합니다.

## Processing

- Image ID와 PTID/RID·실제 날짜·종류·UID·LONI 식별정보를 대조, 충돌·삭제·품질 4·−1·study 보류를 차단 상태로 기록.
- 등급 1·2·3은 허용, chosen 표시는 실패를 덮어쓰거나 후보를 하나로 축소하는 기준으로 사용하지 않음.
- GO/2의 ID 결측은 유일한 LONI series+study+RID+날짜+종류 대응만 허용, 여러 target은 격리.
- 원본 NFQ의 ID → UID → RID/날짜/series number/시각(1초 이내) 대응. 명시 ID 충돌을 다른 매칭으로 덮어쓰지 않음.
- NFQ 품질과 SliceTiming 유무를 분리, ST가 비어 있어도 NFQ 실패 확인.
- `blocked`, `pending`, `pass` 구분. EPI는 기본 QC와 NFQ 모두 확인돼야 `pass`; 소스/기록 부재는 `pending`.

## Output

`image_qc.tsv`, 원본별 QC registry·NFQ 원본 행 감사, 입력/출력/code hash가 있는 `artifact.json`. 결과는 저장소 밖 새 폴더에만 기록합니다. 원본 영상·표·submodule은 변경하지 않습니다.

## Execution

`RS-fMRI/`에서 실행하며 경로는 외부 실제 파일로 바꿉니다.

```sh
python 02_custom/s3a_source_qc/run.py \
  --mriqc-table /ABSOLUTE/PATH/ADNI_DATA/LONI_download/clindata/MRIQC.csv \
  --adni3-qc /ABSOLUTE/PATH/ADNI_DATA/LONI_download/clindata/MAYO_ADNI3.csv \
  --go2-qc /ABSOLUTE/PATH/ADNI_DATA/LONI_download/clindata/MAYO_GO2.csv \
  --deleted-scans /ABSOLUTE/PATH/ADNI_DATA/LONI_download/clindata/DELMRSCANS.csv \
  --nfq GO2_3=/ABSOLUTE/PATH/ADNI_DATA/LONI_download/clindata/NFQ.csv \
  --output-dir /ABSOLUTE/PATH/ADNI_DATA/qc/step3a
```

## Validation

합성 schema로 품질/chosen 분리, grade 4·−1·삭제·충돌, NFQ ST 결측 실패, UID 불일치, GO/2 유일 대응, pending 보존, 덮어쓰기 거절과 5.C 연결 검증. 실제 코호트 전수 검사 완료를 뜻하지 않습니다.

## Dependencies

Python 3.11+ 표준 라이브러리. 출처 및 원본 코드 hash는 `03_config/imported_sources.json`. 근거: [ADNI MRI QC](https://adni.loni.usc.edu/data-samples/adni-data/neuroimaging/mri/mri-quality-control/).

이 단계는 원본의 영상 선택·변환을 대체하지 않습니다. 전체 T1/EPI 소스를 감사하지만, 실제 T1 참조 영상과 BOLD의 대응·NIfTI/JSON·ST 축/방향은 별도 실영상 검증 대상입니다. NFQ ADNI4 원자료를 감사해도 Clinica ADNI4 지원이 추가되는 것은 아닙니다.
