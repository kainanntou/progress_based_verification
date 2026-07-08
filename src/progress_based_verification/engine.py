from __future__ import annotations

from collections.abc import Callable, Hashable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import TypeAlias, cast

import numpy as np
import numpy.typing as npt

StateId: TypeAlias = Hashable
Coordinate: TypeAlias = tuple[float, ...]
BoundaryEdge: TypeAlias = tuple[StateId, StateId, int]
FloatMatrix: TypeAlias = npt.NDArray[np.float64]


@dataclass(frozen=True, slots=True)
class Transition:
    """Directed 1-cell between two progress states."""

    source: StateId
    target: StateId
    label: str = ""
    fair: bool = True


TransitionLike: TypeAlias = (
    Transition
    | tuple[StateId, StateId]
    | tuple[StateId, StateId, str]
    | tuple[StateId, StateId, str, bool]
)


@dataclass(frozen=True, slots=True)
class TwoCell:
    """Oriented 2-cell boundary represented by signed directed edges."""

    boundary: tuple[BoundaryEdge, ...]
    label: str = ""


@dataclass(frozen=True, slots=True)
class DeadlockInfo:
    state: StateId
    persistent_reachable: frozenset[StateId]
    trap_regions: tuple[frozenset[StateId], ...]


@dataclass(frozen=True, slots=True)
class LivelockInfo:
    homology_dimension: int
    cycle_edges: tuple[Transition, ...]
    cycle_states: tuple[StateId, ...]
    representative: tuple[float, ...]


