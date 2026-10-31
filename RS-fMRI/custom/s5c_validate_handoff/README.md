# Step 5.C — 원본 Step 5와 Step 6/7의 입력 연결

## Purpose

원본은 Step 5 결과를 TSV로 쓰지만 Step 6 launcher는 쉼표 CSV를 읽습니다. 이 단계는 **원본에서 이미 통과한 세션**을 형식 검증 후 전달합니다. Research의 과거 Selection Table이나 새 임상 선별은 사용하지 않습니다.

## Input

- 원본 `final_heuristics.tsv`: 필수 `Subject_ID`, `VISCODE`.
- `NIfTI_exists`, `JSON_exists`, `T1w_exists`가 있으면 모두 true여야 합니다.
- `bl`, `mNN`, `MNNN`, `ses-MNNN`을 Clinica 세션으로 정규화합니다. screening·달력 날짜를 방문코드로 추측하지 않습니다.

## Processing

입력 전체를 먼저 검증하고 중복 정규화 세션·비정상 ID·빈 입력·모순된 존재 flag를 거절합니다. 세션을 임의 삭제하거나 대표 run을 고르지 않습니다. 같은 세션에 여러 run이 있으면 명시적인 추가 설계가 필요합니다.

## Output

| 파일 | 역할 |
|---|---|
| `mriqc_subjects.csv` | Step 6용 참가자당 한 행, 쉼표 구분 |
| `post_clinica.csv` | Step 7용 `Subject_ID,sessions`, 공백 구분 `M000 M012` |
| `mriqc_sessions.csv` | Step 7 `--sessions-csv`에 전달할 `Subject_ID,VISCODE` |
| `valid_sessions.tsv` | 통과한 BIDS `sub,ses` 대조용 |
| `handoff.json` | 입력·출력 hash와 범위, 연구 포함 미판정 상태 |

**MRIQC 원본 launcher는 세션 필터를 전달하지 않습니다.** 같은 참가자의 다른 BIDS 세션이 처리될 수 있으므로 group IQM의 적합 모집단을 별도로 확인해야 합니다. 이 변환만으로 세션 제한이 된다고 해석하지 않습니다.

## Execution

root README의 `python custom/s5c_validate_handoff/run.py --input ... --output-dir ...` 사용 후 `prepare-config --handoff ...`로 새로운 외부 설정을 생성합니다. Step 7 명령에는 `--sessions-csv .../mriqc_sessions.csv`도 명시합니다.

## Validation

원본 입력 hash 불변, 참가자·세션의 일대일 보존, CSV를 원본 Step 7 parser로 읽은 결과와의 일치, 기존 출력 거절을 테스트합니다. 완료는 형식 검증이며 새로운 품질 통과 판정이 아닙니다.

## Dependencies

Python 3.11+ 표준 라이브러리. 이 단계 자체는 MRI 파일·RDS·개인 설정을 읽지 않습니다.
