# API Reference

公開シンボルは `progress_based_verification.__init__` から import できます。

```python
from progress_based_verification import (
    BoundaryEdge,
    Coordinate,
    DeadlockInfo,
    LivelockInfo,
    ProgressBasedVerificationEngine,
    StateId,
    Transition,
    TransitionLike,
    TwoCell,
)
```

## Type aliases

### `StateId`

```python
StateId = Hashable
```

状態識別子。文字列、整数、tuple など hashable な値を利用できます。

### `Coordinate`

```python
Coordinate = tuple[float, ...]
```

状態の progress coordinate。

### `BoundaryEdge`

```python
BoundaryEdge = tuple[StateId, StateId, int]
```

`TwoCell.boundary` を構成する `(source, target, sign)`。

### `TransitionLike`

以下のいずれかです。

```python
Transition
(source, target)
(source, target, label)
(source, target, label, fair)
```

## `Transition`

```python
@dataclass(frozen=True, slots=True)
class Transition:
    source: StateId
    target: StateId
    label: str = ""
    fair: bool = True
```

有向 1-cell / 状態遷移です。

## `TwoCell`

```python
@dataclass(frozen=True, slots=True)
class TwoCell:
    boundary: tuple[BoundaryEdge, ...]
    label: str = ""
```

向き付き 2-cell の境界を表します。

## `DeadlockInfo`

```python
@dataclass(frozen=True, slots=True)
class DeadlockInfo:
    state: StateId
    persistent_reachable: frozenset[StateId]
    trap_regions: tuple[frozenset[StateId], ...]
```

### Fields

- `state`: deadlock 条件を満たす解析起点
- `persistent_reachable`: 到達可能な bottom SCC に含まれる state の和集合
- `trap_regions`: 個々の bottom SCC

## `LivelockInfo`

```python
@dataclass(frozen=True, slots=True)
class LivelockInfo:
    homology_dimension: int
    cycle_edges: tuple[Transition, ...]
    cycle_states: tuple[StateId, ...]
    representative: tuple[float, ...]
```

### Fields

- `homology_dimension`: 実装が計算した非自明 1-cycle 空間の次元指標
- `cycle_edges`: representative から抽出した有向 cycle
- `cycle_states`: cycle の state 列。閉路なら先頭と末尾が一致
- `representative`: `ker(D1)` basis から選ばれた係数ベクトル

## `ProgressBasedVerificationEngine`

### Constructor

```python
ProgressBasedVerificationEngine(
    states,
    transitions,
    forbidden_states=None,
    goal_states=None,
    fair_transition_predicate=None,
    two_cells=None,
)
```

### Parameters

`states`
: `Mapping[StateId, Sequence[float]]`。全座標は同一次元である必要があります。

`transitions`
: `Iterable[TransitionLike]`。最低1件必要です。

`forbidden_states`
: 有効空間から除外する state ID。

`goal_states`
: 正常完了状態。

`fair_transition_predicate`
: `Callable[[Transition], bool]`。指定時は `Transition.fair` の代わりに fairness 判定へ使用されます。

`two_cells`
: 2-cell を明示する場合の `Iterable[TwoCell]`。

### Constructor errors

以下では `ValueError` が発生します。

- state が空
- transition が空
- goal / forbidden が未知 state を参照
- coordinate dimension が混在
- transition が未知 state を参照
- transition がいずれかの coordinate で後退
- forbidden 除外後の valid space が空

## `detect_deadlocks()`

```python
def detect_deadlocks(self) -> list[DeadlockInfo]
```

valid graph の terminal SCC を用いて deadlock 状態を返します。

## `detect_livelocks()`

```python
def detect_livelocks(self, tolerance: float = 1e-9) -> list[LivelockInfo]
```

fair non-goal subcomplex の非自明 1-cycle を探索します。

現実装では代表的な非自明 cycle を見つけると探索ループを終了するため、すべての独立 cycle を列挙する API ではありません。

## `build_fair_boundary_matrices()`

```python
def build_fair_boundary_matrices(self):
    ...
```

戻り値:

```python
(
    fair_states,
    fair_edges,
    d1,
    d2,
)
```

- `fair_states`: valid かつ non-goal state
- `fair_edges`: fairness 判定を通過し、両端が fair_states にある edge
- `d1`: shape `(len(fair_states), len(fair_edges))`
- `d2`: shape `(len(fair_edges), number_of_included_two_cells)`

アルゴリズムの意味は [Algorithms](algorithms.md) を参照してください。
