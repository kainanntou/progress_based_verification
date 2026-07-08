import pytest

from progress_based_verification import (
    ProgressBasedVerificationEngine,
    StateId,
    Transition,
)


def test_deadlock_inverse_lock_order() -> None:
    states: dict[StateId, tuple[float, float]] = {
        "start": (0.0, 0.0),
        "p1_holds_a": (1.0, 0.0),
        "p2_holds_b": (0.0, 1.0),
        "deadlocked_wait": (1.0, 1.0),
        "goal": (2.0, 2.0),
    }
    transitions = (
        Transition("start", "p1_holds_a", "p1_lock_a"),
        Transition("start", "p2_holds_b", "p2_lock_b"),
        Transition("p1_holds_a", "deadlocked_wait", "p2_lock_b_then_wait_a"),
        Transition("p2_holds_b", "deadlocked_wait", "p1_lock_a_then_wait_b"),
    )

    engine = ProgressBasedVerificationEngine(
        states=states,
        transitions=transitions,
        forbidden_states=(),
        goal_states={"goal"},
    )

    deadlocks = engine.detect_deadlocks()
    by_state = {deadlock.state: deadlock for deadlock in deadlocks}

    assert "deadlocked_wait" in by_state
    assert by_state["deadlocked_wait"].persistent_reachable == frozenset(
        {"deadlocked_wait"},
    )
    assert by_state["deadlocked_wait"].persistent_reachable.isdisjoint({"goal"})


def test_livelock_try_lock_release_loop() -> None:
    states: dict[StateId, tuple[float, float]] = {
        "try_lock_a": (0.0, 0.0),
        "try_lock_b": (0.0, 0.0),
        "release_and_retry": (0.0, 0.0),
        "goal": (1.0, 1.0),
    }
    transitions = (
        Transition("try_lock_a", "try_lock_b", "try_a_succeeds", fair=True),
        Transition("try_lock_b", "release_and_retry", "try_b_fails", fair=True),
        Transition("release_and_retry", "try_lock_a", "release_a", fair=True),
    )

    engine = ProgressBasedVerificationEngine(
        states=states,
        transitions=transitions,
        goal_states={"goal"},
    )

    livelocks = engine.detect_livelocks()

    assert len(livelocks) == 1
    assert livelocks[0].homology_dimension > 0
    assert tuple(edge.label for edge in livelocks[0].cycle_edges) == (
        "try_a_succeeds",
        "try_b_fails",
        "release_a",
    )
    assert livelocks[0].cycle_states[0] == livelocks[0].cycle_states[-1]


def test_empty_state_complex_raises_value_error() -> None:
    with pytest.raises(ValueError, match="At least one state"):
        ProgressBasedVerificationEngine(states={}, transitions=())


def test_empty_transition_complex_raises_value_error() -> None:
    with pytest.raises(ValueError, match="At least one transition"):
        ProgressBasedVerificationEngine(states={"start": (0.0, 0.0)}, transitions=())


def test_disconnected_isolated_state_is_reported_as_deadlock() -> None:
    states: dict[StateId, tuple[float, float]] = {
        "start": (0.0, 0.0),
        "goal": (1.0, 0.0),
        "isolated": (0.0, 1.0),
    }
    transitions = (Transition("start", "goal", "finish"),)

    engine = ProgressBasedVerificationEngine(
        states=states,
        transitions=transitions,
        goal_states={"goal"},
    )

    deadlocks = engine.detect_deadlocks()
    deadlock_states = {deadlock.state for deadlock in deadlocks}

    assert "isolated" in deadlock_states
    assert "start" not in deadlock_states
    assert "goal" not in deadlock_states


def test_unfair_cycle_is_not_reported_as_livelock() -> None:
    states: dict[StateId, tuple[float, float]] = {
        "spin_a": (0.0, 0.0),
        "spin_b": (0.0, 0.0),
        "goal": (1.0, 1.0),
    }
    transitions = (
        Transition("spin_a", "spin_b", "unfair_spin_forward", fair=False),
        Transition("spin_b", "spin_a", "unfair_spin_backward", fair=False),
    )

    engine = ProgressBasedVerificationEngine(
        states=states,
        transitions=transitions,
        goal_states={"goal"},
    )

    assert engine.detect_livelocks() == []
