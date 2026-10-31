# Repository instructions

- 원본 `01_upstream/ADNI_fMRI_protocol`은 고정 commit의 submodule이다. 호환성 보완은 `02_custom/` 또는 `04_workflow/`에서 구현한다.
- 이 저장소의 기본 흐름은 upstream s1–s9다. 과거 Research Selection Table을 실행의 필수 입력이나 선택의 정본으로 추가하지 않는다.
- 실행 순서와 각 Custom Step의 입력·출력·검증 조건은 root README와 해당 단계 README에 함께 갱신한다.
- 데이터·임상 원본·실제 참가자 ID 목록·개인 설정·실행 결과·라이선스 파일은 저장소 밖에 둔다. 예시는 합성 자료만 사용한다.
- 원본 업데이트는 테스트 브랜치에서 gitlink·lock·문서·호환성 테스트를 함께 검토한다. 자동 `--remote` 갱신을 설치 과정에 넣지 않는다.
- 명령 계획과 실행 완료, 기술 검증과 연구 포함 판정을 구분한다. 전체 MRIQC·fMRIPrep 실행은 별도 요청과 실제 환경 확인 후 진행한다.
- 검증: `python -m pytest -q`, `python 04_workflow/lab.py doctor`. 기존 upstream 작업 사본과 데이터는 수정하지 않는다.
