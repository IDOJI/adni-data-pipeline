# 🧠 RS-fMRI Pipeline

작업·수정 규칙: [Repository instructions.md](<Repository instructions.md>)

statMINDlab의 ADNI fMRI 프로토콜을 **Git Submodule로 버전 고정**하고, 연구실의 추가 과정은 `02_custom/`에 관리합니다. 이 README가 원본 Step과 Custom Step의 전체 실행 순서를 안내합니다.

- 원본: [statMINDlab/ADNI_fMRI_protocol](https://github.com/statMINDlab/ADNI_fMRI_protocol/tree/e8ed72ce1bd4e471a422ec4886ea536f5bb6f5c3)
- 고정 commit: `e8ed72ce1bd4e471a422ec4886ea536f5bb6f5c3` — [검증 범위·버전](03_config/versions.md)
- 원본의 데이터 선택·Clinica·MRIQC·fMRIPrep·기본 QC를 기본 흐름으로 사용합니다. 기존 Research Selection Table은 필수 입력이 아닙니다.
- 추가 단계는 독립 실행하며 입력·출력 경로로 연결합니다. 폴더 추가만으로 자동 실행되지 않습니다.
- 코드 검증과 합성 자료 검증을 완료한 초기 구현입니다. 전체 ADNI 코호트 전처리·연구 포함 판정 완료를 뜻하지 않습니다.

## 📁 구조

```text
RS-fMRI/
├── 01_upstream/ADNI_fMRI_protocol/  # 원본 commit을 가리키는 submodule
├── 02_custom/
│   ├── s3a_source_qc/            # 원본 QC·NFQ·삭제·식별 감사
│   ├── s5c_validate_handoff/     # Step 5 TSV → Step 6/7 입력 연결
│   ├── s7a_volume_workflow/     # 기존 Docker volume profile·감사·복구
│   ├── s8a_motion_duration_qc/    # 실제 FD·TR로 잔여 시간 검증
│   ├── s9a_validate_clinical/    # 촬영일·진단 동률·인구통계 대조
│   └── s10_xcpd_integrated_qc/   # S8 수집·XCP-D·ROI/FC·영상 QC·보관 gate
├── 03_config/                     # 개인 데이터가 없는 설정 예시·버전 lock
├── 04_workflow/                   # 버전 검사·외부 설정 생성·명령 계획
├── 05_tests/                      # 합성 자료 및 원본 호환성 검사
└── 06_docs/                       # 설치·자료 준비·단계 확장·업데이트
```

상위 번호 `01`–`06`은 폴더 분류 순서입니다. 실제 실행 순서는 아래 표의 Step 1–9와 Custom Step 위치를 따릅니다.

## 🚀 최초 설치

```sh
git clone --recurse-submodules https://github.com/IDOJI/adni-data-pipeline.git
cd adni-data-pipeline/RS-fMRI
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python 04_workflow/lab.py doctor
python -m pytest -q
```

이 환경은 연결 도구·테스트용입니다. Clinica, MRIQC, fMRIPrep, R과 Slurm/Apptainer 환경은 원본 지침에 따라 별도로 준비합니다. [설치 안내](06_docs/installation.md)를 확인하세요.

## 🗺️ 전체 실행 순서

| 순서 | 단계 | 코드 | 주요 입출력·완료 조건 |
|---|---|---|---|
| 1 | Account & Access | [원본 Step 1](https://github.com/statMINDlab/ADNI_fMRI_protocol/blob/e8ed72ce1bd4e471a422ec4886ea536f5bb6f5c3/s1_setup_account/README.md) | ADNI 이용 승인 |
| 2 | Download | [원본 Step 2](https://github.com/statMINDlab/ADNI_fMRI_protocol/blob/e8ed72ce1bd4e471a422ec4886ea536f5bb6f5c3/s2_download/README.md) | 원본 UI에서 영상·메타데이터·임상표 다운로드, collection CSV 보존 |
| 3 | Organize & Download QC | [원본 Step 3](https://github.com/statMINDlab/ADNI_fMRI_protocol/blob/e8ed72ce1bd4e471a422ec4886ea536f5bb6f5c3/s3_organize/README.md) | DICOM inventory와 다운로드 목록 대조 |
| **3.A** | **원본 QC·NFQ 검증** | [Custom](02_custom/s3a_source_qc/README.md) | 원본 표의 ID·날짜·UID·품질·삭제·NFQ 감사, 후속 5.C에 연결 |
| 4 | Clinica | [원본 Step 4](https://github.com/statMINDlab/ADNI_fMRI_protocol/blob/e8ed72ce1bd4e471a422ec4886ea536f5bb6f5c3/s4_clinica/README.md) | DICOM → BIDS, conversion_info 보존 |
| 4.B | Philips SliceTiming | [원본 Step 4b](https://github.com/statMINDlab/ADNI_fMRI_protocol/blob/e8ed72ce1bd4e471a422ec4886ea536f5bb6f5c3/s4b_slice_timing/README.md) | 먼저 dry-run, 실제 영상 식별·slice axis 대응 검토 |
| 5.A–B | Post-Clinica QC | [원본 Step 5](https://github.com/statMINDlab/ADNI_fMRI_protocol/blob/e8ed72ce1bd4e471a422ec4886ea536f5bb6f5c3/s5_post_clinica_qc/README.md) | mastersheet → final_heuristics.tsv |
| **5.C** | **입력 연결 검증** | [Custom](02_custom/s5c_validate_handoff/README.md) | 3.A 근거와 선택 BOLD를 대조, 실패·충돌 차단 및 pending 표시 후 6/7 입력 생성 |
| 6 | MRIQC | [원본 Step 6](https://github.com/statMINDlab/ADNI_fMRI_protocol/blob/e8ed72ce1bd4e471a422ec4886ea536f5bb6f5c3/s6_mriqc/README.md) | IQM·보고서 산출, Step-5 생존 세션으로 IQM 적합 범위 확인 |
| 7 | fMRIPrep | [원본 Step 7](https://github.com/statMINDlab/ADNI_fMRI_protocol/blob/e8ed72ce1bd4e471a422ec4886ea536f5bb6f5c3/s7_fmriprep/README.md) | 5.C의 세션 CSV를 명시 전달, 영상·confounds·보고서 생성 |
| **7.A** | **별도 Docker volume profile** | [Custom](02_custom/s7a_volume_workflow/README.md) | 기존 aCompCor profile·독립 감사·metadata 복구, 원본 7 및 S10과 다른 실행 경로 |
| 8 | Final QC | [원본 Step 8](https://github.com/statMINDlab/ADNI_fMRI_protocol/blob/e8ed72ce1bd4e471a422ec4886ea536f5bb6f5c3/s8_final_qc/README.md) | motion·Euler·MRIQC 및 포함·제외 사유 |
| **8.A** | **motion 잔여시간 검사** | [Custom](02_custom/s8a_motion_duration_qc/README.md) | 실제 TR×남은 frame, FD 비율, 초기 시점 제외 민감도와 mask |
| 9 | Clinical Merge | [원본 Step 9](https://github.com/statMINDlab/ADNI_fMRI_protocol/blob/e8ed72ce1bd4e471a422ec4886ea536f5bb6f5c3/s9_clinical_imaging_merge/README.md) | 원본 인지평가 연결·보고서 생성, 원본 출력 보존 |
| **9.A** | **임상정보 검증** | [Custom](02_custom/s9a_validate_clinical/README.md) | 실제 촬영일·최근접 진단 전부·28일 창·Dementia/의심 원인·PTDEMOG/APOE 검증 |
| **10** | **XCP-D·통합 영상 QC** | [Custom](02_custom/s10_xcpd_integrated_qc/README.md) | S7 완료 pair부터 S8 지표 → 잠정 후보 XCP-D → 검증·사람 검토 → 명시 cohort 최종화, 9.A link 생성 |

Step 1.A/1.B는 아직 확정된 처리 과정이 아니므로 생성하지 않았습니다. [Custom Step 추가 방법](06_docs/pipeline_guide.md)에 따라 필요한 시점에 추가합니다.

## 🧩 XCP-D 실행 순서

원본 1–7 → **S8/8.A + S10 pre-QC → XCP-D → 정량·시각 검토 → cohort 영상 QC finalize → S9/9.A 임상 검증** 순서로 연결합니다. S10은 S7 완료 pair부터 별도 worker로 시작할 수 있습니다. `watch/collect`는 최종 판정을 하지 않습니다. 실제 실행 명령·pair 입력 계약·외장 보관 gate는 [S10 README](02_custom/s10_xcpd_integrated_qc/README.md), 기존 폴더 정리와 서비스 전환 경계는 [통합 안내](06_docs/xcpd_consolidation.md)를 따릅니다.

7.A의 기존 aCompCor profile과 S10의 36P/GSR profile은 별도로 보존하며 같은 결과를 혼합하지 않습니다. S10 finalization의 `final_included_runs.tsv`와 `clinical_scan_links.tsv`를 9.A에 함께 전달합니다. 영상 QC만으로 전체 연구 포함을 확정하지 않습니다.

## 🔎 Research 규칙의 이식 범위

[검증 규칙 대응표](06_docs/research_validation_rules.md)에 원본 QC·NFQ·임상 코드에서 가져온 규칙과 별도 실영상 검증이 필요한 항목을 구분했습니다. 기존 RDS·다운로드 ID 목록을 중심 입력으로 만들지 않으며, 원본이 선택한 영상과 외부 원자료를 독립적으로 대조합니다.

3.A는 [실행 명령](02_custom/s3a_source_qc/README.md#execution)에 따라 실제 Study Files 경로를 명시합니다. 생성된 `step3a` artifact를 아래 5.C에 전달합니다. 파일명이나 Obsidian 경로를 자동 검색하지 않습니다.

## ⚙️ 설정과 연결

개인 설정은 `03_config/lab_config.local.yaml` 또는 저장소 밖에 보관하고, 데이터·결과는 전부 저장소 밖에 둡니다.

```sh
cp 03_config/lab_config.example.yaml 03_config/lab_config.local.yaml
# 실제 data/scratch/container/license 절대경로로 수정한 뒤 실행
python 04_workflow/lab.py prepare-config \
  --lab-config 03_config/lab_config.local.yaml \
  --output-dir /ABSOLUTE/PATH/ADNI_DATA/config/run-001
```

생성된 `upstream.yaml`은 원본 설정 schema를 유지하며 원본 `config/config_adni.yaml`을 수정하지 않습니다. Step 5.A/B는 다음과 같이 연결합니다. 아래 placeholder는 실제 경로로 바꿔야 합니다.

```sh
export ADNI_CONFIG=/ABSOLUTE/PATH/ADNI_DATA/config/run-001/upstream.yaml
export PYTHONPATH="$PWD/01_upstream/ADNI_fMRI_protocol${PYTHONPATH:+:$PYTHONPATH}"
export RSFMRI_ROOT="$PWD"
mkdir -p /ABSOLUTE/PATH/ADNI_DATA/qc/step5a
(cd /ABSOLUTE/PATH/ADNI_DATA/qc/step5a && python "$RSFMRI_ROOT/01_upstream/ADNI_fMRI_protocol/s5_post_clinica_qc/create_mastersheet/main.py" --config "$ADNI_CONFIG")
python 01_upstream/ADNI_fMRI_protocol/s5_post_clinica_qc/create_report/run_session_heuristics.py \
  --input-csv /ABSOLUTE/PATH/anchor_plus_dicom_nifti_struct.csv \
  --output-dir /ABSOLUTE/PATH/ADNI_DATA/qc/step5
python 02_custom/s5c_validate_handoff/run.py \
  --input /ABSOLUTE/PATH/ADNI_DATA/qc/step5/final_heuristics.tsv \
  --source-qc /ABSOLUTE/PATH/ADNI_DATA/qc/step3a \
  --output-dir /ABSOLUTE/PATH/ADNI_DATA/qc/step5c
python 04_workflow/lab.py prepare-config \
  --lab-config 03_config/lab_config.local.yaml \
  --handoff /ABSOLUTE/PATH/ADNI_DATA/qc/step5c \
  --output-dir /ABSOLUTE/PATH/ADNI_DATA/config/run-001-handoff
python 04_workflow/lab.py plan \
  --config /ABSOLUTE/PATH/ADNI_DATA/config/run-001-handoff/upstream.yaml \
  --handoff /ABSOLUTE/PATH/ADNI_DATA/qc/step5c
```

`plan`은 명령을 출력하며 작업을 제출하지 않습니다. 원본의 `--dry-run`은 job 파일을 생성할 수 있으므로 출력 명령을 실제로 실행하기 전에 경로와 Slurm 지시문을 검토합니다. 아직 전체 단계 자동 실행 기능은 없습니다.

Step 8 후 추가 검사:

```sh
python 02_custom/s8a_motion_duration_qc/run.py \
  --bids-root /ABSOLUTE/PATH/ADNI_DATA/rawdata \
  --derivatives-root /ABSOLUTE/PATH/ADNI_DATA/derivatives/fmriprep \
  --output-dir /ABSOLUTE/PATH/ADNI_DATA/qc/motion-duration-run-001
```

8.A는 QC 근거를 생성하며 원본 포함표나 영상 시점을 자동 변경하지 않습니다. Step 8의 `--valid-sessions`에는 5.C의 `valid_sessions.tsv`를 전달해 5.C에서 차단한 세션의 재진입을 방지합니다. 8.A·시각 QC 등의 실패·보류를 반영한 별도의 검토 완료 포함표를 Step 9/9.A에 전달합니다.

Step 9.A의 임상 검증은 다음처럼 실행합니다. `--included`는 위 검토 완료 포함표이고, `--scan-links`는 원본 fMRI mastersheet 또는 같은 식별정보의 명시적 CSV입니다.

```sh
python 02_custom/s9a_validate_clinical/run.py \
  --included /ABSOLUTE/PATH/ADNI_DATA/qc/final/included_reviewed_sessions.tsv \
  --scan-links /ABSOLUTE/PATH/ADNI_DATA/qc/step5a/data/anchor_plus_dicom_nifti_struct.csv \
  --dxsum /ABSOLUTE/PATH/ADNI_DATA/LONI_download/clindata/DXSUM.csv \
  --ptdemog /ABSOLUTE/PATH/ADNI_DATA/LONI_download/clindata/PTDEMOG.csv \
  --max-dx-days 28 --dx-direction nearest \
  --output-dir /ABSOLUTE/PATH/ADNI_DATA/qc/step9a
```

APOE/ADSL/DM은 각각 `--apoe`, `--adsl`, `--dm`으로 선택 연결합니다. `clinical_validation.tsv`에는 입력 run 모두와 pass/hold 사유를 보존하고, 임상 조건을 통과한 run은 `clinically_validated_sessions.tsv`에 추가 저장합니다. 임상 pass만으로 분석 준비 완료를 선언하지 않습니다.

## ⚠️ 현재 적용 경계

- 원본 지원은 ADNI GO/2/3입니다. ADNI4는 별도 확장 검증 대상입니다.
- 원본 Step 6 launcher는 참가자 단위로 실행합니다. 5.C의 CSV 연결은 구분자·중복 참가자를 해결하며 **세션 제한을 추가하지 않습니다**. outlier 적합 전 group IQM을 `valid_sessions.tsv`와 대조·제한해야 합니다.
- 원본 Step 8의 IQM 입력은 기본 CSV reader를 사용합니다. s6의 TSV를 바로 넘기지 말고 구분자를 확인한 CSV를 별도로 준비합니다. QC 결측은 연구 포함으로 해석하지 않습니다.
- 원본 Step 9의 `DIAGNOSIS=3 → AD` 표기는 현행 DXSUM Dementia 정의와 구분해야 합니다. `build_imaging_input.py --max-dx-days`와 후속 `--max-days`는 각각 명시합니다. 이후 분석의 진단은 9.A의 원자료 검증 결과를 사용하며, 원본 Step 9 보고서의 AD 표기를 임상 AD/생물학적 AD 확정으로 해석하지 않습니다.
- 5.C source QC gate는 선택 BOLD의 ID·날짜·UID에 적용됩니다. T1의 실제 참조 연결·영상 header/ST 축·coverage/시각 QC는 별도 검증 대상입니다. source QC가 없는 기존 형식 검증만의 사용도 가능하지만 source QC 완료로 표시하지 않습니다.
- Mac volume 파일럿·XCP-D 코드는 7.A/S10 custom으로 통합했습니다. S10은 참조 스레드의 게시 완료 pair layout을 요구하며 평면형 Slurm 결과나 FreeSurfer 없는 7.A 결과를 자동 변환하지 않습니다. 8.A의 300초와 XCP-D의 240초 기준은 별도로 기록합니다.
- [설치·Mac 제한](06_docs/installation.md), [자료 준비](06_docs/data_preparation.md), [검증 결과](06_docs/validation.md), [원본 업데이트](06_docs/update_guide.md)를 확인하세요.

## 🔄 검증된 버전으로 업데이트

초기 무번호 구조를 사용 중인 기존 clone은 먼저 [일회성 전환 안내](06_docs/update_guide.md#초기-무번호-구조에서-한-번만-전환)를 따릅니다.

```sh
git pull --ff-only
git submodule update --init --recursive
python 04_workflow/lab.py doctor
```

위 명령은 상위 저장소가 기록한 commit으로 맞춥니다. 새 원본 버전 채택은 [업데이트 안내](06_docs/update_guide.md)의 별도 테스트 브랜치에서 진행합니다. [Git 공식 submodule 문서](https://git-scm.com/docs/gitsubmodules)의 gitlink 방식으로 관리합니다.

## 📚 출처와 라이선스

원본 저자와 protocol의 인용은 submodule의 [CITATION.cff](https://github.com/statMINDlab/ADNI_fMRI_protocol/blob/e8ed72ce1bd4e471a422ec4886ea536f5bb6f5c3/CITATION.cff)를 따릅니다. 추가 코드의 출처는 [NOTICE](NOTICE.md), 원본과 호환되는 GPL-3.0 조건은 [LICENSE](../LICENSE)에 기록했습니다. ADNI 원본 데이터는 재배포하지 않습니다.
