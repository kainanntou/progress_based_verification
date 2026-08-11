# Development Guide

## Requirements

- Python 3.10+
- pip
- Git

パッケージの runtime dependency は NumPy です。

開発用 optional dependency:

- Hatch
- mypy
- pytest
- Ruff

## Recommended local setup

### macOS / Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -e ".[dev]"
```

### Windows PowerShell

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
python -m pip install -e ".[dev]"
```

Python 3.12 がなければ 3.11 / 3.10 でも package requirement 上は実行可能です。

## Test

```bash
python -m pytest
```

現在の test suite は少なくとも次を確認しています。

- inverse lock order 型 deadlock
- try-lock/release loop 型 livelock
- empty state / transition の validation
- isolated state の deadlock 判定
- unfair cycle が livelock として報告されないこと

## Formatting and lint

```bash
python -m ruff format --check .
python -m ruff check .
```

自動 format:

```bash
python -m ruff format .
```

safe fix を許可する lint:

```bash
python -m ruff check . --fix
```

## Type checking

```bash
python -m mypy --strict src tests
```

`pyproject.toml` の mypy 設定は strict mode です。

## Build

```bash
python -m hatch build
```

成功すると通常 `dist/` に wheel と source distribution が生成されます。

## Bundled setup scripts

リポジトリには以下があります。

```text
setup_and_build.sh
setup_and_build.ps1
```

両方とも概ね次を自動実行します。

1. cache / compiled artifact の削除
2. `.venv` の再作成
3. dependency install
4. Ruff format check
5. Ruff lint `--fix`
6. mypy strict
7. pytest
8. Hatch build
9. Git repository 初期化確認
10. `git add -A`
11. staged change があれば固定メッセージで commit

### Important warning

これらは単なる build script ではありません。

既存の未コミット変更も `git add -A` の対象になります。また `.venv` は削除・再作成されます。

通常の開発では、本ページ上部の個別コマンドを使う方が安全です。完全にクリーンな作業ツリーで、script の副作用を理解している場合にのみ一括 script を使うことを推奨します。

## Suggested change workflow

```bash
git switch -c feature/<name>

python -m pytest
python -m ruff format --check .
python -m ruff check .
python -m mypy --strict src tests

# code/doc changes

git diff
python -m pytest

git add <intended-files>
git commit -m "..."
```

## Test expansion ideas

エンジンを拡張する場合、次の test を追加すると回帰防止に有効です。

- 複数 bottom SCC のうち一部だけ goal を含むケース
- 明示 `TwoCell` で cycle が boundary として消えるケース
- unit-square 自動推論の正例 / 負例
- parallel transition を含むケース
- tolerance 境界の数値テスト
- 3次元以上の coordinate
- custom `fair_transition_predicate`
- forbidden state が edge を切断するケース
