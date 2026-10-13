"""Resolve scalar URDF mimic constraints for a static, bounded reference pose.

No dynamics, joint commands or measured joint trajectories are inferred here.
Each dependency component has one independent coordinate. Intersect its scalar
limits before choosing the value nearest the importer's existing reference.
"""
from __future__ import annotations

import math
from fractions import Fraction
from typing import Any

_BOUND = Fraction(10000)


def _exact(value: int | float) -> Fraction:
    if type(value) not in (int, float) or not math.isfinite(value) or abs(value) > _BOUND:
        raise ValueError("Неверное число в связи mimic.")
    # Preserve the decimal spelling of the parsed number. Interval arithmetic
    # remains exact even for long chains, negative/zero ratios and tiny factors.
    return Fraction(str(value))


def resolve_mimic_reference(nodes: list[dict[str, Any]], *, max_depth: int = 48) -> int:
    """Set reference values only after the whole dependency graph is validated."""
    joints = {joint["name"]: joint for node in nodes for joint in node["joints"]}
    count = sum("mimic" in joint for joint in joints.values())
    if not count:
        return 0
    # q_joint = factor * q_root + offset; depth is independent of XML order.
    expressions: dict[str, tuple[str, Fraction, Fraction, int]] = {}
    visiting: set[str] = set()

    def expression(name: str) -> tuple[str, Fraction, Fraction, int]:
        if name in expressions:
            return expressions[name]
        if name in visiting:
            raise ValueError("Цикл в связях mimic.")
        if len(visiting) > max_depth:
            raise ValueError("Слишком глубокая цепочка mimic.")
        visiting.add(name)
        joint = joints[name]
        mimic = joint.get("mimic")
        if mimic is None:
            result = (name, Fraction(1), Fraction(0), 0)
        else:
            source = mimic["joint"]
            if source not in joints:
                raise ValueError("Mimic ссылается на неизвестный или неподвижный сустав.")
            if (joint["type"] == "prismatic") != (joints[source]["type"] == "prismatic"):
                raise ValueError("Связь mimic между линейным и угловым суставами не поддержана.")
            root, factor, offset, depth = expression(source)
            multiplier = _exact(mimic["multiplier"])
            result = (root, multiplier * factor, multiplier * offset + _exact(mimic["offset"]),
                      depth + 1)
            if result[3] > max_depth:
                raise ValueError("Слишком глубокая цепочка mimic.")
        visiting.remove(name)
        expressions[name] = result
        return result

    for name in joints:
        expression(name)
    domains: dict[str, tuple[Fraction, Fraction]] = {}
    for name, joint in joints.items():
        root, factor, offset, _ = expressions[name]
        limits = joint["range"]
        lower, upper = map(_exact, limits) if limits is not None else (-_BOUND, _BOUND)
        low, high = domains.get(root, (-_BOUND, _BOUND))
        if not factor:
            if not lower <= offset <= upper:
                raise ValueError("Пределы суставов несовместимы со связями mimic.")
        else:
            first, second = (lower - offset) / factor, (upper - offset) / factor
            low, high = max(low, min(first, second)), min(high, max(first, second))
            if low > high:
                raise ValueError("Пределы суставов несовместимы со связями mimic.")
        domains[root] = (low, high)
    chosen = {
        root: max(low, min(_exact(joints[root]["value"]), high))
        for root, (low, high) in domains.items()
    }
    values = {
        name: float(factor * chosen[root] + offset)
        for name, (root, factor, offset, _) in expressions.items()
    }
    for name, value in values.items():
        joints[name]["value"] = value
    return count