class ProgressBasedVerificationEngine:
    """Backend engine for progress-based deadlock and livelock detection."""

    def __init__(
        self,
        states: Mapping[StateId, Sequence[float]],
        transitions: Iterable[TransitionLike],
        forbidden_states: Iterable[StateId] | None = None,
        goal_states: Iterable[StateId] | None = None,
        fair_transition_predicate: Callable[[Transition], bool] | None = None,
        two_cells: Iterable[TwoCell] | None = None,
    ) -> None:
        self.states: dict[StateId, Coordinate] = {
            state: tuple(float(value) for value in coordinate)
            for state, coordinate in states.items()
        }
        self.forbidden_states: set[StateId] = set(forbidden_states or ())
        self.goal_states: set[StateId] = set(goal_states or ())
        self._fair_transition_predicate = fair_transition_predicate

        self.transitions: tuple[Transition, ...] = tuple(
            self._normalize_transition(transition) for transition in transitions
        )
        self.two_cells: tuple[TwoCell, ...] = tuple(two_cells or ())

        self._validate_input()
        self.valid_states: frozenset[StateId] = frozenset(
            state for state in self.states if state not in self.forbidden_states
        )
        if not self.valid_states:
            raise ValueError("Valid space must contain at least one state.")

        self.valid_transitions: tuple[Transition, ...] = tuple(
            transition
            for transition in self.transitions
            if transition.source in self.valid_states
            and transition.target in self.valid_states
        )
        self.adjacency: dict[StateId, list[StateId]] = self._build_adjacency(
            self.valid_states,
            self.valid_transitions,
        )

    def detect_deadlocks(self) -> list[DeadlockInfo]:
        """Detect states whose terminal reachable region contains no goal state."""

        sccs = self._tarjan_scc(self.valid_states, self.adjacency)
        component_of: dict[StateId, int] = {}
        for index, component in enumerate(sccs):
            for state in component:
                component_of[state] = index

        component_graph: dict[int, set[int]] = {
            index: set() for index in range(len(sccs))
        }
        for source, targets in self.adjacency.items():
            source_component = component_of[source]
            for target in targets:
                target_component = component_of[target]
                if source_component != target_component:
                    component_graph[source_component].add(target_component)

        bottom_components = {
            component for component, targets in component_graph.items() if not targets
        }
        reachable_bottom_cache: dict[int, frozenset[int]] = {}

        def reachable_bottom_components(component: int) -> frozenset[int]:
            cached = reachable_bottom_cache.get(component)
            if cached is not None:
                return cached
            if component in bottom_components:
                result = frozenset({component})
            else:
                reached: set[int] = set()
                for target_component in component_graph[component]:
                    reached.update(reachable_bottom_components(target_component))
                result = frozenset(reached)
            reachable_bottom_cache[component] = result
            return result

        deadlocks: list[DeadlockInfo] = []
        for state in sorted(self.valid_states, key=repr):
            bottom = reachable_bottom_components(component_of[state])
            trap_regions = tuple(frozenset(sccs[index]) for index in sorted(bottom))
            persistent_reachable = frozenset(
                trapped_state for region in trap_regions for trapped_state in region
            )
            if persistent_reachable and persistent_reachable.isdisjoint(
                self.goal_states,
            ):
                deadlocks.append(
                    DeadlockInfo(
                        state=state,
                        persistent_reachable=persistent_reachable,
                        trap_regions=trap_regions,
                    ),
                )
        return deadlocks

    def detect_livelocks(self, tolerance: float = 1e-9) -> list[LivelockInfo]:
        """Detect non-trivial fair 1-cycles in the non-goal valid space."""

        fair_states, fair_edges, d1, d2 = self.build_fair_boundary_matrices()
        if not fair_states or not fair_edges:
            return []

        null_basis = self._nullspace(d1, tolerance)
        if null_basis.size == 0:
            return []

        image_rank = int(np.linalg.matrix_rank(d2, tol=tolerance)) if d2.size else 0
        livelocks: list[LivelockInfo] = []

        for column in range(null_basis.shape[1]):
            representative = null_basis[:, column]
            augmented = (
                representative.reshape((-1, 1))
                if d2.size == 0
                else cast(FloatMatrix, np.column_stack([d2, representative]))
            )
            if int(np.linalg.matrix_rank(augmented, tol=tolerance)) <= image_rank:
                continue

            cycle_edges = self._extract_cycle_edges(
                fair_edges,
                representative,
                tolerance,
            )
            if cycle_edges:
                cycle_states = self._cycle_states(cycle_edges)
                livelocks.append(
                    LivelockInfo(
                        homology_dimension=max(1, null_basis.shape[1] - image_rank),
                        cycle_edges=cycle_edges,
                        cycle_states=cycle_states,
                        representative=tuple(float(value) for value in representative),
                    ),
                )
            break

        return livelocks

    def build_fair_boundary_matrices(
        self,
    ) -> tuple[tuple[StateId, ...], tuple[Transition, ...], FloatMatrix, FloatMatrix]:
        """Return fair non-goal states, fair edges, D1, and D2."""

        fair_states, fair_edges = self._fair_non_goal_subcomplex()
        d1 = self._boundary_matrix_d1(fair_states, fair_edges)
        d2 = self._boundary_matrix_d2(fair_edges)
        return fair_states, fair_edges, d1, d2

    def _normalize_transition(self, transition: TransitionLike) -> Transition:
        if isinstance(transition, Transition):
            return transition
        if len(transition) == 2:
            source, target = transition
            return Transition(source=source, target=target)
        if len(transition) == 3:
            source, target, label = transition
            return Transition(source=source, target=target, label=label)
        if len(transition) == 4:
            source, target, label, fair = transition
            return Transition(
                source=source,
                target=target,
                label=label,
                fair=fair,
            )
        raise ValueError(f"Unsupported transition shape: {transition!r}")

    def _validate_input(self) -> None:
        if not self.states:
            raise ValueError("At least one state is required.")
        if not self.transitions:
            raise ValueError("At least one transition is required.")

        missing_goals = self.goal_states.difference(self.states)
        if missing_goals:
            raise ValueError(
                f"Unknown goal states: {sorted(missing_goals, key=repr)!r}"
            )

        missing_forbidden = self.forbidden_states.difference(self.states)
        if missing_forbidden:
            raise ValueError(
                f"Unknown forbidden states: {sorted(missing_forbidden, key=repr)!r}",
            )

        dimensions = {len(coordinate) for coordinate in self.states.values()}
        if len(dimensions) > 1:
            raise ValueError("All states must use the same coordinate dimension.")

        for transition in self.transitions:
            if (
                transition.source not in self.states
                or transition.target not in self.states
            ):
                raise ValueError(
                    f"Transition references an unknown state: {transition!r}"
                )
            source_coordinate = self.states[transition.source]
            target_coordinate = self.states[transition.target]
            if any(
                target_value < source_value
                for source_value, target_value in zip(
                    source_coordinate,
                    target_coordinate,
                    strict=True,
                )
            ):
                raise ValueError(
                    "Transitions must be monotone non-decreasing in every coordinate: "
                    f"{transition!r}",
                )

    def _build_adjacency(
        self,
        states: Iterable[StateId],
        transitions: Iterable[Transition],
    ) -> dict[StateId, list[StateId]]:
        adjacency: dict[StateId, list[StateId]] = {state: [] for state in states}
        for transition in transitions:
            adjacency[transition.source].append(transition.target)
        return adjacency

    def _tarjan_scc(
        self,
        states: Iterable[StateId],
        adjacency: Mapping[StateId, Sequence[StateId]],
    ) -> list[frozenset[StateId]]:
        index = 0
        stack: list[StateId] = []
        on_stack: set[StateId] = set()
        indices: dict[StateId, int] = {}
        lowlink: dict[StateId, int] = {}
        components: list[frozenset[StateId]] = []

        def strong_connect(state: StateId) -> None:
            nonlocal index
            indices[state] = index
            lowlink[state] = index
            index += 1
            stack.append(state)
            on_stack.add(state)

            for target in adjacency.get(state, ()):
                if target not in indices:
                    strong_connect(target)
                    lowlink[state] = min(lowlink[state], lowlink[target])
                elif target in on_stack:
                    lowlink[state] = min(lowlink[state], indices[target])

            if lowlink[state] == indices[state]:
                component: set[StateId] = set()
                while True:
                    member = stack.pop()
                    on_stack.remove(member)
                    component.add(member)
                    if member == state:
                        break
                components.append(frozenset(component))

        for state in sorted(states, key=repr):
            if state not in indices:
                strong_connect(state)
        return components

    def _is_fair(self, transition: Transition) -> bool:
        if self._fair_transition_predicate is not None:
            return self._fair_transition_predicate(transition)
        return transition.fair

    def _fair_non_goal_subcomplex(
        self,
    ) -> tuple[tuple[StateId, ...], tuple[Transition, ...]]:
        states = tuple(sorted(self.valid_states.difference(self.goal_states), key=repr))
        state_set = set(states)
        edges = tuple(
            transition
            for transition in self.valid_transitions
            if self._is_fair(transition)
            and transition.source in state_set
            and transition.target in state_set
        )
        return states, edges

    def _boundary_matrix_d1(
        self,
        states: Sequence[StateId],
        edges: Sequence[Transition],
    ) -> FloatMatrix:
        state_index = {state: index for index, state in enumerate(states)}
        matrix = np.zeros((len(states), len(edges)), dtype=np.float64)
        for edge_index, transition in enumerate(edges):
            matrix[state_index[transition.source], edge_index] -= 1.0
            matrix[state_index[transition.target], edge_index] += 1.0
        return matrix

    def _boundary_matrix_d2(self, fair_edges: Sequence[Transition]) -> FloatMatrix:
        edge_index = {
            (transition.source, transition.target): index
            for index, transition in enumerate(fair_edges)
        }
        cells = self.two_cells or self._infer_unit_square_two_cells()
        columns: list[FloatMatrix] = []
        for cell in cells:
            column = np.zeros((len(fair_edges),), dtype=np.float64)
            included = False
            missing_boundary_edge = False
            for source, target, sign in cell.boundary:
                index = edge_index.get((source, target))
                if index is None:
                    missing_boundary_edge = True
                    break
                column[index] += float(sign)
                included = True
            if included and not missing_boundary_edge:
                columns.append(column)
        if not columns:
            return np.zeros((len(fair_edges), 0), dtype=np.float64)
        return cast(FloatMatrix, np.column_stack(columns))

    def _infer_unit_square_two_cells(self) -> tuple[TwoCell, ...]:
        dimension = len(next(iter(self.states.values())))
        if dimension < 2:
            return ()

        coordinate_to_state: dict[Coordinate, StateId] = {}
        for state, coordinate in self.states.items():
            if state in self.valid_states:
                coordinate_to_state.setdefault(coordinate, state)

        edge_set = {
            (transition.source, transition.target)
            for transition in self.valid_transitions
        }
        cells: list[TwoCell] = []
        for base_state, base_coordinate in self.states.items():
            if base_state not in self.valid_states:
                continue
            for first_axis in range(dimension):
                for second_axis in range(first_axis + 1, dimension):
                    first_coordinate = self._shift(base_coordinate, first_axis)
                    second_coordinate = self._shift(base_coordinate, second_axis)
                    diagonal_coordinate = self._shift(first_coordinate, second_axis)
                    first_state = coordinate_to_state.get(first_coordinate)
                    second_state = coordinate_to_state.get(second_coordinate)
                    diagonal_state = coordinate_to_state.get(diagonal_coordinate)
                    if (
                        first_state is None
                        or second_state is None
                        or diagonal_state is None
                    ):
                        continue

                    boundary: tuple[BoundaryEdge, ...] = (
                        (base_state, first_state, 1),
                        (first_state, diagonal_state, 1),
                        (second_state, diagonal_state, -1),
                        (base_state, second_state, -1),
                    )
                    if all(
                        (source, target) in edge_set for source, target, _ in boundary
                    ):
                        cells.append(TwoCell(boundary=boundary))
        return tuple(cells)

    def _shift(self, coordinate: Coordinate, axis: int) -> Coordinate:
        shifted = list(coordinate)
        shifted[axis] += 1.0
        return tuple(shifted)

    def _nullspace(self, matrix: FloatMatrix, tolerance: float) -> FloatMatrix:
        _, singular_values, vh = np.linalg.svd(matrix, full_matrices=True)
        rank = int((singular_values > tolerance).sum())
        return vh[rank:].T.copy()

    def _extract_cycle_edges(
        self,
        fair_edges: Sequence[Transition],
        representative: FloatMatrix,
        tolerance: float,
    ) -> tuple[Transition, ...]:
        selected_edges = [
            edge
            for edge, coefficient in zip(fair_edges, representative, strict=True)
            if abs(coefficient) > tolerance
        ]
        selected = {(edge.source, edge.target) for edge in selected_edges}
        adjacency: dict[StateId, list[Transition]] = {}
        for edge in selected_edges:
            adjacency.setdefault(edge.source, []).append(edge)

        visited: set[StateId] = set()
        active: set[StateId] = set()
        stack: list[Transition] = []

        def dfs(state: StateId) -> tuple[Transition, ...] | None:
            visited.add(state)
            active.add(state)
            for edge in adjacency.get(state, ()):
                if (edge.source, edge.target) not in selected:
                    continue
                stack.append(edge)
                if edge.target in active:
                    start = next(
                        index
                        for index, stacked_edge in enumerate(stack)
                        if stacked_edge.source == edge.target
                    )
                    return tuple(stack[start:])
                if edge.target not in visited:
                    found = dfs(edge.target)
                    if found is not None:
                        return found
                stack.pop()
            active.remove(state)
            return None

        for edge in selected_edges:
            if edge.source not in visited:
                found_cycle = dfs(edge.source)
                if found_cycle is not None:
                    return found_cycle
        return tuple(selected_edges)

    def _cycle_states(self, cycle_edges: Sequence[Transition]) -> tuple[StateId, ...]:
        if not cycle_edges:
            return ()
        states = [cycle_edges[0].source]
        states.extend(edge.target for edge in cycle_edges)
        return tuple(states)
