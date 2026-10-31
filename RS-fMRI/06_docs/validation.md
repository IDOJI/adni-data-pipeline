# 초기 구현 검증 — 2026-10-31

## 완료한 범위

- 자체 테스트: **20 passed**. 원본 Step-5 TSV 정규화·중복·결측·존재 flag·빈 목록·출력 경로, 원본 Step-7 parser round-trip, 원본 Step-6 실제 launcher dry-run 포함.
- 고정 원본의 `utils/tests`: **60 passed, 1 skipped**. wrapper 테스트와 분리해 실행. skip은 원본 테스트의 환경 조건에 따른 것이며 wrapper 검증 완료 수에 포함하지 않음.
- motion 검사: 합성 4D NIfTI·JSON·confounds로 300초/30% 경계, 초기 시점 제외 민감도, FD 결측, TR 대응, hash와 원본 frame index 보존, 덮어쓰기 방지 확인.
- submodule: gitlink·lock·실제 HEAD 일치와 원본 checkout clean 확인.
- 설정: 외부 경로 생성, 원본 설정 불변, placeholder·저장소 내부 출력 거절, Step-5.C 출력 hash가 바뀌면 새 설정 생성 중단.

## 테스트 환경

Python 3.11.16 / NumPy 2.4.6 / pandas 3.1.0 / NiBabel 5.4.2 / PyYAML 6.0.3 / pytest 9.2.0. 원본 shell이 실행하는 `python`도 같은 환경을 사용하도록 PATH를 맞춰 실행했다.

처음에는 pytest가 submodule 테스트까지 자동 수집하고 shell에서 다른 Python을 사용해 PyYAML import가 실패했다. 자체 테스트 탐색 경로를 `05_tests/`로 한정하고 원본 테스트는 올바른 PATH에서 별도로 다시 실행해 위 결과를 확인했다.

```sh
# RS-fMRI 가상환경 활성화 후
python -m pytest -q
python -m pytest -q 01_upstream/ADNI_fMRI_protocol/utils/tests
python 04_workflow/lab.py doctor
```

## 완료하지 않은 범위

새 저장소에서 실제 ADNI 자료 다운로드, DICOM 변환, MRIQC·fMRIPrep 전체 코호트 실행, MRIQC 적합 모집단/시각 QC, 임상 mapping 보완, SNP 처리, Mac 전체 adapter 검증은 수행하지 않았다. Step-6 dry-run은 synthetic 디렉터리·CSV만 사용하며 container를 실행하거나 영상을 처리한 결과가 아니다.

GitHub Actions에는 Python 3.11/3.12 합성 검증을 구성했다. 원격 CI의 실행 결과는 로컬 통과 결과와 별도로 확인한다.


## 2026-11-01 폴더 번호화 검증

`01_upstream`·`02_custom`·`03_config`·`04_workflow`·`05_tests`·`06_docs`로 경로를 통일했습니다. 자체 테스트는 경로·문서 링크·CI/pytest 설정·개인 설정 제외·imported code hash 검사를 포함해 **23 passed**입니다. 고정 upstream commit은 변경하지 않았으며 원본 소스 내부의 `config/`, `utils/tests`와 외부 ADNI_DATA의 `config/` 명칭은 원래 규약을 따릅니다.


## 2026-11-01 Research QC·임상정보 검증 추가

원본 Study Files QC/NFQ 감사 3.A, 선택 BOLD에 적용하는 5.C source gate, run별 실제 날짜·임상정보 검증 9.A를 구현했습니다. 자체 테스트 **57 passed**로 실제 원본 Step-6 dry-run·Step-7 parser 호환성 외에 native CLI·source hash·실패 차단·pending 보존·동률·반복 방문·인구통계 결측·식별 충돌을 확인했습니다.

원본 코드의 입력 규약을 합성 CSV/NIfTI로 검증한 결과입니다. Research 원본 CSV/RDS·실영상 전체를 새 저장소에서 처리한 결과가 아니며, source QC pass·clinical pass를 전체 연구 포함 완료로 해석하지 않습니다. source QC와 임상 구현의 이식/미이식 범위는 `research_validation_rules.md`를 참고합니다.

## 2026-11-01 XCP-D 코드 통합

7.A Docker volume 실행·감사·metadata 복구·영상 QA, S10 S8 수집·36P/LINC XCP-D·ROI/FC/coverage·통합 영상 QC·검증 후 외장 보관 코드를 이식했습니다. 자체 **193 passed, 17 subtests passed**입니다. 원래 테스트를 합성 참가자·외부 설정으로 이식하고 명시 config 요구·pinned upstream·외부 runtime 보호·두 profile 분리·9.A 연결을 추가 검증했습니다.

컨테이너 재연결/실패 복구와 외장 단절·손상·중단 복구는 합성 파일 및 모의 subprocess로 검사했습니다. 실제 Docker 영상 계산이나 실제 외장 이동을 이번 통합에서 재실행한 결과가 아닙니다. 진행 중인 SB pilot과 과거 2방문 volume pilot의 실제 실행 증빙은 각각 기존 private runtime/로컬 archive에 보존합니다. 현재 worker의 완료를 이번 코드 테스트로 대신 판정하지 않습니다.

기존 원본 submodule commit은 유지하며 7.A(FreeSurfer 없음)·S10(Euler 필수)의 입력 계약 차이를 문서화했습니다. Linux/Slurm·CIFTI 실제 계산, 평면형 derivatives → 게시 pair adapter, source QC/8.A/임상 조건과의 연구 포함표 자동 교집합은 미검증/미구현 범위입니다.
