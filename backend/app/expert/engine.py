import re
from typing import Any, Dict, List, Optional, Union
from app.expert.functions import WHITELISTED_FUNCTIONS
from app.expert.memory import WorkingMemory
from app.expert.schemas import Rule


def combine_certainty(a: float, b: float) -> float:
    """
    MYCIN Certainty Factor combination:
    both >= 0:   a + b * (1 - a)
    both <= 0:   a + b * (1 + a)
    mixed signs: (a + b) / (1 - min(|a|, |b|))
    Clamped to [-1.0, 1.0].
    """
    if a == 0.0:
        res = b
    elif b == 0.0:
        res = a
    elif a >= 0.0 and b >= 0.0:
        res = a + b * (1.0 - a)
    elif a <= 0.0 and b <= 0.0:
        res = a + b * (1.0 + a)
    else:
        denom = 1.0 - min(abs(a), abs(b))
        if denom == 0.0:
            res = 0.0
        else:
            res = (a + b) / denom

    return round(max(-1.0, min(1.0, res)), 4)


def count_specificity(cond: Union[str, Dict[str, Any]]) -> int:
    """Computes condition specificity by counting atomic leaf checks."""
    if cond == "always":
        return 0
    if not isinstance(cond, dict):
        return 1

    if "all" in cond and isinstance(cond["all"], list):
        return sum(count_specificity(c) for c in cond["all"])
    if "any" in cond and isinstance(cond["any"], list):
        return sum(count_specificity(c) for c in cond["any"])
    if "not" in cond:
        return count_specificity(cond["not"])

    return 1


def evaluate_condition(cond: Union[str, Dict[str, Any]], memory: WorkingMemory) -> bool:
    """
    Evaluates a condition against working memory.
    Unknown facts evaluate to False (never error).
    """
    if cond == "always":
        return True

    if not isinstance(cond, dict):
        return False

    if "all" in cond:
        return all(evaluate_condition(c, memory) for c in cond["all"])

    if "any" in cond:
        return any(evaluate_condition(c, memory) for c in cond["any"])

    if "not" in cond:
        return not evaluate_condition(cond["not"], memory)

    fact_name = cond.get("fact")
    if not fact_name:
        return False

    val = memory.get_fact(fact_name)

    # Operator: exists
    if "exists" in cond:
        target_bool = bool(cond["exists"])
        return (val is not None) == target_bool

    # For all other operators, an unknown fact is False
    if val is None:
        return False

    # Operator: is
    if "is" in cond:
        target = cond["is"]
        if isinstance(target, bool):
            return bool(val) == target
        return str(val).lower() == str(target).lower()

    # Operator: is_not
    if "is_not" in cond:
        target = cond["is_not"]
        return str(val).lower() != str(target).lower()

    # Operator: in
    if "in" in cond:
        target_list = [str(x).lower() for x in cond["in"]]
        return str(val).lower() in target_list

    # Operator: gte
    if "gte" in cond:
        try:
            return float(val) >= float(cond["gte"])
        except (ValueError, TypeError):
            return False

    # Operator: gt
    if "gt" in cond:
        try:
            return float(val) > float(cond["gt"])
        except (ValueError, TypeError):
            return False

    # Operator: lte
    if "lte" in cond:
        try:
            return float(val) <= float(cond["lte"])
        except (ValueError, TypeError):
            return False

    # Operator: lt
    if "lt" in cond:
        try:
            return float(val) < float(cond["lt"])
        except (ValueError, TypeError):
            return False

    # Operator: between
    if "between" in cond:
        bounds = cond["between"]
        try:
            return float(bounds[0]) <= float(val) <= float(bounds[1])
        except (ValueError, TypeError, IndexError):
            return False

    # Operator: has
    if "has" in cond:
        target = str(cond["has"]).lower()
        if isinstance(val, (list, set, tuple)):
            return any(str(x).lower() == target for x in val)
        return False

    # Operator: has_any
    if "has_any" in cond:
        targets = {str(x).lower() for x in cond["has_any"]}
        if isinstance(val, (list, set, tuple)):
            return any(str(x).lower() in targets for x in val)
        return False

    return False


def interpolate_text(text: str, memory: WorkingMemory) -> str:
    """Interpolates {fact.name} placeholders with real values from working memory."""
    def replacer(match: re.Match) -> str:
        var_name = match.group(1)
        val = memory.get_fact(var_name)
        if val is None:
            return ""
        if isinstance(val, float):
            return f"{val:g}"
        return str(val)

    return re.sub(r"\{([a-zA-Z0-9_\.]+)\}", replacer, text)


