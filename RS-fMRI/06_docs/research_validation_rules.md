# Research 규칙과 Custom Step 대응

현재 기준은 Research의 `2026-10-30-preserve-all-v1`입니다. 공개 저장소에는 원본 데이터·RDS·실제 참가자 예시·개인 경로를 복사하지 않고 처리 규칙과 코드 출처 hash만 기록합니다.

| Research 규칙 | 구현 위치 | 현재 동작 |
|---|---|---|
| 원본 QC·삭제·판정 충돌 | 3.A | 원본 Image ID/날짜/PTID/UID 대조, 차단 상태 감사 |
| GO/2 ID 결측·NFQ 대응 | 3.A | 유일한 합성 식별만 사용, 명시 ID 충돌은 우회하지 않음 |
| NFQ 품질과 ST 유무 분리 | 3.A | 빈 ST에서도 실패 검사, ST는 QC 통과의 대체 근거가 아님 |
| 미확인 품질 보존 | 3.A/5.C | pending 별도 표시; 기본 전처리 후보 보존, 엄격 mode 선택 가능 |
| 확인된 문제 영상 재진입 방지 | 5.C → 6/7/8 | source QC gate의 생존 목록을 config/세션 필터 및 final valid-sessions에 연결 |
| 실제 MRI 촬영일 연결 | 9.A | 날짜/영상/phase 다중 후보는 hold, 행 순서로 날짜를 고르지 않음 |
| DXSUM 날짜 차이·동률 | 9.A | 기본 28일, nearest/past 선택, 모든 최근접 원본 행 보존 |
| Dementia와 임상 원인 구분 | 9.A | 코드 3은 Dementia, 일치한 원인 code만 suspected 표기 |
| PTDEMOG·APOE·성별 | 9.A | 날짜 동률·보조 source 충돌·부분 결측을 미확인으로 보존, complete-case 제외 없음 |
| 여러 방문·여러 run 보존 | 9.A | 입력 run별 결과, 정확한 image/run 대응 요구, 임상 평가 재사용 가능 |
| Search Age와 PTDOB 점검 | 9.A | 명시 scan-link Age와 월 단위 근사 나이 대조, 생년월일 충돌 표시 |

## 별도 검증이 필요한 항목

- 원본 BIDS와 DICOM/UID의 실제 파일 대응, NIfTI header/hash와 SliceTiming 축·방향은 물리 검증 대상입니다. 3.A의 metadata pass가 이를 입증하지 않습니다.
- T1 참조 영상의 실제 선택·여러 T1 조합·다른 날짜 T1 대응은 5.C source BOLD gate에서 확정하지 않습니다.
- Research의 QC1 sequence-description 제외 목록, 알려진 변환 실패 목록·ST 확정 결측 제외, 과거 PTDOB RDS snapshot 정책은 이번 단계에 자동 이식하지 않았습니다. 원본 처리와 실제 source에 맞는 별도 검증이 필요합니다.
- 원본 Step 6의 참가자 실행 범위, IQM 적합 모집단 제한, 원본 s8의 결측 판정/입력 구분자 문제와 임상 인지점수 전체 병합은 별도 작업입니다.
- `clinical pass`와 `source QC pass`는 각 검사의 범위를 뜻하며, 결과의 `ANALYSIS_READY=False`를 연구 적합성 완료로 승격하지 않습니다.

## 근거

- [ADNI Mayo MRI QC](https://adni.loni.usc.edu/data-samples/adni-data/neuroimaging/mri/mri-quality-control/): 허용 등급 1–3, 실패 4.
- [ADNI 진단 정의](https://adni.loni.usc.edu/quick-start-guide-asset/diagnostic.html): DIAGNOSIS 3은 Dementia.
- Research 코드의 출처와 version은 `03_config/imported_sources.json`에 기록합니다. Source CSV 경로·입력/출력 hash와 실제 원본 행은 실행별 외부 artifact에만 저장합니다.
