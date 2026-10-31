# Codex co-author attribution

Commits with Codex contributions in this repository use the following Git trailer.

```text
Co-authored-by: Codex <codex@openai.com>
```

Enable the hook once in the current clone. Integrate it with any existing hook configuration first.

```sh
git config --local core.hooksPath .githooks
```

Running `git commit` in a Codex environment with `CODEX_THREAD_ID` adds the trailer automatically. Other Codex environments can opt in with `CODEX_COAUTHOR=1 git commit ...`. Ordinary commit messages remain unchanged when neither variable is set. Existing co-authors are preserved, and the same Codex trailer is not added twice.

Git does not activate hooks when cloning, so each new clone requires the setup above. The setting applies only to this repository. Previously published commits are not rewritten.

Co-author attribution and account/Contributors display are separate. GitHub links an identity only when the email belongs to that account. See the [official GitHub documentation](https://docs.github.com/en/pull-requests/how-tos/commit-changes/creating-a-commit-with-multiple-authors).
