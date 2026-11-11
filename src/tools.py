
try:
    from .storage import save_draft as persist_draft, list_drafts
except ImportError:
    from storage import save_draft as persist_draft, list_drafts


# Example material data.
# In a real project, this can be replaced by a database or API.
MATERIALS = {
    "M01": {
        "name": "Material M01",
        "status": "ready",
        "metadata": {
            "title": "Sample material",
            "description": "A sample material for scheduling"
        },
        "risk_level": "low",
        "risk_reasons": []
    },

    "M002": {
        "name": "Material M002",
        "status": "ready",
        "metadata": {
            "title": "Risky sample material",
            "description": "A sample material containing potentially risky content"
        },
        "risk_level": "high",
        "risk_reasons": [
            "素材包含未经核实的信息",
            "存在内容合规风险"
        ]
    },

    "M003": {
        "name": "Material M003",
        "status": "ready",
        "risk_level": "low",
        "risk_reasons": []
    },

    "M004": {
        "name": "Material M004",
        "status": "ready",
        "metadata": {
            "title": "sample material04",
            "description": "A sample material_04 containing potentially risky content"
        },
        "risk_level": "low",
        "risk_reasons": []
    }
}


# Simulated unavailable slots.
OCCUPIED_SLOTS = ["18:00"]

# Candidate publishing slots.
ALL_SLOTS = ["18:00", "19:00", "20:00", "21:00"]


def read_material(material_id):
    """Read material information and metadata."""
    material = MATERIALS.get(material_id)

    if material is None:
        return {
            "success": False,
            "material_id": material_id,
            "missing": True,
            "message": f"未找到素材 {material_id}。",
            "material": None
        }

    required_fields = ["name", "status", "metadata"]
    missing_fields = [
        field for field in required_fields
        if field not in material or material[field] is None
    ]

    if missing_fields:
        return {
            "success": True,
            "material_id": material_id,
            "missing": True,
            "missing_fields": missing_fields,
            "message": "素材信息不完整。",
            "material": material
        }

    return {
        "success": True,
        "material_id": material_id,
        "missing": False,
        "message": "素材读取成功。",
        "material": material
    }


def check_rules(material_id):
    """Check material review status and risk information."""
    material = MATERIALS.get(material_id)

    if material is None:
        return {
            "success": False,
            "review_status": "not_checked",
            "risk_level": "unknown",
            "risk_reasons": ["素材不存在"],
            "can_schedule": False,
            "message": "无法审核：素材不存在。"
        }

    if material.get("status") != "ready":
        return {
            "success": True,
            "review_status": "blocked",
            "risk_level": material.get("risk_level", "high"),
            "risk_reasons": material.get(
                "risk_reasons",
                ["素材状态不是 ready"]
            ),
            "can_schedule": False,
            "message": "素材未达到排期条件。"
        }

    risk_level = material.get("risk_level")
    risk_reasons = material.get("risk_reasons", [])

    # Unknown or invalid risk levels should be blocked
    if risk_level not in ["low", "medium", "high"]:
        return {
            "success": True,
            "review_status": "blocked",
            "risk_level": "unknown",
            "risk_reasons": ["风险等级缺失或无效"],
            "can_schedule": False,
            "message": "风险等级无法确认，阻断排期。"
        }

    if risk_level == "high":
        return {
            "success": True,
            "review_status": "blocked",
            "risk_level": risk_level,
            "risk_reasons": risk_reasons,
            "can_schedule": False,
            "message": "发现高风险，阻断排期。"
        }

    if risk_level == "medium":
        return {
            "success": True,
            "review_status": "needs_review",
            "risk_level": risk_level,
            "risk_reasons": risk_reasons,
            "can_schedule": False,
            "message": "存在待处理风险，需要人工审核。"
        }

    return {
        "success": True,
        "review_status": "passed",
        "risk_level": "low",
        "risk_reasons": risk_reasons,
        "can_schedule": True,
        "message": "审核通过，无明显风险。"
    }


def query_slots(material_id=None):
    """
    Query available time slots.
    Both manually occupied slots and existing saved drafts
    are considered.
    """
    drafts_result = list_drafts()

    if not drafts_result["success"]:
        return drafts_result

    occupied = set(OCCUPIED_SLOTS)

    for draft in drafts_result["drafts"]:
        is_saved = (
            draft.get("draft_status") == "saved"
            or draft.get("status") == "pending_confirmation"
        )

        if not is_saved:
            continue

        publish_time = draft.get("publish_time")

        if publish_time:
            occupied.add(publish_time)

    available = [
        slot for slot in ALL_SLOTS
        if slot not in occupied
    ]

    return {
        "success": True,
        "occupied": sorted(occupied),
        "available": available,
        "message": "时段查询成功。"
    }


def save_schedule_draft(
    material_id,
    publish_time,
    schedule_request=None
):
    """
    Final validation before saving.
    Never performs real publishing.
    """
    material_result = read_material(material_id)

    if not material_result["success"] or material_result.get("missing"):
        return {
            "success": False,
            "message": "素材信息缺失，无法保存排期草稿。"
        }

    review_result = check_rules(material_id)

    if not review_result["success"] or not review_result["can_schedule"]:
        return {
            "success": False,
            "message": "审核未通过，无法保存排期草稿。",
            "review": review_result
        }

    slots_result = query_slots()

    if not slots_result["success"]:
        return {
            "success": False,
            "message": slots_result["message"]
        }

    if publish_time not in ALL_SLOTS:
        return {
            "success": False,
            "message": "所选时间不在系统支持的时段范围内。"
        }

    # Idempotency check happens in storage as well.
    # This check prevents saving a time already occupied by another draft.
    if publish_time in OCCUPIED_SLOTS:
        return {
            "success": False,
            "message": f"{publish_time} 已被占用。",
            "available": slots_result["available"]
        }

    existing_drafts = [
        draft for draft in slots_result.get("drafts", [])
        if draft.get("publish_time") == publish_time
    ]

    if publish_time not in slots_result["available"]:
        # A matching draft for the same material/time is an idempotent retry.
        existing = next(
            (
                draft for draft in list_drafts().get("drafts", [])
                if draft.get("material_id") == material_id
                and draft.get("publish_time") == publish_time
            ),
            None
        )

        if existing:
            return {
                "success": True,
                "created": False,
                "duplicate": True,
                "message": "相同排期草稿已经存在。",
                "draft": existing
            }

        return {
            "success": False,
            "message": f"{publish_time} 已被其他排期占用。",
            "available": slots_result["available"]
        }

    return persist_draft(
        material_id,
        publish_time,
        schedule_request=schedule_request
    )
