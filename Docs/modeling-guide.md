# Modeling Guide

## 1. What you need to model

最低限必要なのは次の2つです。

- `states`: 状態 ID と progress coordinate
- `transitions`: 状態間の有向遷移

実運用では通常、以下も定義します。

- `goal_states`: 正常完了状態
- `forbidden_states`: 禁止・無効状態
- `fair` または `fair_transition_predicate`: livelock 解析対象の遷移
- `two_cells`: 2次元セルを明示したい場合

## 2. States and progress coordinates

```python
states = {
    "start": (0.0, 0.0),
    "worker1_done": (1.0, 0.0),
    "worker2_done": (0.0, 1.0),
    "all_done": (1.0, 1.0),
}
```

state ID は hashable であれば文字列以外も利用できます。

座標は「各主体や工程がどこまで進んだか」を表す抽象的な progress vector と考えると分かりやすいです。

### Coordinate invariants

全 state は同じ次元を持つ必要があります。

```python
# OK
"a": (0.0, 0.0)
"b": (1.0, 0.0)

# NG: dimension mismatch
"c": (1.0, 0.0, 0.0)
```

また、transition はどの軸でも後退できません。

```python
# OK: (0, 0) -> (1, 0)
# OK: (0, 0) -> (0, 0)
# NG: (1, 0) -> (0, 0)
```

同じ座標間の遷移は許されるため、retry / spin / protocol 内部遷移の cycle を表現できます。

## 3. Transitions

推奨形式は `Transition` です。

```python
from progress_based_verification import Transition

edge = Transition(
    source="start",
    target="worker1_done",
    label="worker1_commit",
    fair=True,
)
```

tuple 形式も利用できます。

```python
("start", "worker1_done")
("start", "worker1_done", "worker1_commit")
("start", "worker1_done", "worker1_commit", True)
```

`label` は検出された cycle を人間が読める形にするため、実システム上のイベント名を付けることを推奨します。

## 4. Goal states

```python
goal_states = {"all_done"}
```

Deadlock 解析では「終端 trap region に goal が存在するか」の判定に使われます。

Livelock 解析では goal state 自体を部分複体から除外します。つまり「正常完了へ入る cycle」は livelock 候補から外れます。

## 5. Forbidden states

```python
forbidden_states = {"invalid_interleaving"}
```

forbidden state は valid state 集合から完全に除かれ、その state を source / target に持つ transition も解析対象外になります。

禁止状態は、例えば次の用途に使えます。

- mutex 制約上あり得ない組み合わせ
- protocol invariant に違反する状態
- モデル上は座標格子に存在するが実行不能な領域

## 6. Fairness

### Per-edge flag

```python
Transition("a", "b", "retry", fair=True)
Transition("b", "a", "scheduler_artifact", fair=False)
```

標準では `fair=True` の edge だけが livelock 解析に入ります。

### Predicate override

```python
def fairness(edge: Transition) -> bool:
    return edge.label not in {"timeout_artifact", "debug_only"}

engine = ProgressBasedVerificationEngine(
    states=states,
    transitions=transitions,
    fair_transition_predicate=fairness,
)
```

predicate が指定されると、その判定が `Transition.fair` より優先されます。

## 7. TwoCell

Livelock 判定では「単なる cycle」と「2次元領域の境界として潰せる cycle」を区別するため `D2` を使います。

2-cell を明示する場合:

```python
from progress_based_verification import TwoCell

cell = TwoCell(
    boundary=(
        ("s00", "s10", +1),
        ("s10", "s11", +1),
        ("s01", "s11", -1),
        ("s00", "s01", -1),
    ),
    label="commuting_square",
)
```

`boundary` の各要素は `(source, target, sign)` です。

### Automatic inference

`two_cells` を渡さない場合、エンジンは progress coordinate 上の unit square を推論します。

2次元の例:

```text
(0,1) ----> (1,1)
  ^             ^
  |             |
(0,0) ----> (1,0)
```

4辺が valid transition として存在すると 2-cell 候補になります。

自動推論には制約があるため、一般的な cell complex を扱う場合は明示的な `TwoCell` を推奨します。

## 8. Deadlock example

```python
from progress_based_verification import ProgressBasedVerificationEngine, Transition

states = {
    "start": (0.0, 0.0),
    "p1_holds_a": (1.0, 0.0),
    "p2_holds_b": (0.0, 1.0),
    "deadlocked_wait": (1.0, 1.0),
    "goal": (2.0, 2.0),
}

transitions = (
    Transition("start", "p1_holds_a", "p1_lock_a"),
    Transition("start", "p2_holds_b", "p2_lock_b"),
    Transition("p1_holds_a", "deadlocked_wait", "p2_waits_a"),
    Transition("p2_holds_b", "deadlocked_wait", "p1_waits_b"),
)

engine = ProgressBasedVerificationEngine(
    states=states,
    transitions=transitions,
    goal_states={"goal"},
)

assert any(item.state == "deadlocked_wait" for item in engine.detect_deadlocks())
```

## 9. Livelock example

同一 progress coordinate 内で retry loop を表現できます。

```python
states = {
    "try_a": (0.0, 0.0),
    "try_b": (0.0, 0.0),
    "release": (0.0, 0.0),
    "goal": (1.0, 1.0),
}

transitions = (
    Transition("try_a", "try_b", "try_a_succeeds", fair=True),
    Transition("try_b", "release", "try_b_fails", fair=True),
    Transition("release", "try_a", "release_a", fair=True),
)

engine = ProgressBasedVerificationEngine(
    states=states,
    transitions=transitions,
    goal_states={"goal"},
)

livelocks = engine.detect_livelocks()
assert livelocks
```

この cycle は progress coordinate を増やさないまま fair edge 上を回り続けるため、non-goal 1-cycle として検出対象になります。

## 10. Modeling checklist

モデルを作る際は次を確認してください。

- 全 state coordinate の次元が同じか
- edge が progress を逆行していないか
- goal を正常終了状態として網羅できているか
- forbidden を「到達不能」や「無効」と混同していないか
- fair/unfair の意味をシステム側の scheduler 仮定と揃えているか
- 2-cell 自動推論で十分か、明示 `TwoCell` が必要か
- 同一 source/target の parallel edge が必要なモデルになっていないか

最後の項目は現実装の重要な制約です。詳細は [Limitations](limitations.md) を参照してください。
