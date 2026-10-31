> 보존된 volume 파일럿의 방법 문서입니다. 예시는 합성 식별자로 치환했으며, 최신 36P/LINC 경로의 방법·검증 결과로 사용하지 않습니다.

# 🟥1️⃣ 문헌 근거와 적용 범위

- 확인일: 2026-10-28
- 목적: BIDS로 정리된 ADNI3·ADNI4 rs-fMRI에 적용할 Docker 전처리의 근거 확인
- 결론: ADNI3·ADNI4를 실제 분석한 Wang et al. (2026)을 확인. 이 논문은 GRETNA 기반이며, 현재 구현은 Rutherford·Leone의 fMRIPrep 선례와 공식 소프트웨어 설정을 조합한 adaptation이다. 실제 ADNI4 코호트가 명시된 fMRIPrep 논문은 이번 확인 범위에서 미확정

## 🟩2️⃣ 확인한 핵심 문헌

| 문헌 | 자료·출판 상태 | 확인한 전처리와 활용 | 한계 |
| --- | --- | --- | --- |
| Wang, Chen & Qiao, 2026 | Medical Image Analysis 원저; ADNI3·ADNI4 실제 분석 | §4.3: ADNI4 104명(CN 59/MCI 45), TR 1.5초, TE 0.03초, 90 nodes·200 timepoints | GRETNA 기반. ADNI4에 적용한 개별 전처리 설정의 공유 범위는 아래와 같이 제한하여 해석 |
| Rutherford et al., 2026, A Pipeline for ADNI Resting-State Functional MRI Processing and Quality Control | ADNI GO/2/3; Research Square 및 arXiv preprint | 확인본 arXiv v3(2026-09-04): fMRIPrep 25.2.3, MRIQC 24.0.2. FD 0.5 mm 기준, 검열 프레임 30% 초과 또는 남은 저움직임 자료 5분 미만 제외. FreeSurfer 표면과 Euler QC 포함 | ADNI4는 Clinica 변환 미지원으로 제외. 공개 저장소 예제 config의 fMRIPrep 24.0.0은 최신 본문 버전과 불일치. 5분 획득인 ADNI4에 동일한 잔존 5분 기준 적용 곤란 |
| Canal-Garcia et al., 2024, Dynamic multilayer functional connectivity detects preclinical and clinical Alzheimer’s disease | ADNI3; Cerebral Cortex 원저 | fMRIPrep 20.2.4, 처음 2 volumes 제거, 움직임·slice timing 보정, 2 mm MNI152, 24-parameter motion nuisance model 및 WM/CSF 관련 잡음 처리, 0.01 Hz high-pass | 동적 연결성 연구용 파이프라인. 본 구현의 aCompCor, 0.08 Hz low-pass, 6 mm smoothing의 직접 근거로 인용 불가 |
| Billaud & Yu, 2025, Structure–function coupling using fixel-based analysis and functional magnetic resonance imaging in Alzheimer’s disease and mild cognitive impairment | ADNI3 프로토콜을 명시한 Network Neuroscience 원저 | fMRIPrep 20.2.5; AFNI slice timing, MCFLIRT, FreeSurfer bbregister 9 DOF, MNI 변환. Nilearn으로 6 motion, WM/CSF/global signal 및 derivatives와 cosine 처리; 5 mm smoothing, 0.1 Hz low-pass; relative RMS >0.25인 volumes가 20% 초과이면 제외 | GSR·5 mm·0.1 Hz·RMS 기준은 본 구현의 noGSR·6 mm·0.08 Hz·Power FD 기준과 다름 |
| Arani et al., 2024, Design and validation of the ADNI MR protocol | ADNI4 MRI 획득 프로토콜 원저 | ADNI4 BOLD: basic TR 1.5초, advanced 0.6초; 구형 장비 3초 지속. ADNI3 10분에서 ADNI4 5분으로 단축 | 분석 코호트의 fMRIPrep 검증 논문이 아님. TR·duration을 phase만으로 고정하지 않고 각 sidecar와 NIfTI에서 확인할 근거 |

