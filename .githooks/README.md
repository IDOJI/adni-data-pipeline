# Codex 공동 작성자 표기

이 저장소에서 Codex가 기여한 커밋에는 다음 Git trailer를 기록합니다.

```text
Co-authored-by: Codex <codex@openai.com>
```

현재 clone에 한 번 활성화합니다. 기존 hook 설정을 사용 중이면 그 설정과 먼저 통합해야 합니다.

```sh
git config --local core.hooksPath .githooks
```

`CODEX_THREAD_ID`가 있는 Codex 작업 환경에서 `git commit`하면 자동 추가됩니다. 다른 Codex 실행 환경에서는 `CODEX_COAUTHOR=1 git commit ...`로 명시할 수 있습니다. 두 환경변수가 모두 없으면 일반 커밋 메시지를 변경하지 않습니다. 기존 공동 작성자를 보존하고 동일한 Codex trailer를 중복 추가하지 않습니다.

Git은 clone 시 hook을 자동 활성화하지 않으므로 새 clone에도 위 설정이 필요합니다. 이 설정은 현재 저장소에만 적용됩니다. 이미 게시한 과거 커밋은 수정하지 않습니다.

공동 작성자 기록과 계정/Contributors 표시를 구분합니다. GitHub의 계정 연결은 해당 이메일이 계정에 연결되어 있어야 합니다. [GitHub 공식 문서](https://docs.github.com/en/pull-requests/how-tos/commit-changes/creating-a-commit-with-multiple-authors).
