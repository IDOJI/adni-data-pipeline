# XCP-D 코드 통합과 운영 전환

## 코드 정본

| 원래 구현 | 통합 위치 | 처리 |
|---|---|---|
| adni-rsfmri-pipeline의 volume 실행·복구·감사·영상 QA | 02_custom/s7a_volume_workflow | aCompCor 별도 profile 유지 |
| 해당 폴더의 tests·METHODS·literature | 05_tests/volume_workflow 및 7.A 문서 | 합성 ID·외부 경로 예시로 변환 |
| 참조 스레드의 로컬 S10 | 02_custom/s10_xcpd_integrated_qc | 최신 36P/LINC 후처리·통합 영상 QC |
| continuous5의 검증 후 외장 이동기 | S10/offload_completed.py | 코드와 runtime settings 분리, config_id/hash gate 유지 |
| 실제 config·실제 대상 실행 결과·검증 로그, one-case staging/migration | 비공개 로컬 원본 보관본 | 공개 소스에서 제외, 원본 복원용 보존 |

`03_config/imported_sources.json`에 원본 코드 hash와 이식 위치를 기록합니다. 기존 fMRIPrep·XCP-D 영상은 이동하거나 재계산하지 않습니다. 원래 2방문 파일럿 완료 기록과 현재 SB pilot 진행 상태는 서로 다른 실행입니다.

## 현재 worker와의 관계

통합 시점의 기존 XCP-D worker는 별도 로컬 ADNI_fMRI_protocol의 S10 코드를, 외장 이동 worker는 기존 runtime의 frozen offloader를 사용 중입니다. 이들은 진행 중 attempt의 재현성을 위해 해당 소스·config_id·cache·컨테이너를 유지합니다. 새 저장소를 설치했다고 서비스를 재시작하거나 다음 대상으로 새 설정을 강제하지 않습니다.

새 통합본은 `repo=null`을 parent가 고정한 submodule로 해석하고 명시적인 외부 config를 요구합니다. 그 경로 변경도 config_id에 반영되므로 기존 worker의 configuration과 cache를 같은 것으로 가장하지 않습니다. 새 연구 runtime으로 전환할 때 기존 attempt를 완료·증빙 보존한 뒤 새 root/config로 preflight → dry-run → pilot을 검증합니다. 기존 watch가 계속 관리 중인 root에서 두 번째 watch를 실행하지 않습니다.

기존 adni-rsfmri-pipeline 경로는 원본 파일 전체를 로컬 archive로 보존·hash 검증한 뒤 7.A 코드로 연결하는 호환 symlink로 정리합니다. 실제 원본 config와 전용 staging/migration의 위치는 공개 저장소가 아닌 private migration manifest를 따릅니다. symlink는 source 파일 경로 호환용이며 이전 개인 config를 자동 선택하는 동작은 제거했습니다.

## 실행 순서와 연구 판정

원본 1–7 → S8/8.A 지표·검토와 S10 pre-QC → 잠정 후보 XCP-D → collect·사람 검토 → cohort 기반 S10 영상 QC finalize → S9/9.A 임상 검증 → 연구별 source/영상/임상 포함 조건 대조.

S10은 S7 완료 pair부터 독립적으로 시작할 수 있습니다. S9 임상 연결도 별도로 수행할 수 있으며, S10 최종 영상 목록이 바뀌면 해당 run 목록으로 9.A를 다시 검증합니다. 단계 번호는 파일 역할 식별이며 숫자대로만 실행해야 한다는 뜻이 아닙니다.

9.A 연결 예시의 두 파일은 동일한 S10 finalization 폴더에서 선택합니다:

```sh
python 02_custom/s9a_validate_clinical/run.py \
  --included /ABSOLUTE/PATH/finalization/final_included_runs.tsv \
  --scan-links /ABSOLUTE/PATH/finalization/clinical_scan_links.tsv \
  --dxsum /ABSOLUTE/PATH/DXSUM.csv --ptdemog /ABSOLUTE/PATH/PTDEMOG.csv \
  --output-dir /ABSOLUTE/PATH/clinical/run-001
```

## 아직 일반화하지 않은 범위

S6/S7 실시간 queue와 raw zip staging, 평면 derivatives → 게시 완료 pair adapter, 실제 cohort 연구 포함표의 source QC/8.A/임상 교집합 자동화, Slurm/CIFTI 실제 계산 검증은 별도입니다. 현 pair receipt 계약을 우회하거나 metadata만 만들어 기존 계산을 성공으로 표시하지 않습니다. 7.A(FreeSurfer 없음)와 S10(Euler 필수)은 직접 이어지는 호환 profile이 아닙니다.
