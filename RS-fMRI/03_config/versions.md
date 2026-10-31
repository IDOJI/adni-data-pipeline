# 버전과 검증 범위

| 구성 | 초기 고정·기준 | 상태 |
|---|---|---|
| upstream | `e8ed72ce1bd4e471a422ec4886ea536f5bb6f5c3` | 기존 검토한 로컬 commit, 원격 최신 자동 채택 없음 |
| wrapper | 0.1.0, 2026-10-31 | submodule·설정·형식 연결과 합성 테스트 |
| motion-duration | 기존 local_mac 검사 코드 | 초기 byte-identical import, source hash 별도 기록 |
| 예시 MRIQC | 24.0.2 | 실제 설치·실행·digest 확인은 사용자 환경별 별도 |
| 예시 fMRIPrep | 25.2.7 | 실제 설치·실행·digest 확인은 사용자 환경별 별도 |
| 전체 코호트 | 미실행 | 연구 포함·제외 판정 미완료 |

원본 commit의 환경 예시와 wrapper 테스트 환경은 다릅니다. upstream lock과 `06_docs/validation.md`를 함께 확인합니다. 과거 별도 프로젝트의 fMRIPrep→XCP-D 240초 기준은 이 300초 검사의 설정이 아닙니다.
