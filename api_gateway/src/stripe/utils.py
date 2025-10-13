from typing import Optional, Dict

def build_subscription_metadata(*, role: str, role_entity_id: Optional[str] = None, plan_type: Optional[str] = None, source: Optional[str] = None) -> Dict[str, str]:
    meta: Dict[str, str] = {"role": role}
    if role_entity_id:
        meta["role_entity_id"] = role_entity_id
    if plan_type:
        meta["plan_type"] = plan_type
    if source:
        meta["source"] = source
    return meta
