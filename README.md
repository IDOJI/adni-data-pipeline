# 🧬 ADNI Data Pipeline

ADNI 자료를 modality별로 처리하고 검증하는 연구 파이프라인입니다. 현재 구현은 **[RS-fMRI](RS-fMRI/README.md)**이며, SNP 데이터 파이프라인은 추후 별도 모듈로 추가합니다.

| 영역 | 상태 | 안내 |
|---|---|---|
| RS-fMRI | 원본 submodule + Custom Step + 통합 실행 안내 구현, 합성 자료 검증·XCP-D 및 통합 영상 QC 구현 | [RS-fMRI/README.md](RS-fMRI/README.md) |
| SNP | 향후 추가 예정, 실행 코드 없음 | 구현 시 독립 폴더와 프로토콜 추가 |

```text
adni-data-pipeline/
├── README.md
├── .gitmodules
├── LICENSE
└── RS-fMRI/
    ├── 01_upstream/ADNI_fMRI_protocol/  # 원본 commit 고정
    ├── 02_custom/                      # 연구실 추가 단계
    ├── 03_config/                      # 설정 예시·버전 기록
    ├── 04_workflow/                    # 연결·설정·명령 계획
    ├── 05_tests/                       # 합성 자료 검증
    └── 06_docs/                        # 설치·업데이트·검증 안내
```

## 🚀 시작

```sh
git clone --recurse-submodules https://github.com/IDOJI/adni-data-pipeline.git
cd adni-data-pipeline/RS-fMRI
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python 04_workflow/lab.py doctor
python -m pytest -q
```

연구 자료와 개인 설정·결과는 저장소 밖에서 관리합니다. 이 공개 저장소에는 원본 ADNI 영상·임상표·SNP·실제 참가자 목록·인증정보를 넣지 않습니다. 코드 테스트의 성공과 전체 코호트의 연구 적합성은 구분합니다.

원본 출처와 추가 코드 안내는 [RS-fMRI/NOTICE.md](RS-fMRI/NOTICE.md), 라이선스는 [GPL-3.0](LICENSE)을 따릅니다.