def execute_action(action: Dict[str, Any], memory: WorkingMemory, rule_id: str) -> Optional[str]:
    """Executes a single rule action against working memory."""
    if "set" in action:
        set_data = action["set"]
        fact_name = set_data["fact"]
        val = set_data["value"]
        if isinstance(val, str) and val.startswith("$"):
            val = memory.get_fact(val[1:])
        memory.set_fact(fact_name, val)
        return f"{fact_name} = {val}"

    if "compute" in action:
        comp_data = action["compute"]
        fact_name = comp_data["fact"]
        fn_name = comp_data["fn"]
        arg_names = comp_data.get("args", [])

        fn = WHITELISTED_FUNCTIONS.get(fn_name)
        if not fn:
            raise ValueError(f"Unknown compute function '{fn_name}' in rule {rule_id}")

        args = [memory.get_fact(a) for a in arg_names]
        if any(a is None for a in args):
            return f"skipped compute for {fact_name} (missing arguments)"

        if fn_name == "daily_calories":
            result, floor_applied = fn(*args)
            memory.set_fact("derived.floor_applied", floor_applied)
            memory.set_fact(fact_name, round(result))
            return f"{fact_name} = {round(result)} (floor_applied={floor_applied})"
        else:
            result = fn(*args)
            if fact_name == "derived.meal_calorie_budget":
                result = round(result)
            memory.set_fact(fact_name, result)
            return f"{fact_name} = {result}"

    if "tighten_max" in action:
        t_data = action["tighten_max"]
        limit = t_data["limit"]
        raw_val = t_data["value"]
        if isinstance(raw_val, str) and raw_val.startswith("$"):
            resolved = memory.get_fact(raw_val[1:])
            if resolved is None:
                return f"skipped tighten_max {limit} (unresolved {raw_val})"
            val = float(resolved)
        else:
            val = float(raw_val)

        old, new = memory.tighten_max(limit, val)
        old_str = f"{old:g}" if old is not None else "none"
        return f"{limit}: {old_str} -> {new:g}"

    if "tighten_min" in action:
        t_data = action["tighten_min"]
        limit = t_data["limit"]
        raw_val = t_data["value"]
        if isinstance(raw_val, str) and raw_val.startswith("$"):
            resolved = memory.get_fact(raw_val[1:])
            if resolved is None:
                return f"skipped tighten_min {limit} (unresolved {raw_val})"
            val = float(resolved)
        else:
            val = float(raw_val)

        old, new = memory.tighten_min(limit, val)
        old_str = f"{old:g}" if old is not None else "none"
        return f"{limit}: {old_str} -> {new:g}"

    if "add_goal" in action:
        goal = action["add_goal"]
        added = memory.add_goal(goal)
        return f"goal {goal} added" if added else None

    if "add_exclude" in action:
        words = action["add_exclude"]
        if isinstance(words, str):
            words = [words]
        added = memory.add_exclude(words)
        return f"exclude keywords added: {added}" if added else None

    if "warn" in action:
        text = interpolate_text(action["warn"], memory)
        memory.add_warning(text)
        return f"warning added: {text}"

    if "tag" in action:
        tag_name = action["tag"]
        memory.add_tag(tag_name)
        return f"tagged {tag_name}"

    if "score" in action:
        score_data = action["score"]
        cf_val = float(score_data["cf"])
        raw_reason = score_data.get("reason", "")
        formatted_reason = interpolate_text(raw_reason, memory)

        new_cf = combine_certainty(memory.cf, cf_val)
        memory.cf = new_cf
        memory.cf_history.append(new_cf)
        memory.reasons.append(formatted_reason)
        return f"score cf {cf_val}: {formatted_reason} (combined={new_cf})"

    return None


def run_forward_chaining(
    rules: List[Rule],
    memory: WorkingMemory,
    max_cycles: int = 500,
) -> List[Dict[str, Any]]:
    """
    Forward-chaining inference engine loop:
    1. Match: evaluate condition of un-fired rules.
    2. Conflict Resolution: sort by (-priority, -specificity, id).
    3. Fire top rule and apply actions to working memory.
    4. Repeat until quiescence or max_cycles.
    """
    cycle = 1
    cycle_trace: List[Dict[str, Any]] = []

    while cycle <= max_cycles:
        candidates: List[Rule] = []
        for r in rules:
            if r.id not in memory.fired:
                if evaluate_condition(r.condition, memory):
                    candidates.append(r)

        if not candidates:
            break

        # Conflict resolution: higher priority, more specific, rule id ascending
        candidates.sort(
            key=lambda r: (
                -r.priority,
                -count_specificity(r.condition),
                r.id,
            )
        )

        chosen = candidates[0]
        memory.fired.add(chosen.id)

        changes: List[str] = []
        for act in chosen.then:
            ch = execute_action(act, memory, chosen.id)
            if ch:
                changes.append(ch)

        trace_entry = {
            "cycle": cycle,
            "rule": chosen.id,
            "name": chosen.name,
            "change": "; ".join(changes),
        }
        memory.trace.append(trace_entry)
        cycle_trace.append(trace_entry)
        cycle += 1

    if cycle > max_cycles:
        raise RuntimeError(f"Forward-chaining engine exceeded max cycle limit of {max_cycles}")

    return cycle_trace

