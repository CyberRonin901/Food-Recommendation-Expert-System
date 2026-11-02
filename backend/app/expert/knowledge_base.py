import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
import yaml

from app.expert.schemas import (
    ALLOWED_FACTS,
    VALID_FACT_PREFIXES,
    Question,
    Rule,
)

RULES_DIR = Path(__file__).resolve().parent / "rules"

ALLOWED_BASIS = {
    "formula",
    "guideline",
    "guideline_derived",
    "label_claim",
    "team_defined",
}


def extract_facts_from_condition(cond: Any) -> Set[str]:
    """Finds all fact names referenced in a condition."""
    facts = set()
    if isinstance(cond, dict):
        if "fact" in cond:
            facts.add(cond["fact"])
        if "all" in cond and isinstance(cond["all"], list):
            for sub in cond["all"]:
                facts.update(extract_facts_from_condition(sub))
        if "any" in cond and isinstance(cond["any"], list):
            for sub in cond["any"]:
                facts.update(extract_facts_from_condition(sub))
        if "not" in cond:
            facts.update(extract_facts_from_condition(cond["not"]))
    return facts


def extract_facts_from_actions(actions: List[Dict[str, Any]]) -> Set[str]:
    """Finds all fact names written or referenced in actions."""
    facts = set()
    for act in actions:
        if "set" in act and "fact" in act["set"]:
            facts.add(act["set"]["fact"])
        if "compute" in act and "fact" in act["compute"]:
            facts.add(act["compute"]["fact"])
            for arg in act["compute"].get("args", []):
                facts.add(arg)
        if "tighten_max" in act and "limit" in act["tighten_max"]:
            facts.add(f"constraint.{act['tighten_max']['limit']}")
        if "tighten_min" in act and "limit" in act["tighten_min"]:
            facts.add(f"constraint.{act['tighten_min']['limit']}")
    return facts


class KnowledgeBase:
    def __init__(self, rules_dir: Optional[Path] = None):
        self.rules_dir = rules_dir or RULES_DIR
        self.rules: List[Rule] = []
        self.rules_by_id: Dict[str, Rule] = {}
        self.rules_by_layer: Dict[str, List[Rule]] = {}
        self.questions: List[Question] = []
        self.questions_by_id: Dict[str, Question] = {}
        self.fact_to_reading_rules: Dict[str, List[str]] = {}

        self.load()

    def load(self) -> None:
        self.rules.clear()
        self.rules_by_id.clear()
        self.rules_by_layer.clear()
        self.questions.clear()
        self.questions_by_id.clear()
        self.fact_to_reading_rules.clear()

        rule_files = [
            "00_derived.yaml",
            "01_constraints.yaml",
            "04_safety.yaml",
            "02_food_classes.yaml",
            "03_recommend.yaml",
        ]

        for fname in rule_files:
            fpath = self.rules_dir / fname
            if not fpath.exists():
                raise FileNotFoundError(f"Missing required rule file: {fpath}")

            with open(fpath, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)

            layer = data.get("layer", "")
            raw_rules = data.get("rules", [])

            for item in raw_rules:
                rule_id = item.get("id")
                if not rule_id:
                    raise ValueError(f"Rule missing 'id' in {fname}: {item}")
                if rule_id in self.rules_by_id:
                    raise ValueError(f"Duplicate rule id '{rule_id}' found in {fname}")

                basis = item.get("basis")
                if basis and basis not in ALLOWED_BASIS:
                    raise ValueError(f"Rule '{rule_id}' has invalid basis '{basis}'. Allowed: {ALLOWED_BASIS}")

                source = item.get("source")
                if not source or str(source).strip() == "":
                    raise ValueError(f"Rule '{rule_id}' has empty or missing 'source'")

                rule = Rule(
                    id=rule_id,
                    name=item.get("name", rule_id),
                    priority=item.get("priority", 0),
                    condition=item.get("if"),
                    then=item.get("then", []),
                    layer=layer,
                    basis=basis,
                    source=source,
                    note=item.get("note"),
                )

                self.rules.append(rule)
                self.rules_by_id[rule.id] = rule
                self.rules_by_layer.setdefault(layer, []).append(rule)

                # Index fact reads
                cond_facts = extract_facts_from_condition(rule.condition)
                for f_name in cond_facts:
                    self.fact_to_reading_rules.setdefault(f_name, []).append(rule.id)

        # Load questions.yaml
        q_path = self.rules_dir / "questions.yaml"
        if q_path.exists():
            with open(q_path, "r", encoding="utf-8") as f:
                q_data = yaml.safe_load(f)
            for q_raw in q_data.get("questions", []):
                q = Question(**q_raw)
                self.questions.append(q)
                self.questions_by_id[q.id] = q

    def get_phase_a_rules(self) -> List[Rule]:
        """Phase A: user facts -> derived -> constraints -> safety."""
        return (
            self.rules_by_layer.get("derived", [])
            + self.rules_by_layer.get("constraint", [])
            + self.rules_by_layer.get("safety", [])
        )

    def get_phase_b_rules(self) -> List[Rule]:
        """Phase B: candidate food -> classify tags."""
        return self.rules_by_layer.get("food_class", [])

    def get_phase_c_rules(self) -> List[Rule]:
        """Phase C: food + tags + constraints -> recommendation certainty factors."""
        return self.rules_by_layer.get("recommend", [])


# Singleton instance for application runtime
_kb_instance: Optional[KnowledgeBase] = None


def get_knowledge_base() -> KnowledgeBase:
    global _kb_instance
    if _kb_instance is None:
        _kb_instance = KnowledgeBase()
    return _kb_instance

