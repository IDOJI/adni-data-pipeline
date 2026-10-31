# 초기 구현 검증 — 2026-10-31

## 완료한 범위

- 자체 테스트: **20 passed**. 원본 Step-5 TSV 정규화·중복·결측·존재 flag·빈 목록·출력 경로, 원본 Step-7 parser round-trip, 원본 Step-6 실제 launcher dry-run 포함.
- 고정 원본의 `utils/tests`: **60 passed, 1 skipped**. wrapper 테스트와 분리해 실행. skip은 원본 테스트의 환경 조건에 따른 것이며 wrapper 검증 완료 수에 포함하지 않음.
- motion 검사: 합성 4D NIfTI·JSON·confounds로 300초/30% 경계, 초기 시점 제외 민감도, FD 결측, TR 대응, hash와 원본 frame index 보존, 덮어쓰기 방지 확인.
- submodule: gitlink·lock·실제 HEAD 일치와 원본 checkout clean 확인.
- 설정: 외부 경로 생성, 원본 설정 불변, placeholder·저장소 내부 출력 거절, Step-5.C 출력 hash가 바뀌면 새 설정 생성 중단.

## 테스트 환경

Python 3.11.16 / NumPy 2.4.6 / pandas 3.1.0 / NiBabel 5.4.2 / PyYAML 6.0.3 / pytest 9.2.0. 원본 shell이 실행하는 `python`도 같은 환경을 사용하도록 PATH를 맞춰 실행했다.

처음에는 pytest가 submodule 테스트까지 자동 수집하고 shell에서 다른 Python을 사용해 PyYAML import가 실패했다. 자체 테스트 탐색 경로를 `tests/`로 한정하고 원본 테스트는 올바른 PATH에서 별도로 다시 실행해 위 결과를 확인했다.

```sh
# RS-fMRI 가상환경 활성화 후
python -m pytest -q
python -m pytest -q upstream/ADNI_fMRI_protocol/utils/tests
python workflow/lab.py doctor
```

## 완료하지 않은 범위

새 저장소에서 실제 ADNI 자료 다운로드, DICOM 변환, MRIQC·fMRIPrep 전체 코호트 실행, MRIQC 적합 모집단/시각 QC, 임상 mapping 보완, SNP 처리, Mac 전체 adapter 검증은 수행하지 않았다. Step-6 dry-run은 synthetic 디렉터리·CSV만 사용하며 container를 실행하거나 영상을 처리한 결과가 아니다.

GitHub Actions에는 Python 3.11/3.12 합성 검증을 구성했다. 원격 CI의 실행 결과는 로컬 통과 결과와 별도로 확인한다.
