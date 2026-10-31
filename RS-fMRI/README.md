# 🧠 RS-fMRI Pipeline

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
│   ├── s5c_validate_handoff/     # Step 5 TSV → Step 6/7 입력 연결
│   └── s8a_motion_duration_qc/  # 실제 FD·TR로 잔여 시간 검증
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
| 1 | Account & Access | [원본 Step 1](01_upstream/ADNI_fMRI_protocol/s1_setup_account/README.md) | ADNI 이용 승인 |
| 2 | Download | [원본 Step 2](01_upstream/ADNI_fMRI_protocol/s2_download/README.md) | 원본 UI에서 영상·메타데이터·임상표 다운로드, collection CSV 보존 |
| 3 | Organize & Download QC | [원본 Step 3](01_upstream/ADNI_fMRI_protocol/s3_organize/README.md) | DICOM inventory와 다운로드 목록 대조 |
| 4 | Clinica | [원본 Step 4](01_upstream/ADNI_fMRI_protocol/s4_clinica/README.md) | DICOM → BIDS, conversion_info 보존 |
| 4.B | Philips SliceTiming | [원본 Step 4b](01_upstream/ADNI_fMRI_protocol/s4b_slice_timing/README.md) | 먼저 dry-run, 실제 영상 식별·slice axis 대응 검토 |
| 5.A–B | Post-Clinica QC | [원본 Step 5](01_upstream/ADNI_fMRI_protocol/s5_post_clinica_qc/README.md) | mastersheet → final_heuristics.tsv |
| **5.C** | **입력 연결 검증** | [Custom](02_custom/s5c_validate_handoff/README.md) | TSV 검증, 참가자·세션 CSV와 형식별 입력 생성; 추가 임상 선별 없음 |
| 6 | MRIQC | [원본 Step 6](01_upstream/ADNI_fMRI_protocol/s6_mriqc/README.md) | IQM·보고서 산출, Step-5 생존 세션으로 IQM 적합 범위 확인 |
| 7 | fMRIPrep | [원본 Step 7](01_upstream/ADNI_fMRI_protocol/s7_fmriprep/README.md) | 5.C의 세션 CSV를 명시 전달, 영상·confounds·보고서 생성 |
| 8 | Final QC | [원본 Step 8](01_upstream/ADNI_fMRI_protocol/s8_final_qc/README.md) | motion·Euler·MRIQC 및 포함·제외 사유 |
| **8.A** | **motion 잔여시간 검사** | [Custom](02_custom/s8a_motion_duration_qc/README.md) | 실제 TR×남은 frame, FD 비율, 초기 시점 제외 민감도와 mask |
| 9 | Clinical Merge | [원본 Step 9](01_upstream/ADNI_fMRI_protocol/s9_clinical_imaging_merge/README.md) | 연구 기준을 충족한 포함표만 임상 연결, 진단·날짜창 재검토 |

Step 1.A/1.B/3.A/7.A는 아직 확정된 처리 과정이 아니므로 생성하지 않았습니다. [Custom Step 추가 방법](06_docs/pipeline_guide.md)에 따라 필요한 시점에 추가합니다.

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

8.A는 QC 근거를 생성하며, 원본 포함표나 영상 시점을 자동 변경하지 않습니다. 8.A에서 실패·보류한 run은 최종 연구 포함표에서 명시적으로 처리한 뒤 Step 9에 전달해야 합니다.

## ⚠️ 현재 적용 경계

- 원본 지원은 ADNI GO/2/3입니다. ADNI4는 별도 확장 검증 대상입니다.
- 원본 Step 6 launcher는 참가자 단위로 실행합니다. 5.C의 CSV 연결은 구분자·중복 참가자를 해결하며 **세션 제한을 추가하지 않습니다**. outlier 적합 전 group IQM을 `valid_sessions.tsv`와 대조·제한해야 합니다.
- 원본 Step 8의 IQM 입력은 기본 CSV reader를 사용합니다. s6의 TSV를 바로 넘기지 말고 구분자를 확인한 CSV를 별도로 준비합니다. QC 결측은 연구 포함으로 해석하지 않습니다.
- 원본 Step 9의 `DIAGNOSIS=3 → AD` 표기는 현행 DXSUM Dementia 정의와 구분해야 합니다. `build_imaging_input.py --max-dx-days`와 후속 `--max-days`는 각각 명시합니다. 아직 임상 mapping을 대체하는 Custom Step은 없습니다.
- 초기 Mac 파일럿과 별도 XCP-D 코드는 이 submodule에 포함되지 않습니다. 기존 파일럿을 완성된 전체 코호트 adapter로 소개하지 않으며, 240초 등 다른 프로젝트 기준을 이 300초 검사에 섞지 않습니다.
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

원본 저자와 protocol의 인용은 submodule의 [CITATION.cff](01_upstream/ADNI_fMRI_protocol/CITATION.cff)를 따릅니다. 추가 코드의 출처는 [NOTICE](NOTICE.md), 원본과 호환되는 GPL-3.0 조건은 [LICENSE](../LICENSE)에 기록했습니다. ADNI 원본 데이터는 재배포하지 않습니다.
