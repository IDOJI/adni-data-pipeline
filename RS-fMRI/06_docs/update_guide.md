# 원본 업데이트

일반 사용자는 저장소 root에서 `git pull --ff-only` 후 `git submodule update --init --recursive`로 기록된 원본 commit을 받습니다. `--remote`는 일상 설치 명령에 넣지 않습니다.

## 초기 무번호 구조에서 한 번만 전환

기존 clone에서 아직 `RS-fMRI/upstream/ADNI_fMRI_protocol`을 사용한다면 **업데이트 전에** 저장소 root에서 다음 순서로 진행합니다. `deinit`은 수정이 있는 submodule을 강제로 제거하지 않도록 `--force` 없이 사용합니다. 진행이 거절되면 원본 변경을 먼저 보존합니다.

```sh
git submodule deinit -- RS-fMRI/upstream/ADNI_fMRI_protocol
git pull --ff-only
git submodule update --init --recursive
cd RS-fMRI
python 04_workflow/lab.py doctor
```

이 절의 무번호 경로는 이전 clone을 정리하는 일회성 입력입니다. 새 경로는 `RS-fMRI/01_upstream/ADNI_fMRI_protocol`이며, submodule 식별 이름과 고정 원본 commit은 유지합니다. 새 clone이나 이미 번호화한 clone은 위 deinit 단계를 생략합니다.

원본 업데이트를 평가할 때는 깨끗한 root에서 별도 브랜치를 만듭니다.

```sh
git switch -c test/upstream-update
git submodule update --remote --checkout RS-fMRI/01_upstream/ADNI_fMRI_protocol
git diff --submodule=log -- RS-fMRI/01_upstream/ADNI_fMRI_protocol
```

새 source commit과 입력·출력 변경을 확인한 뒤 `RS-fMRI/03_config/upstream.lock.json`의 commit과 검토일을 갱신하고 gitlink를 stage합니다. lock 변경만으로 검증 완료로 표시하지 않습니다.

```sh
git add RS-fMRI/01_upstream/ADNI_fMRI_protocol RS-fMRI/03_config/upstream.lock.json
cd RS-fMRI
python -m pytest -q
python 04_workflow/lab.py doctor
```

합성 호환성 테스트 외에 연구실 검증 자료의 변환·QC·전처리·임상 연결 결과를 별도 외부 run에서 비교합니다. 통과하면 `03_config/versions.md`에 실제 도구·이미지 digest·변경·검증 범위를 기록하고 PR 검토 후 채택합니다.

실패하면 기존 main으로 돌아간 후 `git submodule update --init --recursive`로 원래 고정 버전을 복원합니다. 실험 branch나 사용자 변경이 있으면 먼저 보존하며 강제 checkout·reset을 사용하지 않습니다.

참고: [Git submodule 공식 문서](https://git-scm.com/docs/git-submodule).
