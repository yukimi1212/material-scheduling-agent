
import json
import re
from pathlib import Path
from datetime import datetime


BASE_DIR = Path(__file__).resolve().parent.parent
DRAFT_DIR = BASE_DIR / "data" / "drafts"


def _validate(material_id, publish_time):
    if not isinstance(material_id, str) or not re.fullmatch(
        r"[A-Za-z0-9_-]+", material_id
    ):
        raise ValueError("Invalid material ID")

    if not isinstance(publish_time, str) or not re.fullmatch(
        r"(?:[01]\d|2[0-3]):[0-5]\d", publish_time
    ):
        raise ValueError("Invalid publish time")


def _path(material_id, publish_time):
    _validate(material_id, publish_time)
    return DRAFT_DIR / (
        f"{material_id}_{publish_time.replace(':', '')}.json"
    )


def list_drafts():
    """Return all persisted scheduling drafts."""
    try:
        DRAFT_DIR.mkdir(parents=True, exist_ok=True)
        drafts = []

        for path in sorted(DRAFT_DIR.glob("*.json")):
            with path.open("r", encoding="utf-8") as file:
                draft = json.load(file)

            if not isinstance(draft, dict):
                raise ValueError(f"Invalid draft file: {path.name}")

            drafts.append(draft)

        return {
            "success": True,
            "drafts": drafts,
            "count": len(drafts)
        }

    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return {
            "success": False,
            "message": f"读取草稿失败：{exc}"
        }


def get_draft(material_id, publish_time):
    try:
        path = _path(material_id, publish_time)

        if not path.exists():
            return {
                "success": False,
                "message": "草稿不存在"
            }

        with path.open("r", encoding="utf-8") as file:
            draft = json.load(file)

        return {
            "success": True,
            "draft": draft
        }

    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return {
            "success": False,
            "message": f"读取草稿失败：{exc}"
        }


def save_draft(material_id, publish_time, schedule_request=None):
    """
    Save a draft idempotently.

    The same material + publish time can only produce one file.
    A repeated request returns the existing draft instead of
    creating another copy.
    """

    try:
        path = _path(material_id, publish_time)
        DRAFT_DIR.mkdir(parents=True, exist_ok=True)

        if path.exists():
            with path.open("r", encoding="utf-8") as file:
                existing = json.load(file)

            return {
                "success": True,
                "created": False,
                "duplicate": True,
                "message": "相同排期草稿已经存在，未重复创建。",
                "draft": existing
            }

        draft = {
            "material_id": material_id,
            "publish_time": publish_time,
            "schedule_request": schedule_request or {},
            "review_status": "passed",
            "schedule_status": "pending_confirmation",
            "draft_status": "saved",
            "created_at": datetime.now().isoformat(timespec="seconds")
        }

        # Exclusive creation prevents accidental overwrite.
        with path.open("x", encoding="utf-8") as file:
            json.dump(draft, file, ensure_ascii=False, indent=4)

        return {
            "success": True,
            "created": True,
            "duplicate": False,
            "message": "草稿保存成功。",
            "draft": draft
        }

    except FileExistsError:
        # Another request may have created the same draft.
        return get_draft(material_id, publish_time)

    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return {
            "success": False,
            "created": False,
            "message": f"草稿保存失败：{exc}"
        }
