# 자료 준비

ADNI 접근 승인과 데이터 선택·다운로드는 원본 s1/s2를 따릅니다. 이전 Research RDS나 특정 Selection Table을 필수 입력으로 사용하지 않습니다.

```text
ADNI_DATA/                         # 이 Git 저장소 밖
├── LONI_download/
│   ├── zipped_imaging_data/
│   ├── meta_data/                 # collection·다운로드 metadata
│   ├── sourcedata/                # DICOM
│   └── clindata/                  # 원본 임상·QC·NFQ 표
├── rawdata/                       # Clinica BIDS
├── derivatives/{mriqc,fmriprep}/
├── config/                        # 생성된 실제 upstream 설정
├── qc/{step4b,step5a,step5,step5c,step8}/
├── jobs/
├── logs/
└── results/
```

다운로드 조건·자료 동결일·collection CSV·원본 표 버전을 보존합니다. 현재 지원 범위는 원본과 같은 GO/2/3입니다. ADNI4/SNP 확장 시 독립 입력·검증·적용 범위를 먼저 정의합니다.

Step 5.C의 출력은 실행 연결용 자료이며 새로운 선별 정본이 아닙니다. 세션·run·Image ID는 각 원본 conversion_info와 계속 연결해 두고, 파일 존재와 형식 검증을 원본 QC 통과로 해석하지 않습니다.
