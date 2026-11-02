#!/usr/bin/env python3
import re
import sys
from app.expert.knowledge_base import (
    ALLOWED_BASIS,
    KnowledgeBase,
    extract_facts_from_actions,
    extract_facts_from_condition,
)
from app.expert.schemas import ALLOWED_FACTS


def run_linter() -> int:
    print("Linting Expert System Knowledge Base...")
    errors = []

    try:
        kb = KnowledgeBase()
    except Exception as e:
        print(f"FATAL: Could not load knowledge base: {e}", file=sys.stderr)
        return 1

    # 1. Total rule count
    total_rules = len(kb.rules)
    print(f"Loaded {total_rules} rules across {len(kb.rules_by_layer)} layers.")

    layer_order = ["derived", "constraint", "safety", "food_class", "recommend"]
    for lyr in layer_order:
        lyr_rules = kb.rules_by_layer.get(lyr, [])
        print(f"  - Layer '{lyr}': {len(lyr_rules)} rules")

    if total_rules != 85:
        print(f"Note: Total rules is {total_rules} (Section 8 summary lists 85).")

    # 2. Check each rule's fact vocabulary and fields
    for r in kb.rules:
        # Check source and basis
        if not r.source or str(r.source).strip() == "":
            errors.append(f"Rule {r.id}: 'source' field is missing or empty")
        if r.basis not in ALLOWED_BASIS:
            errors.append(f"Rule {r.id}: invalid basis '{r.basis}'")

        # Check condition facts
        cond_facts = extract_facts_from_condition(r.condition)
        for cf in cond_facts:
            clean_cf = cf[1:] if cf.startswith("$") else cf
            if clean_cf not in ALLOWED_FACTS:
                errors.append(f"Rule {r.id}: condition references unknown fact '{cf}'")

        # Check action facts
        act_facts = extract_facts_from_actions(r.then)
        for af in act_facts:
            clean_af = af[1:] if af.startswith("$") else af
            if clean_af not in ALLOWED_FACTS:
                errors.append(f"Rule {r.id}: action references unknown fact '{af}'")

    # 3. Check questions.yaml
    print(f"Loaded {len(kb.questions)} consultation questions.")
    for q in kb.questions:
        if q.fact not in ALLOWED_FACTS:
            errors.append(f"Question {q.id}: references unknown fact '{q.fact}'")

        # Check rule references inside 'why' text (e.g. "rule D06")
        referenced_rules = re.findall(r"\b([DCSF][0-9]{2}|R[0-9]{2})\b", q.why)
        for ref_id in referenced_rules:
            if ref_id not in kb.rules_by_id:
                errors.append(f"Question {q.id}: why text cites non-existent rule '{ref_id}'")

    if errors:
        print(f"\nFound {len(errors)} LINT ERRORS:", file=sys.stderr)
        for err in errors:
            print(f"  ERROR: {err}", file=sys.stderr)
        return 1

    print("\n✓ Knowledge base lint passed successfully! All rules and questions valid.\n")
    return 0


if __name__ == "__main__":
    sys.exit(run_linter())

