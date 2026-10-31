# 단계 확장과 연결

## 추가 위치

원본 Step 이후 필요한 단계만 생성합니다. 예: s3 이후 `custom/s3a_*`, s5 내부 5a/5b 이후 `custom/s5c_*`, s7 이후 `custom/s7a_*`. root RS-fMRI README의 순서표도 같은 작업에서 수정합니다.

## 각 Custom Step의 필수 내용

README에 Purpose, Input, Processing, Output, Execution, Validation, Dependencies를 적습니다. 코드·연구적 기준·합성 테스트를 함께 관리하고, 결과는 입력 tree와 겹치지 않는 외부 폴더에 씁니다.

독립 보고 단계는 새 결과만 생성합니다. 대상자·세션·영상·포함표를 바꾸는 단계는 다음 원본 Step의 실제 입력 옵션을 확인하고 adapter와 계약 테스트를 추가합니다. `prepare-config`가 모든 script의 하드코딩을 해결한다고 가정하지 않습니다.

## 구현된 연결

- 5.C: 원본 final_heuristics.tsv의 모든 세션을 검증하고 Step 6 쉼표 CSV와 Step 7 세션 CSV로 연결. 추가 임상 선별 없음.
- 8.A: 기존 로컬 motion-duration QC의 코드 재사용. upstream 최종 표와 자동 결합하지 않으므로 실패·보류 run의 연구 포함 판정을 별도로 기록.
- `workflow/lab.py plan`: 알려진 실행 진입점의 명령을 출력. 자동 단계 실행·스케줄 제출·오류 복구를 구현한 orchestration engine은 아님.

## 아직 해결하지 않은 원본 경계

MRIQC 세션별 실행·적합 모집단 제한, 원본 s8 결측 판정과 TSV 입력, 임상 diagnosis mapping·날짜창·동률 처리, Mac 전체 adapter는 후속 단계입니다. 현재 코드의 테스트 성공을 이러한 기능의 완료로 표시하지 않습니다.
