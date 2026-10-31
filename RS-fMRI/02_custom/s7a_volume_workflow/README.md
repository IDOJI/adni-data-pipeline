# Step 7.A — Docker volume workflow (aCompCor profile)

## Purpose

기존 로컬 `adni-rsfmri-pipeline`의 fMRIPrep → XCP-D volume 실행·감사·영상 QC·안전한 metadata 복구 기능을 통합한 경로입니다. 최신 S10의 36P/LINC와 다른 분석 설정을 보존합니다. 원본 Step 7 Slurm 경로와 함께 같은 output/cache에 실행하지 않습니다.

| 항목 | 이 경로 | 주 후처리 S10 |
|---|---|---|
| 표준 공간 | MNI152NLin2009cAsym/res-2 | MNI152NLin6Asym/res-2 |
| 회귀 | aCompCor, GSR 없음 | 36P, GSR 포함 |
| FD / 최소 잔여 시간 | 0.5 mm / 240초 | 0.3 mm / 240초 |
| FreeSurfer reconstruction | 비활성 | S8 Euler를 위해 완료된 FreeSurfer 필요 |
| ROI/FC | 이 profile에서 생략 | 4S256 ROI/FC·coverage 검증 |

## Input

실제 BIDS T1w/rest BOLD와 원래 metadata, 별도의 FreeSurfer license, 외부 JSON 설정이 필요합니다. `config.example.json`의 참가자는 합성 예시입니다. 모든 runtime/data 경로를 저장소 밖 실제 위치로 바꿉니다. 지원 단위는 명시 subject/session이며 여러 run/echo로 일반화된 실행기로 간주하지 않습니다.

## Processing

- fMRIPrep 25.2.7 및 XCP-D 26.2.0의 고정 tag를 설치된 immutable digest로 해석, shell 없는 argv 실행.
- 입력 read-only mount·전후 SHA-256, 명령·설정·runner snapshot·CITATION 및 cache identity 기록.
- `repair_xcpd_metadata.py`: 알려진 누락 단위만 조건부 보완, 압축 원본·전후 header 및 voxel payload 불변 증명 보존. 임의 헤더 수정 금지.
- `audit_outputs.py`: confounds/Power FD·censoring·출력 volume·설정·보고서 대조. `qc_images.py`: voxel 유한값/시간 분산과 정합 mosaic. 영상 생성은 사람이 하는 시각 검토의 대체가 아님.

## Output

외부 `paths`의 derivatives/work/logs와 독립 QC JSON·PNG. 실행 완료와 기술 검사·시각/연구 판정을 구분합니다. 기존 실제 두 방문의 상세 결과와 개인 config는 로컬 보관본에만 유지합니다.

## Execution

`RS-fMRI/`에서 실제 외부 config를 지정합니다. 컨테이너 다운로드·계산은 아래 명령을 명시 실행할 때만 수행합니다.

```sh
python 02_custom/s7a_volume_workflow/pipeline.py --config /ABSOLUTE/PATH/volume.local.json dry-run --stage fmriprep --subject 999S9999
python 02_custom/s7a_volume_workflow/pipeline.py --config /ABSOLUTE/PATH/volume.local.json run --stage fmriprep --subject 999S9999
python 02_custom/s7a_volume_workflow/pipeline.py --config /ABSOLUTE/PATH/volume.local.json verify --stage fmriprep --subject 999S9999
python 02_custom/s7a_volume_workflow/pipeline.py --config /ABSOLUTE/PATH/volume.local.json run --stage xcpd --subject 999S9999
python 02_custom/s7a_volume_workflow/audit_outputs.py --data-root /ABSOLUTE/PATH/ADNI_DATA/volume --subject 999S9999 --session 20200101 --output /ABSOLUTE/PATH/ADNI_DATA/volume-qc/audit.json
```

이전 성공한 XCP-D의 metadata 보완은 같은 config/subject에 `finalize-xcpd --stage xcpd`를 사용합니다. 성공·입력 불변·실행 identity를 확인하며 원래 실행 기록은 보존합니다. 이미 동작 중인 컨테이너를 이사하거나 cache identity를 새로 채워 우회하지 않습니다.

## Validation

기존 실행·실패 복구·header/voxel 불변·독립 감사·영상 QC 합성 테스트를 `05_tests/volume_workflow/`에 이식했습니다. 원래 실제 방문의 실행 기록은 이번 통합의 재실행 결과로 주장하지 않습니다. [전체 검증 범위](../../06_docs/validation.md).

## Dependencies

Python 3.11+, [requirements](../../requirements.txt), Docker 및 기존 이미지·template cache. 실행은 Linux AMD64이며 Mac emulation과 실제 소요 시간은 환경별 검증 대상입니다. [보존한 방법](METHODS.md), [문헌/적용 범위](literature.md), [통합·전환 안내](../../06_docs/xcpd_consolidation.md).
