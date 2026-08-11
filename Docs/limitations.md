# Limitations and Engineering Notes

このページは、現実装を利用・拡張する際に特に誤解しやすい点をまとめます。

## 1. The engine does not build the model for you

入力は finite states / transitions です。

ソースコード、Petri net、BPMN、ログ、トレース、実プロセスなどから状態空間を自動生成する機能はありません。

したがって検証品質は、外部で作成した abstraction の品質に依存します。

## 2. Finite-state only

すべての state と transition を明示的に列挙します。

無限状態系、symbolic state、parameterized verification は現時点の対象外です。

## 3. Monotone progress is a hard invariant

すべての transition について、全 progress coordinate が単調非減少である必要があります。

このため「進捗を巻き戻す」モデルはそのまま入力できません。

retry / spin cycle は、同一座標に複数 state を置くことで表現できます。

## 4. Deadlock semantics are stronger than may-deadlock

ある state から到達可能な bottom SCC をすべて集め、その和集合が goal と disjoint な場合に報告します。

したがって、

```text
state -> goal terminal region
     \-> bad terminal region
```

のように goal へ到達する終端候補も bad trap も両方ある場合、現実装はその state を deadlock として報告しません。

「deadlock へ到達可能な経路が1本でも存在するか」を調べたい場合は別の may-reachability 判定が必要です。

## 5. Fairness is an edge filter, not a fairness proof

`Transition.fair` と `fair_transition_predicate` は、livelock 解析に含める edge を選別する mechanism です。

弱公平性・強公平性などの temporal fairness 条件をエンジンが自動証明するわけではありません。

## 6. Livelock API returns a representative, not a full basis

`detect_livelocks()` は非自明な representative を見つけるとループを終了します。

そのため複数の独立 livelock class が存在しても、現 API は完全列挙を目的としていません。

将来的な拡張では、例えば次を分けると扱いやすくなります。

```text
compute_h1_basis()
extract_cycle_for_class(i)
detect_all_livelocks()
```

## 7. Parallel edges can be ambiguous in D2

`D2` 構築時の edge index は `(source, target)` を key にしています。

同一 source / target 間に複数の異なる `Transition` がある場合、2-cell boundary がどの edge を指すのか区別できません。

並列 edge を本格的に扱うなら、transition ID を一意に持たせ、`BoundaryEdge` も edge ID を参照する設計が安全です。

## 8. Automatic TwoCell inference is intentionally narrow

自動推論は座標上の `+1` unit square を探します。

次のケースでは明示的な `TwoCell` を推奨します。

- step size が1ではない
- 非格子状の complex
- 3次元以上で意味のある高次 cell を厳密に扱いたい
- 同一 coordinate に複数 state がある
- domain-specific な commuting relation がある

## 9. Duplicate coordinates are lossy for auto inference

自動 2-cell 推論用の `coordinate -> state` 対応は、同じ coordinate に複数 state が存在した場合に代表1 state へまとめられます。

retry-loop のように同一座標へ複数状態を置くモデルでは、auto TwoCell inference が意図を完全には反映しない可能性があります。


## 10. User-supplied TwoCell is not fully validated

`TwoCell` の topology や sign が数学的に妥当かを constructor で完全検証する処理はありません。

また `D2` 構築時、fair edge 集合に存在しない boundary edge を含む cell は列として採用されません。

厳密に chain complex を保証したい場合は、少なくとも次を追加検証する余地があります。

```text
D1 @ D2 == 0
```

加えて boundary sign、edge identity、cell orientation の validation も明示化すると安全です。

## 11. Numerical linear algebra

livelock 検出は NumPy の SVD と matrix rank を使います。

- floating point
- tolerance default `1e-9`
- ill-conditioned matrix

の影響を受けます。

厳密代数が必要な用途では、有理数体・有限体上の行列演算など別 backend の検討余地があります。

## 12. No CLI / serialization layer

現時点の主要インターフェースは Python API です。

以下は未提供です。

- CLI
- JSON/YAML schema
- model file loader
- graph visualization
- report export

利用者が増える場合、まず JSON/YAML model schema と CLI を追加すると導入障壁を下げやすいです。

## 13. Package metadata and repository metadata should be kept aligned

`pyproject.toml` では MIT license が宣言されています。配布・外部利用を想定する場合は、リポジトリ直下の license text、release process、CI、versioning policy も合わせて明示すると OSS として理解しやすくなります。

## Suggested next engineering steps

優先度順の一案です。

1. transition に一意 ID を導入し parallel edge を安全に扱う
2. deadlock を `must` / `may` semantics に分ける
3. livelock class の完全列挙 API を追加する
4. JSON/YAML model schema と loader を追加する
5. CLI を追加する
6. GitHub Actions で lint/type/test/build を自動化する
7. examples/ を追加して典型モデルを実行可能にする
