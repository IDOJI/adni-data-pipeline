# 설치와 실행 환경

## Wrapper와 Custom Step

root README의 recursive clone 후 `RS-fMRI/`에서 Python 3.11+ 가상환경을 만들고 `requirements.txt`를 설치합니다. `doctor`는 gitlink·lock·원본 checkout·dirty 상태를 대조합니다.

## 원본 환경

원본의 `env/env_adni.yml`, `env/env_clinica.yml`, R 패키지와 Apptainer/Slurm 구성을 따릅니다. 이 저장소의 requirements는 Clinica·MRIQC·fMRIPrep 실행 환경을 대신하지 않습니다. container·template 수신은 여러 GB가 될 수 있으며 설치 단계와 분리합니다.

`03_config/lab_config.example.yaml`의 이미지명은 기존 로컬 검사에서 사용한 MRIQC 24.0.2·fMRIPrep 25.2.7을 명시한 예시입니다. 원본 commit의 예시 24.0.0과 구분합니다. 실제 이미지 digest와 명령은 실행별 provenance에 보존해야 합니다.

## Mac

Custom Step과 설정 도구는 Mac에서 테스트합니다. 원본 s4/s6/s7 launcher는 Slurm/Apptainer용이며 Mac용으로 자동 변환하지 않습니다. 기존 `local_mac` 파일럿은 원본에서 추적되지 않는 별도 로컬 확장이므로 submodule에 자동 포함되지 않습니다. 7.A에 별도 volume Docker 실행·감사 profile, S10에 완료 pair 후처리·통합 QC를 추가했습니다. 기존 local_mac 전체와 S6/S7 queue는 통합되지 않았으며, 평면 결과에서 S10 pair 계약으로의 자동 adapter도 별도입니다. [통합 범위](xcpd_consolidation.md)를 확인합니다.

## 출력 위치

`prepare-config`는 저장소 밖에만 결과를 씁니다. s5.A는 현재 작업 폴더에 `data/`를 쓰므로 외부 `ADNI_DATA/qc/step5a/`에서 실행합니다. s4의 원본 Slurm template에는 하드코딩 경로·환경·메일 지시문이 있으므로 그대로 제출하지 말고 외부 연구실 template에서 실제 경로·계정·modality·알림 정책을 확인합니다.
