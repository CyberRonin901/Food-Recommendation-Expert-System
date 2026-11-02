from typing import Any, Dict, List, Optional, Set, Tuple


class WorkingMemory:
    def __init__(self, initial_facts: Optional[Dict[str, Any]] = None):
        self.facts: Dict[str, Any] = {}
        self.constraints: Dict[str, Any] = {
            "max_calories": None,
            "min_calories": None,
            "min_protein": None,
            "max_carbs": None,
            "max_fat": None,
            "min_fiber": None,
            "max_sugars": None,
            "max_sodium": None,
            "max_cholesterol": None,
            "goals": [],
            "exclude_keywords": [],
            "warnings": [],
        }
        self.tags: Set[str] = set()
        self.fired: Set[str] = set()
        self.trace: List[Dict[str, Any]] = []
        self.cf: float = 0.0
        self.cf_history: List[float] = []
        self.reasons: List[str] = []

        if initial_facts:
            for k, v in initial_facts.items():
                self.set_fact(k, v)

    def get_fact(self, name: str) -> Any:
        """Resolves fact name to its value in working memory."""
        clean_name = name[1:] if name.startswith("$") else name

        if clean_name == "food.tags":
            return list(self.tags)
        if clean_name == "constraint.goals":
            return list(self.constraints.get("goals", []))
        if clean_name == "constraint.exclude_keywords":
            return list(self.constraints.get("exclude_keywords", []))
        if clean_name == "constraint.warnings":
            return list(self.constraints.get("warnings", []))
        if clean_name.startswith("constraint."):
            field = clean_name.split(".", 1)[1]
            return self.constraints.get(field)

        return self.facts.get(clean_name, None)

    def set_fact(self, name: str, value: Any) -> None:
        clean_name = name[1:] if name.startswith("$") else name
        self.facts[clean_name] = value

        if clean_name.startswith("constraint."):
            field = clean_name.split(".", 1)[1]
            if field in self.constraints:
                self.constraints[field] = value

    def tighten_max(self, limit: str, val: float) -> Tuple[Optional[float], float]:
        old = self.constraints.get(limit)
        new = val if old is None else min(old, val)
        self.constraints[limit] = new
        self.facts[f"constraint.{limit}"] = new
        return old, new

    def tighten_min(self, limit: str, val: float) -> Tuple[Optional[float], float]:
        old = self.constraints.get(limit)
        new = val if old is None else max(old, val)
        self.constraints[limit] = new
        self.facts[f"constraint.{limit}"] = new
        return old, new

    def add_goal(self, goal: str) -> bool:
        if goal not in self.constraints["goals"]:
            self.constraints["goals"].append(goal)
            self.facts["constraint.goals"] = list(self.constraints["goals"])
            return True
        return False

    def add_exclude(self, words: List[str]) -> List[str]:
        added = []
        for w in words:
            if w not in self.constraints["exclude_keywords"]:
                self.constraints["exclude_keywords"].append(w)
                added.append(w)
        self.facts["constraint.exclude_keywords"] = list(self.constraints["exclude_keywords"])
        return added

    def add_warning(self, msg: str) -> bool:
        if msg not in self.constraints["warnings"]:
            self.constraints["warnings"].append(msg)
            self.facts["constraint.warnings"] = list(self.constraints["warnings"])
            return True
        return False

    def add_tag(self, tag: str) -> bool:
        if tag not in self.tags:
            self.tags.add(tag)
            return True
        return False