- Wang: Yiding Wang, Longyun Chen, Chen Qiao. *Continuous-time causal distribution learning with identifiability for brain dynamic effective connectivity inference*. Medical Image Analysis. 2026;112:104124; 2026-05-13 온라인 출판. DOI: [10.1016/j.media.2026.104124](https://doi.org/10.1016/j.media.2026.104124). [PubMed](https://pubmed.ncbi.nlm.nih.gov/42134283/), [출판사 §4.3](https://www.sciencedirect.com/science/article/pii/S1361841526001933)
- Rutherford: [PubMed](https://pubmed.ncbi.nlm.nih.gov/42926671/), [확인한 v3 PDF](https://arxiv.org/pdf/2602.03278v3), [저자 코드](https://github.com/statMINDlab/ADNI_fMRI_protocol), [예제 config](https://raw.githubusercontent.com/statMINDlab/ADNI_fMRI_protocol/main/config/config_adni.yaml), [최종 QC 코드 설명](https://raw.githubusercontent.com/statMINDlab/ADNI_fMRI_protocol/main/s8_final_qc/README.md). DOI: 10.21203/rs.3.rs-11132707/v1
- Canal-Garcia: [논문 PDF](https://adni.loni.usc.edu/adni-publications/Canal-Garcia_2024_Dynamic%20multilayer%20functiona.pdf). DOI: 10.1093/cercor/bhad542
- Billaud & Yu: [논문 PDF](https://direct.mit.edu/netn/article-pdf/doi/10.1162/netn_a_00461/2513016/netn_a_00461.pdf). DOI: 10.1162/netn_a_00461
- Arani: [원문](https://alz-journals.onlinelibrary.wiley.com/doi/full/10.1002/alz.14162). DOI: 10.1002/alz.14162

## 🟩2️⃣ Wang 논문의 Methods 적용 범위

- §4.3 앞부분은 ADNI3 EMCI/LMCI와 Table 7에 연결: GRETNA로 초기 안정화·움직임 보정·정규화·평활화·0.01–0.08 Hz 필터, AAL90·187 timepoints를 설명
- 뒤의 ADNI4 문단과 Fig. 9(a)는 실제 추가 코호트를 확인하지만 ADNI3의 10분·TR 3초·187 timepoints를 ADNI4에 적용하지 않음. ADNI4의 dummy 수·회귀변수·motion cutoff·평활화 폭·SDC·정규화 공간은 확정하지 않음
- 앞의 합성자료 실험 및 §4.2 Starplus task-fMRI 설정은 ADNI 전처리 근거가 아님. §4.3은 ROI 수준 자료 사용을 명시하며, 완전한 BIDS→fMRIPrep 재현 명세를 제공하지 않음
- 확인 경로: 출판사에 색인된 원문 §4.3과 PubMed 서지를 대조. 직접 페이지 접근은 403으로 제한되어 PDF 확보로 기록하지 않음

## 🟩2️⃣ Down 및 Leone 문헌의 검증 수준

- Down et al., 2026, *Synergistic and redundant information dynamics are modulated by Alzheimer’s disease and cognitive impairment*: [PubMed](https://pubmed.ncbi.nlm.nih.gov/41757079/), [PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC12934565/), DOI 10.64898/2026.02.18.706630. bioRxiv preprint. 검색에 노출된 원문 Methods는 2023-11-22 이전의 10분 rs-fMRI 2,907 scans에서 개인별 가장 최근 scan을 선택했다고 설명. 획득 절에 ADNI3·ADNI4를 함께 언급하지만 phase별 실제 포함 수나 ADNI4 scan 목록은 확인하지 못함. 따라서 실제 ADNI4 처리 검증의 확정 근거로 사용하지 않음. 논문의 10분 및 TR 3/0.6초 설명은 공식 ADNI4 5분 및 TR 1.5/0.6초 프로토콜을 모두 설명하지 못하므로 특히 주의 필요. PMC에 색인된 원문의 전처리 절에서 fMRIPrep 23.0.2와 Clinica ADNI-to-BIDS 확인. 사용자 지정 nuisance/filter의 세부 수치는 미확인
- Leone et al., 2024, *Beyond Focal Lesions: Dynamical Network Effects of White Matter Hyperintensities*: [PubMed](https://pubmed.ncbi.nlm.nih.gov/39624946/), [출판사 원문 §2.1–2.2](https://onlinelibrary.wiley.com/doi/full/10.1002/hbm.70081), DOI 10.1002/hbm.70081. ADNI3 초기 363명 중 188명 분석. fMRIPrep 21.0.4 → XCP-D, 처음 4 timepoints 제거, nonaggressive ICA-AROMA, motion 6개·derivatives와 WM/CSF 잡음 처리, AAL90, demean·detrend, 0.04–0.07 Hz 필터 확인. ADNI3에서 fMRIPrep→XCP-D를 적용한 동료심사 근거로 사용. XCP-D 세부 버전·smoothing·motion cutoff는 확인한 절만으로 확정하지 않음. 본 구현의 aCompCor·0.01–0.08 Hz는 해당 논문과 다른 설정

## 🟩2️⃣ 현재 구현값의 출처 구분

| 구현 선택 | 근거 구분 |
| --- | --- |
| fMRIPrep 25.2.7 Docker | 최신 ADNI 공개 파이프라인을 참고한 버전 갱신. Rutherford의 25.2.3과 동일 실행 재현은 아님. 실제 버전·digest와 변경 이유는 실행 manifest/방법 문서에서 기록 |
| MNI152NLin2009cAsym 2 mm, volumetric-only, fs-no-reconall | 공통 표준공간과 용량·실행범위를 정한 본 프로젝트 선택. 표면/CIFTI·Euler QC를 포함한 Rutherford의 전체 파이프라인과 차이 |
| fieldmap-less SyN SDC | Rutherford 공개 코드에서 확인한 접근을 참고. 실제 PE·readout 메타데이터 및 실행 로그로 적용 여부 검증. fieldmap 입력이 있으면 별도 검토 |
| XCP-D 26.2.0, WM5+CSF5 aCompCor, 12 motion, cosines, noGSR | Leone의 fMRIPrep→XCP-D 구조를 참고하되 ICA-AROMA를 복제하지 않는 후처리 명세. XCP-D 공식 acompcor model을 명시적으로 사용 |
| FD >0.5 mm censoring 및 motion censoring 비율 ≤30% | Rutherford의 움직임 기준을 참고. 비율 분모는 dummy 제거 후 volume으로 명시. 잔존 시간은 300초에서 240초로 변경. XCP-D 명령의 최소 잔존 시간과 별도로 audit에서 30% 이하 및 240초 이상을 함께 판정 |
| 최소 잔존 240초 | ADNI4 5분 촬영을 고려해 정한 프로젝트 기준. Rutherford의 300초 기준에서 변경했음을 명시 |
| 0.01–0.08 Hz, Butterworth order parameter 2 및 6 mm smoothing | 본 프로젝트 선택. 위 확인 논문의 정확한 공통 설정이라고 서술하지 않음 |
| 획득 TR 유지 | ADNI3/4의 시간 해상도 차이를 입력별로 처리. Down의 TR 3초 downsampling을 재현하지 않음 |

- fMRIPrep 자체는 motion/registration/normalization 등 최소 전처리와 confound 추정을 제공하며, 일반적인 최종 nuisance regression·band-pass·smoothing을 모두 완료한 denoised BOLD와 구별 필요: [fMRIPrep 공식 문서](https://fmriprep.org/en/latest/)
- ADNI4 공식 FAQ에는 일반 field map acquisition이 없다고 명시. diffusion의 역방향 PE scan을 BOLD fieldmap으로 자동 지정할 근거는 아님: [ADNI MRI FAQ](https://adni.loni.usc.edu/help-faqs/faqs/)

## 🟩2️⃣ 검색 기록과 해석 제한

- 주요 검색어: `ADNI3 fMRIPrep resting state preprocessing 2024 2025`; `ADNI4 resting state fMRI preprocessing fMRIPrep`; `ADNI4 functional connectivity 2025 2026 preprocessing`; 논문 제목·PMID 기반 확인
- 확인 우선순위: 저자 공개 코드, 논문 원문·저자 기관 공개 PDF, PubMed, ADNI MRI Core 공식 문서
- 제외 사례: ADNI GO/2/3/4를 포함하지만 T1w 구조영상 연구인 Baek et al., 2026, DOI 10.1002/hbm.70548. ADNI4 rs-fMRI 전처리 근거로 사용하지 않음
- 일부 PMC 원문 접근 시 재인증 화면 발생. 검색에 노출된 원문 절과 접근 가능한 공개 원문을 구분하여 사용. 추가 XML 네트워크 접근은 승인 대기 후 중단되어 취득 성공으로 기록하지 않음
- 추가 검색어: `"Continuous-time causal distribution learning" "ADNI4"`. 초기 ADNI4 분석 논문 미확정 결론은 Wang 논문의 직접 코호트 확인으로 교체. ADNI4 적용의 기술적 완료와 과학적 타당성 검증은 별도로 판단


## 🟩2️⃣ 실행 버전과 공식 설정 근거

- [fMRIPrep 25.2.7 변경 이력](https://fmriprep.org/en/25.2.7/changes.html): 25.0.0–25.2.6의 MCFLIRT motion parameter 재구성 및 BOLD mask 수정. 신규 실행에서 25.2.7 선택
- [XCP-D 26.2.0 처리 과정](https://xcp-d.readthedocs.io/en/26.2.0/workflows.html): linc의 0.01–0.08 Hz·6 mm 설정을 명시적으로 고정하고, 기본 FD=0을 0.5로 변경
- [XCP-D acompcor 설정](https://raw.githubusercontent.com/PennLINC/xcp_d/26.2.0/xcp_d/data/nuisance/acompcor.yml): WM5·CSF5·motion12·cosine 구성 확인
- 검색 과정의 초기 미확인 상태는 최종 원문 확인 결과로 교체. 원문 확인 범위 밖의 설정을 추정하지 않음
