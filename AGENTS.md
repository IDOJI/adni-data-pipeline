# Repository instructions

- 공개 ADNI modality별 소스 저장소다. 현재 구현은 `RS-fMRI/`, SNP는 향후 별도 모듈로 추가한다.
- 작업 전 해당 modality의 `AGENTS.md`와 README를 읽는다. 원본 submodule 코드를 직접 수정하지 않는다.
- 원본 영상·임상표·유전자료·실제 참가자 ID·개인 설정·실행 결과·라이선스 키·인증정보를 커밋하지 않는다. 예시는 합성 자료만 사용한다.
- 기존 Selection Table 중심 흐름을 추가하지 않는다. 원본 단계와 독립 Custom Step, 통합 README 구조를 유지한다.
- 테스트 명령은 `cd RS-fMRI` 후 `python -m pytest -q`, `python 04_workflow/lab.py doctor`.
- submodule 업데이트는 명시적인 검토와 호환성 테스트 이후 고정한다. 설치 과정은 상위 gitlink에 기록된 버전만 사용한다.
