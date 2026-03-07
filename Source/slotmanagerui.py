from __future__ import annotations

import os
from datetime import date, datetime, time, timedelta
import xml.etree.ElementTree as ET

import pandas as pd
import streamlit as st
from streamlit_sortables import sort_items

BASE_DIR = os.path.dirname(__file__)
XML_PATH = os.path.join(BASE_DIR, "pupil_slots.xml")
START_HOUR = 8
END_HOUR = 17
SLOT_DURATION_MINUTES = 60
MAX_STUDENTS_PER_TIMESLOT = 8
WEEKDAY_LABELS = [
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
]
WEEKDAY_ANCHOR_DATES = {
    0: date(2000, 1, 3),  # Monday
    1: date(2000, 1, 4),  # Tuesday
    2: date(2000, 1, 5),  # Wednesday
    3: date(2000, 1, 6),  # Thursday
    4: date(2000, 1, 7),  # Friday
    5: date(2000, 1, 8),  # Saturday
    6: date(2000, 1, 9),  # Sunday
}

CONFIG = {
    "SUPER_USER": "Braincal2009@",
}


def _default_day_config() -> dict[str, str]:
    return {
        "active": "1",
        "start_hour": str(START_HOUR),
        "end_hour": str(END_HOUR),
        "slot_duration_minutes": str(SLOT_DURATION_MINUTES),
        "max_students_per_timeslot": str(MAX_STUDENTS_PER_TIMESLOT),
    }


def _default_schedule_config() -> dict[str, dict[str, dict[str, str]]]:
    return {
        "day_configs": {
            str(i): _default_day_config()
            for i in range(7)
        }
    }


def _default_company_submissions() -> list[dict[str, str]]:
    return []


def _parse_int(value: str, fallback: int) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return fallback


def _normalize_day_config(raw: dict[str, str]) -> dict[str, str]:
    active_raw = str(raw.get("active", "1")).strip().lower()
    active = "1" if active_raw in {"1", "true", "yes", "y"} else "0"
    start_hour = _parse_int(raw.get("start_hour", START_HOUR), START_HOUR)
    end_hour = _parse_int(raw.get("end_hour", END_HOUR), END_HOUR)
    slot_duration_minutes = _parse_int(raw.get("slot_duration_minutes", SLOT_DURATION_MINUTES), SLOT_DURATION_MINUTES)
    max_students = _parse_int(raw.get("max_students_per_timeslot", MAX_STUDENTS_PER_TIMESLOT), MAX_STUDENTS_PER_TIMESLOT)

    start_hour = min(max(start_hour, 0), 23)
    end_hour = min(max(end_hour, start_hour + 1), 24)
    slot_duration_minutes = min(max(slot_duration_minutes, 5), 240)
    max_students = min(max(max_students, 1), 50)

    return {
        "active": active,
        "start_hour": str(start_hour),
        "end_hour": str(end_hour),
        "slot_duration_minutes": str(slot_duration_minutes),
        "max_students_per_timeslot": str(max_students),
    }


def _normalize_schedule_config(raw: dict) -> dict[str, dict[str, dict[str, str]]]:
    normalized = _default_schedule_config()
    raw_day_configs = raw.get("day_configs", {}) if isinstance(raw, dict) else {}
    for i in range(7):
        incoming = raw_day_configs.get(str(i), {})
        normalized["day_configs"][str(i)] = _normalize_day_config(incoming)
    return normalized


def _day_config_for_weekday(schedule_config: dict[str, dict[str, dict[str, str]]], weekday: int) -> dict[str, str]:
    normalized = _normalize_schedule_config(schedule_config)
    return normalized["day_configs"][str(weekday)]


def _day_values(schedule_config: dict[str, dict[str, dict[str, str]]], weekday: int) -> tuple[bool, int, int, int, int]:
    day_config = _day_config_for_weekday(schedule_config, weekday)
    active = day_config["active"] == "1"
    start_hour = int(day_config["start_hour"])
    end_hour = int(day_config["end_hour"])
    slot_duration_minutes = int(day_config["slot_duration_minutes"])
    max_students = int(day_config["max_students_per_timeslot"])
    return active, start_hour, end_hour, slot_duration_minutes, max_students


def _next_date_for_weekday(base_date: date, target_weekday: int) -> date:
    delta_days = (target_weekday - base_date.weekday()) % 7
    return base_date + timedelta(days=delta_days)


def _ensure_xml_exists(xml_path: str) -> None:
    if os.path.exists(xml_path):
        return

    root = ET.Element("bookings")
    tree = ET.ElementTree(root)
    try:
        ET.indent(tree, space="  ")
    except AttributeError:
        pass
    tree.write(xml_path, encoding="utf-8", xml_declaration=True)


def _load_bookings(xml_path: str) -> list[dict[str, str]]:
    _ensure_xml_exists(xml_path)
    root = ET.parse(xml_path).getroot()
    bookings: list[dict[str, str]] = []
    for booking in root.findall("booking"):
        bookings.append(
            {
                "pupil_name": booking.get("pupil_name", "").strip(),
                "slot_date": booking.get("slot_date", "").strip(),
                "start_time": booking.get("start_time", "").strip(),
                "end_time": booking.get("end_time", "").strip(),
                "slot_index": booking.get("slot_index", "").strip(),
                "created_at_utc": booking.get("created_at_utc", "").strip(),
            }
        )
    return bookings


def _load_pool(xml_path: str) -> list[dict[str, str]]:
    _ensure_xml_exists(xml_path)
    root = ET.parse(xml_path).getroot()
    pool: list[dict[str, str]] = []
    for pupil in root.findall("pool_pupil"):
        pool.append(
            {
                "pupil_name": pupil.get("pupil_name", "").strip(),
                "slot_date": pupil.get("slot_date", "").strip(),
                "created_at_utc": pupil.get("created_at_utc", "").strip(),
            }
        )
    return pool


def _load_schedule_config(xml_path: str) -> dict[str, dict[str, dict[str, str]]]:
    _ensure_xml_exists(xml_path)
    root = ET.parse(xml_path).getroot()
    schedule_node = root.find("schedule_config")
    if schedule_node is None:
        return _default_schedule_config()

    day_nodes = schedule_node.findall("day_schedule")
    if day_nodes:
        day_configs: dict[str, dict[str, str]] = {}
        for node in day_nodes:
            weekday_raw = str(node.get("weekday", "")).strip()
            if not weekday_raw.isdigit():
                continue
            weekday_int = int(weekday_raw)
            if weekday_int < 0 or weekday_int > 6:
                continue
            day_configs[str(weekday_int)] = {
                "active": node.get("active", "1"),
                "start_hour": node.get("start_hour", str(START_HOUR)),
                "end_hour": node.get("end_hour", str(END_HOUR)),
                "slot_duration_minutes": node.get("slot_duration_minutes", str(SLOT_DURATION_MINUTES)),
                "max_students_per_timeslot": node.get("max_students_per_timeslot", str(MAX_STUDENTS_PER_TIMESLOT)),
            }
        return _normalize_schedule_config({"day_configs": day_configs})

    # Backward-compatibility for older XML format with global attributes.
    active_days_raw = str(schedule_node.get("active_days", "0,1,2,3,4,5,6"))
    active_days = {
        int(x.strip())
        for x in active_days_raw.split(",")
        if x.strip().isdigit() and 0 <= int(x.strip()) <= 6
    }
    if not active_days:
        active_days = {0, 1, 2, 3, 4, 5, 6}

    start_hour = schedule_node.get("start_hour", str(START_HOUR))
    end_hour = schedule_node.get("end_hour", str(END_HOUR))
    slot_duration_minutes = schedule_node.get("slot_duration_minutes", str(SLOT_DURATION_MINUTES))
    max_students = schedule_node.get("max_students_per_timeslot", str(MAX_STUDENTS_PER_TIMESLOT))

    day_configs = {}
    for i in range(7):
        day_configs[str(i)] = {
            "active": "1" if i in active_days else "0",
            "start_hour": start_hour,
            "end_hour": end_hour,
            "slot_duration_minutes": slot_duration_minutes,
            "max_students_per_timeslot": max_students,
        }
    return _normalize_schedule_config({"day_configs": day_configs})


def _company_submission_from_node(node: ET.Element) -> dict[str, str]:
    return {
        "company_name": node.get("company_name", "").strip(),
        "email_id": node.get("email_id", "").strip(),
        "password": node.get("password", ""),
        "status": node.get("status", "").strip(),
        "submitted_at_utc": node.get("submitted_at_utc", "").strip(),
    }


def _load_company_submissions(xml_path: str) -> list[dict[str, str]]:
    _ensure_xml_exists(xml_path)
    root = ET.parse(xml_path).getroot()
    submissions_node = root.find("company_submissions")
    if submissions_node is not None:
        return [
            _company_submission_from_node(submission)
            for submission in submissions_node.findall("submission")
        ]
    company_node = root.find("company_setup")
    if company_node is not None:
        return [_company_submission_from_node(company_node)]
    return _default_company_submissions()


def _save_data(
    xml_path: str,
    bookings: list[dict[str, str]],
    pool: list[dict[str, str]],
    schedule_config: dict[str, dict[str, dict[str, str]]],
    company_submissions: list[dict[str, str]],
) -> None:
    root = ET.Element("bookings")
    normalized_config = _normalize_schedule_config(schedule_config)
    schedule_node = ET.SubElement(root, "schedule_config")
    for i in range(7):
        day_config = normalized_config["day_configs"][str(i)]
        ET.SubElement(
            schedule_node,
            "day_schedule",
            attrib={
                "weekday": str(i),
                "active": day_config["active"],
                "start_hour": day_config["start_hour"],
                "end_hour": day_config["end_hour"],
                "slot_duration_minutes": day_config["slot_duration_minutes"],
                "max_students_per_timeslot": day_config["max_students_per_timeslot"],
            },
        )

    for row in bookings:
        ET.SubElement(
            root,
            "booking",
            attrib={
                "pupil_name": row["pupil_name"],
                "slot_date": row["slot_date"],
                "start_time": row["start_time"],
                "end_time": row["end_time"],
                "slot_index": str(row.get("slot_index", "")),
                "created_at_utc": row["created_at_utc"],
            },
        )

    for row in pool:
        ET.SubElement(
            root,
            "pool_pupil",
            attrib={
                "pupil_name": row["pupil_name"],
                "slot_date": row["slot_date"],
                "created_at_utc": row["created_at_utc"],
            },
        )

    submissions_node = ET.SubElement(root, "company_submissions")
    for submission in company_submissions:
        ET.SubElement(
            submissions_node,
            "submission",
            attrib={
                "company_name": submission.get("company_name", "").strip(),
                "email_id": submission.get("email_id", "").strip(),
                "password": submission.get("password", ""),
                "status": submission.get("status", "").strip(),
                "submitted_at_utc": submission.get("submitted_at_utc", "").strip(),
            },
        )

    if company_submissions:
        latest = company_submissions[-1]
        ET.SubElement(
            root,
            "company_setup",
            attrib={
                "company_name": latest.get("company_name", "").strip(),
                "email_id": latest.get("email_id", "").strip(),
                "password": latest.get("password", ""),
                "status": latest.get("status", "").strip(),
                "submitted_at_utc": latest.get("submitted_at_utc", "").strip(),
            },
        )

    tree = ET.ElementTree(root)
    try:
        ET.indent(tree, space="  ")
    except AttributeError:
        pass
    tree.write(xml_path, encoding="utf-8", xml_declaration=True)


def _generate_daily_slots(
    target_date: date,
    schedule_config: dict[str, dict[str, dict[str, str]]],
) -> list[tuple[str, str]]:
    active, start_hour, end_hour, slot_duration_minutes, _ = _day_values(schedule_config, target_date.weekday())
    if not active:
        return []
    slots: list[tuple[str, str]] = []
    start_dt = datetime.combine(target_date, time(hour=start_hour))
    end_dt = datetime.combine(target_date, time(hour=end_hour))

    current = start_dt
    while current < end_dt:
        slot_end = current + timedelta(minutes=slot_duration_minutes)
        if slot_end > end_dt:
            break
        slots.append((current.strftime("%H:%M"), slot_end.strftime("%H:%M")))
        current = slot_end
    return slots


def _is_valid_email(email_value: str) -> bool:
    email = email_value.strip()
    if "@" not in email:
        return False
    local_part, domain = email.split("@", 1)
    if not local_part or not domain:
        return False
    return "." in domain


def _parse_iso_datetime(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def _evaluate_trial_access(company_submissions: list[dict[str, str]]) -> tuple[str, int | None]:
    latest = company_submissions[-1] if company_submissions else None
    if not latest or latest.get("status") == "approved":
        return "approved", None
    submitted_at = _parse_iso_datetime(latest.get("submitted_at_utc", ""))
    if submitted_at is None:
        return "expired", 0
    expiry = submitted_at + timedelta(days=30)
    remaining = expiry - datetime.utcnow()
    if remaining.total_seconds() <= 0:
        return "expired", 0
    days_left = remaining.days + (1 if remaining.seconds > 0 else 0)
    return "trial", days_left


def _students_by_slot(
    target_date: date,
    bookings: list[dict[str, str]],
    max_students_per_timeslot: int,
) -> dict[str, list[dict[str, str]]]:
    date_key = target_date.isoformat()
    students: dict[str, list[dict[str, str]]] = {}
    for row in bookings:
        if row["slot_date"] != date_key:
            continue
        students.setdefault(row["start_time"], []).append(row)

    for start_time, values in students.items():
        values.sort(key=lambda x: int(x.get("slot_index") or "999"))
        normalized: list[dict[str, str]] = []
        used: set[int] = set()
        for row in values:
            raw_index = str(row.get("slot_index", "")).strip()
            if (
                raw_index.isdigit()
                and 1 <= int(raw_index) <= max_students_per_timeslot
                and int(raw_index) not in used
            ):
                idx = int(raw_index)
            else:
                free = next((i for i in range(1, max_students_per_timeslot + 1) if i not in used), None)
                if free is None:
                    continue
                idx = free
            row["slot_index"] = str(idx)
            used.add(idx)
            normalized.append(row)
        students[start_time] = normalized

    return students


def _build_overview_rows(
    target_date: date,
    bookings: list[dict[str, str]],
    schedule_config: dict[str, dict[str, dict[str, str]]],
) -> list[dict[str, str]]:
    _, _, _, _, max_students_per_timeslot = _day_values(schedule_config, target_date.weekday())
    students_map = _students_by_slot(target_date, bookings, max_students_per_timeslot)
    date_key = target_date.isoformat()

    rows: list[dict[str, str]] = []
    for start_label, end_label in _generate_daily_slots(target_date, schedule_config):
        slot_students = students_map.get(start_label, [])
        status = "Booked" if slot_students else "Available"
        rows.append(
            {
                "Date": date_key,
                "Start Time": start_label,
                "End Time": end_label,
                "Status": status,
                "Filled": f"{len(slot_students)}/{max_students_per_timeslot}",
            }
        )
    return rows


def _build_time_grid_df(
    target_date: date,
    bookings: list[dict[str, str]],
    schedule_config: dict[str, dict[str, dict[str, str]]],
) -> pd.DataFrame:
    _, _, _, _, max_students_per_timeslot = _day_values(schedule_config, target_date.weekday())
    students_map = _students_by_slot(target_date, bookings, max_students_per_timeslot)
    time_labels = [start for start, _ in _generate_daily_slots(target_date, schedule_config)]

    grid_rows: list[dict[str, str]] = []
    for slot_index in range(1, max_students_per_timeslot + 1):
        row: dict[str, str] = {"Student Slot": f"Slot {slot_index}"}
        for time_label in time_labels:
            entries = students_map.get(time_label, [])
            match = next((x for x in entries if str(x.get("slot_index", "")) == str(slot_index)), None)
            row[time_label] = match["pupil_name"] if match else "-"
        grid_rows.append(row)
    return pd.DataFrame(grid_rows)


def _book_slot(
    bookings: list[dict[str, str]],
    pupil_name: str,
    slot_date: date,
    start_time_label: str,
    schedule_config: dict[str, dict[str, dict[str, str]]],
) -> tuple[bool, str]:
    pupil_name = pupil_name.strip()
    if not pupil_name:
        return False, "Please enter pupil name."

    active, _, _, _, max_students_per_timeslot = _day_values(schedule_config, slot_date.weekday())
    if not active:
        return False, "No class schedule configured for this day."
    slot_rows = _generate_daily_slots(slot_date, schedule_config)
    slot_map = {start: end for start, end in slot_rows}
    if start_time_label not in slot_map:
        return False, "Invalid slot selected."

    date_key = slot_date.isoformat()
    same_slot = [
        row
        for row in bookings
        if row["slot_date"] == date_key and row["start_time"] == start_time_label
    ]

    for row in same_slot:
        if row["pupil_name"].casefold() == pupil_name.casefold():
            return False, "This pupil is already assigned to this timeslot."

    used_indexes = {
        int(str(row.get("slot_index", "0")))
        for row in same_slot
        if str(row.get("slot_index", "")).isdigit()
    }
    free_index = next((i for i in range(1, max_students_per_timeslot + 1) if i not in used_indexes), None)
    if free_index is None:
        return False, f"This timeslot is full ({max_students_per_timeslot}/{max_students_per_timeslot})."

    bookings.append(
        {
            "pupil_name": pupil_name,
            "slot_date": date_key,
            "start_time": start_time_label,
            "end_time": slot_map[start_time_label],
            "slot_index": str(free_index),
            "created_at_utc": datetime.utcnow().isoformat(timespec="seconds"),
        }
    )
    return True, f"Pupil added to {start_time_label} in Slot {free_index}."


def _remove_booking(
    bookings: list[dict[str, str]],
    slot_date: date,
    start_time_label: str,
    slot_index: int,
) -> tuple[bool, str]:
    date_key = slot_date.isoformat()
    for index, row in enumerate(bookings):
        if (
            row["slot_date"] == date_key
            and row["start_time"] == start_time_label
            and str(row.get("slot_index", "")) == str(slot_index)
        ):
            removed_name = row["pupil_name"]
            bookings.pop(index)
            return True, f"Removed {removed_name} from {start_time_label} Slot {slot_index}."
    return False, "No booking found for the selected timeslot slot number."


def _add_pupil_to_pool(
    pool: list[dict[str, str]],
    bookings: list[dict[str, str]],
    pupil_name: str,
    slot_date: date,
) -> tuple[bool, str]:
    pupil_name = pupil_name.strip()
    if not pupil_name:
        return False, "Please enter pupil name."

    date_key = slot_date.isoformat()
    if any(
        row["slot_date"] == date_key and row["pupil_name"].casefold() == pupil_name.casefold()
        for row in pool
    ):
        return False, "This pupil is already in the left-panel list."

    if any(
        row["slot_date"] == date_key and row["pupil_name"].casefold() == pupil_name.casefold()
        for row in bookings
    ):
        return False, "This pupil is already allocated for this day."

    pool.append(
        {
            "pupil_name": pupil_name,
            "slot_date": date_key,
            "created_at_utc": datetime.utcnow().isoformat(timespec="seconds"),
        }
    )
    return True, "Pupil added to left-panel list."


def _remove_pupil_from_pool(
    pool: list[dict[str, str]],
    slot_date: date,
    pupil_name: str,
) -> tuple[bool, str]:
    date_key = slot_date.isoformat()
    for index, row in enumerate(pool):
        if row["slot_date"] == date_key and row["pupil_name"].casefold() == pupil_name.casefold():
            pool.pop(index)
            return True, f"Removed {pupil_name} from left-panel list."
    return False, "Pupil not found in left-panel list."


def _apply_drag_layout(
    bookings: list[dict[str, str]],
    pool: list[dict[str, str]],
    slot_date: date,
    containers: list[dict[str, list[str]]],
    time_options: list[str],
    schedule_config: dict[str, dict[str, dict[str, str]]],
) -> tuple[bool, str]:
    container_map: dict[str, list[str]] = {
        str(c.get("header", "")).strip(): [str(x).strip() for x in c.get("items", []) if str(x).strip()]
        for c in containers
    }

    unallocated = container_map.get("Added pupils for this day:", [])
    deleted = container_map.get("Delete", [])
    active, _, _, _, max_students_per_timeslot = _day_values(schedule_config, slot_date.weekday())
    if not active:
        return False, "No class schedule configured for this day."
    slot_map = {start: end for start, end in _generate_daily_slots(slot_date, schedule_config)}

    seen: set[str] = set()
    for label in ["Added pupils for this day:", "Delete", *time_options]:
        for name in container_map.get(label, []):
            folded = name.casefold()
            if folded in seen:
                return False, f"Duplicate pupil found in drag board: {name}."
            seen.add(folded)

    for label in time_options:
        if len(container_map.get(label, [])) > max_students_per_timeslot:
            return False, f"{label} has more than {max_students_per_timeslot} pupils."

    date_key = slot_date.isoformat()
    preserved_bookings = [row for row in bookings if row["slot_date"] != date_key]
    preserved_pool = [row for row in pool if row["slot_date"] != date_key]

    now_utc = datetime.utcnow().isoformat(timespec="seconds")
    rebuilt_bookings: list[dict[str, str]] = []
    for time_label in time_options:
        for idx, pupil_name in enumerate(container_map.get(time_label, []), start=1):
            rebuilt_bookings.append(
                {
                    "pupil_name": pupil_name,
                    "slot_date": date_key,
                    "start_time": time_label,
                    "end_time": slot_map[time_label],
                    "slot_index": str(idx),
                    "created_at_utc": now_utc,
                }
            )

    rebuilt_pool: list[dict[str, str]] = []
    for pupil_name in unallocated:
        rebuilt_pool.append(
            {
                "pupil_name": pupil_name,
                "slot_date": date_key,
                "created_at_utc": now_utc,
            }
        )

    # Pupils dropped in "Delete" are intentionally removed from this day.
    _ = deleted
    bookings[:] = preserved_bookings + rebuilt_bookings
    pool[:] = preserved_pool + rebuilt_pool
    return True, "Drag-and-drop changes saved."


st.set_page_config(
    page_title="Daily Slot Dashboard",
    page_icon=os.path.join(BASE_DIR, "assets", "favicon-bc.svg"),
    layout="wide",
)

# Add branding header at the very top
st.markdown("""
    <div style="background: linear-gradient(90deg, #003D82 0%, #0056B3 100%); padding: 20px 30px; border-radius: 10px; margin-bottom: 20px; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
        <div style="display: flex; justify-content: space-between; align-items: center;">
            <h1 style="color: white; margin: 0; font-size: 28px; font-weight: bold;">AI Powered Slot Dashboard</h1>
            <div style="color: #FF6B6B; font-size: 16px; font-weight: bold;">By BrainCal Tech Team <a href="https://braincal.com" target="_blank" style="color: #FF6B6B; text-decoration: none;">https://braincal.com</a></div>
        </div>
    </div>
""", unsafe_allow_html=True)

# Keep sidebar buttons aligned left
st.sidebar.markdown("""
    <style>
    [data-testid="stSidebar"] .stButton > button {
        background: rgba(22, 31, 54, 0.85);
        color: white;
        border: 1px solid rgba(99, 242, 200, 0.2);
        border-radius: 12px;
        font-weight: 600;
        justify-content: flex-start !important;
        text-align: left !important;
        padding-left: 0.9rem !important;
    }
    [data-testid="stSidebar"] .stButton > button > div {
        justify-content: flex-start !important;
    }
    [data-testid="stSidebar"] .stButton > button:hover {
        border-color: rgba(99, 242, 200, 0.6);
        box-shadow: 0 8px 18px rgba(6, 12, 26, 0.2);
    }
    [data-testid="stStatusWidget"],
    [data-testid="stDecoration"],
    #MainMenu,
    footer {
        visibility: visible !important;
        opacity: 1 !important;
        height: auto !important;
        pointer-events: auto !important;
    }
    </style>
""", unsafe_allow_html=True)

if st.sidebar.button("📊 Slot Overview", use_container_width=True, key="menu_overview"):
    st.session_state.menu_choice = "Slot Overview"

if st.sidebar.button("⚙️ Slot Management", use_container_width=True, key="menu_management"):
    st.session_state.menu_choice = "Slot Management"

if st.sidebar.button("📈 Slot Dashboard", use_container_width=True, key="menu_dashboard"):
    st.session_state.menu_choice = "Slot Dashboard"

if st.sidebar.button("🏢 Company Management", use_container_width=True, key="menu_company"):
    st.session_state.menu_choice = "Company Management"

if st.sidebar.button("⚡ Settings", use_container_width=True, key="menu_settings"):
    st.session_state.menu_choice = "Settings"

st.sidebar.markdown("---")

# Initialize session state for menu
if "menu_choice" not in st.session_state:
    st.session_state.menu_choice = "Slot Dashboard"
if "super_user_authenticated" not in st.session_state:
    st.session_state.super_user_authenticated = False

menu_choice = st.session_state.menu_choice

bookings_data = _load_bookings(XML_PATH)
pool_data = _load_pool(XML_PATH)
schedule_config = _load_schedule_config(XML_PATH)
company_submissions = _load_company_submissions(XML_PATH)

access_state, trial_days_left = _evaluate_trial_access(company_submissions)
if access_state == "expired":
    st.error("Please contact the administrator")
    st.stop()
elif access_state == "trial" and menu_choice != "Slot Dashboard":
    st.warning(f"Approval is pending; trial access expires in {trial_days_left} day(s).")

st.caption(
    "This planner works by weekday (day), not calendar date."
)

# Check menu selection and display appropriate content
if menu_choice == "Slot Overview":
    selected_working_day_label = st.selectbox(
        "Select Working Day",
        options=WEEKDAY_LABELS,
        key="overview_working_day_select",
    )
    selected_working_day_index = WEEKDAY_LABELS.index(selected_working_day_label)
    selected_date = WEEKDAY_ANCHOR_DATES[selected_working_day_index]
    overview_df = pd.DataFrame(_build_overview_rows(selected_date, bookings_data, schedule_config))
    st.subheader("Timeslot Overview")
    st.dataframe(overview_df, use_container_width=True, hide_index=True)
    st.stop()
elif menu_choice == "Slot Management":
    st.subheader("⚙️ Slot Management")
    st.subheader("Schedule Setup")
    selected_schedule_day_label = st.selectbox("Select Day", options=WEEKDAY_LABELS, key="schedule_day_select")
    selected_schedule_day_index = WEEKDAY_LABELS.index(selected_schedule_day_label)
    selected_day_config = _day_config_for_weekday(schedule_config, selected_schedule_day_index)

    with st.form("schedule_form"):
        days_to_apply = st.multiselect(
            "Days To Apply",
            options=WEEKDAY_LABELS,
            default=[selected_schedule_day_label],
        )
        class_runs_on_day = st.checkbox(
            "Class Runs On Selected Days",
            value=selected_day_config["active"] == "1",
        )
        start_hour_input = st.number_input(
            "Start Hour",
            min_value=0,
            max_value=23,
            value=int(selected_day_config["start_hour"]),
            step=1,
        )
        end_hour_input = st.number_input(
            "End Hour",
            min_value=1,
            max_value=24,
            value=int(selected_day_config["end_hour"]),
            step=1,
        )
        slot_duration_input = st.number_input(
            "Slot Duration (Minutes)",
            min_value=5,
            max_value=240,
            value=int(selected_day_config["slot_duration_minutes"]),
            step=5,
        )
        capacity_input = st.number_input(
            "Max Students Per Timeslot",
            min_value=1,
            max_value=50,
            value=int(selected_day_config["max_students_per_timeslot"]),
            step=1,
        )
        save_schedule_clicked = st.form_submit_button("Save Slots For Selected Days")

    if save_schedule_clicked:
        if not days_to_apply:
            st.error("Select at least one day in Days To Apply.")
        elif int(end_hour_input) <= int(start_hour_input):
            st.error("End Hour must be greater than Start Hour.")
        elif ((int(end_hour_input) - int(start_hour_input)) * 60) % int(slot_duration_input) != 0:
            st.error("Slot duration must divide the daily time window exactly.")
        else:
            day_config_payload = _normalize_day_config(
                {
                    "active": "1" if class_runs_on_day else "0",
                    "start_hour": str(int(start_hour_input)),
                    "end_hour": str(int(end_hour_input)),
                    "slot_duration_minutes": str(int(slot_duration_input)),
                    "max_students_per_timeslot": str(int(capacity_input)),
                }
            )
            for day_label in days_to_apply:
                day_index = WEEKDAY_LABELS.index(day_label)
                schedule_config["day_configs"][str(day_index)] = day_config_payload
            schedule_config = _normalize_schedule_config(schedule_config)
            _save_data(XML_PATH, bookings_data, pool_data, schedule_config, company_submissions)
            st.success(f"Saved slots for {', '.join(days_to_apply)}.")
            st.rerun()
    st.stop()
elif menu_choice == "Company Management":
    st.subheader("🏢 Company Management")

    latest_submission = company_submissions[-1] if company_submissions else None

    with st.form("company_setup_form"):
        company_name_input = st.text_input(
            "Company Name",
            value=latest_submission.get("company_name", "") if latest_submission else "",
        )
        email_input = st.text_input(
            "Email ID",
            value=latest_submission.get("email_id", "") if latest_submission else "",
        )
        password_input = st.text_input("Password", type="password")
        confirm_password_input = st.text_input("Confirm Password", type="password")
        send_for_approval_clicked = st.form_submit_button("Send for Approval")

    if send_for_approval_clicked:
        company_name = company_name_input.strip()
        email_id = email_input.strip()
        if not company_name:
            st.error("Company Name is required.")
        elif not email_id:
            st.error("Email ID is required.")
        elif not _is_valid_email(email_id):
            st.error("Please enter a valid Email ID.")
        elif not password_input:
            st.error("Password is required.")
        elif password_input != confirm_password_input:
            st.error("Password and Confirm Password must match.")
        else:
            duplicate = any(
                submission["company_name"].casefold() == company_name.casefold()
                and submission["email_id"].casefold() == email_id.casefold()
                for submission in company_submissions
            )
            if duplicate:
                st.error("A submission with this company name and email already exists.")
            else:
                new_submission = {
                    "company_name": company_name,
                    "email_id": email_id,
                    "password": password_input,
                    "status": "pending_approval",
                    "submitted_at_utc": datetime.utcnow().isoformat(timespec="seconds"),
                }
                company_submissions.append(new_submission)
                _save_data(XML_PATH, bookings_data, pool_data, schedule_config, company_submissions)
                st.success("Company details sent for approval and saved.")
                st.rerun()

    if latest_submission:
        st.caption(
            f"Latest submission: {latest_submission.get('company_name')} "
            f"({latest_submission.get('email_id')}) | Status: {latest_submission.get('status', 'N/A')}"
        )
    st.stop()
elif menu_choice == "Settings":
    if not st.session_state.super_user_authenticated:
        st.warning("Super User authentication is required to access Settings.")
        with st.form("super_user_form"):
            st.write("Enter the Super User password to continue into Settings.")
            super_user_password = st.text_input("Super User Password", type="password")
            unlock_clicked = st.form_submit_button("Unlock Settings")
            if unlock_clicked:
                if super_user_password == CONFIG["SUPER_USER"]:
                    st.session_state.super_user_authenticated = True
                    st.success("Settings unlocked.")
                    st.info("Reopen the Settings menu to refresh the view.")
                else:
                    st.error("Invalid super user password.")
        if not st.session_state.super_user_authenticated:
            st.stop()
    st.subheader("⚙️ Settings")
    st.caption("Review company submissions and toggle approval to move them forward.")
    if access_state == "trial":
        st.caption("Unapproved submissions expire 30 days after the submitted timestamp; approval keeps access open beyond that.")
    if not company_submissions:
        st.info("No submissions yet. Send a company for approval using the Company Management tab.")
    else:
        approval_checks: list[bool] = []
        with st.form("settings_approval_form"):
            header_cols = st.columns([3, 3, 2, 2, 2])
            header_cols[0].markdown("**Company Name**")
            header_cols[1].markdown("**Email ID**")
            header_cols[2].markdown("**Status**")
            header_cols[3].markdown("**Submitted At (UTC)**")
            header_cols[4].markdown("**Approve**")

            for idx, submission in enumerate(company_submissions):
                row_cols = st.columns([3, 3, 2, 2, 2])
                row_cols[0].write(submission.get("company_name") or "-")
                row_cols[1].write(submission.get("email_id") or "-")
                row_cols[2].write(submission.get("status") or "pending_approval")
                submitted_at = submission.get("submitted_at_utc") or "N/A"
                row_cols[3].write(submitted_at)

                raw_key = f"settings_approve_{idx}_{submission.get('company_name','')}_{submission.get('email_id','')}"
                checkbox_key = "".join(ch if ch.isalnum() else "_" for ch in raw_key)
                approval_checks.append(
                    row_cols[4].checkbox(
                        "",
                        value=submission.get("status") == "approved",
                        key=checkbox_key,
                    )
                )

            approval_submit = st.form_submit_button("Save Approval Statuses")

        if approval_submit:
            updated = False
            for idx, submission in enumerate(company_submissions):
                desired_status = "approved" if approval_checks[idx] else "pending_approval"
                if submission.get("status") != desired_status:
                    submission["status"] = desired_status
                    updated = True
            if updated:
                _save_data(XML_PATH, bookings_data, pool_data, schedule_config, company_submissions)
                st.success("Approval statuses updated.")
                st.rerun()
            else:
                st.info("No approval status changes detected.")
    st.stop()

# Default: Show Slot Dashboard
dashboard_title_col, dashboard_status_col = st.columns([2, 3])
with dashboard_title_col:
    st.subheader("📈 Slot Dashboard")
with dashboard_status_col:
    if access_state == "trial":
        st.markdown(
            f"""
            <div style="margin-top: 0.35rem; padding: 0.55rem 0.85rem; border-radius: 10px; background: #fff4e5; color: #8a4b08; border: 1px solid #f2c078; font-size: 0.95rem;">
                Approval is pending; trial access expires in {trial_days_left} day(s).
            </div>
            """,
            unsafe_allow_html=True,
        )

selected_working_day_label = st.sidebar.selectbox("Select Working Day", options=WEEKDAY_LABELS, key="working_day_select")
selected_working_day_index = WEEKDAY_LABELS.index(selected_working_day_label)
selected_date = WEEKDAY_ANCHOR_DATES[selected_working_day_index]
class_runs_today, _, _, _, max_students_per_timeslot = _day_values(schedule_config, selected_date.weekday())
time_options = [start for start, _ in _generate_daily_slots(selected_date, schedule_config)]

if not class_runs_today:
    weekday_name = WEEKDAY_LABELS[selected_date.weekday()]
    st.warning(f"No class schedule configured for {weekday_name}. Update Slot Management to enable this day.")

st.sidebar.subheader("Pupil List (Left Panel)")
with st.sidebar.form("pool_form", clear_on_submit=True):
    pool_name_input = st.text_input("Pupil Name")
    add_to_pool_clicked = st.form_submit_button("Add To List")

if add_to_pool_clicked:
    ok, msg = _add_pupil_to_pool(pool_data, bookings_data, pool_name_input, selected_date)
    if ok:
        _save_data(XML_PATH, bookings_data, pool_data, schedule_config, company_submissions)
        st.sidebar.success(msg)
        st.rerun()
    else:
        st.sidebar.error(msg)

daily_pool = [row for row in pool_data if row["slot_date"] == selected_date.isoformat()]

overview_df = pd.DataFrame(_build_overview_rows(selected_date, bookings_data, schedule_config))
grid_df = _build_time_grid_df(selected_date, bookings_data, schedule_config)
students_map = _students_by_slot(selected_date, bookings_data, max_students_per_timeslot)
all_daily_bookings = sum(len(v) for v in students_map.values())

metrics_col1, metrics_col2, metrics_col3 = st.columns(3)
with metrics_col1:
    st.metric("Total Timeslots", len(overview_df))
with metrics_col2:
    st.metric("Total Capacity", len(overview_df) * max_students_per_timeslot)
with metrics_col3:
    st.metric("Booked Students", all_daily_bookings)

if daily_pool:
    pupils_list = ", ".join([x["pupil_name"] for x in daily_pool])
    st.write(f"**{pupils_list}**")
else:
    st.info("No pupils added yet.")

st.caption("Drag pupils from above and drop into time slots. Drag to `Delete` to remove.")
if class_runs_today and time_options:
    containers = [{"header": "Added pupils for this day:", "items": [x["pupil_name"] for x in daily_pool]}]
    for time_label in time_options:
        slot_students = students_map.get(time_label, [])
        ordered_names = [
            row["pupil_name"]
            for row in sorted(slot_students, key=lambda x: int(str(x.get("slot_index", "999"))))
        ]
        containers.append({"header": time_label, "items": ordered_names})
    containers.append({"header": "Delete", "items": []})

    drag_result = sort_items(
        containers,
        multi_containers=True,
        direction="vertical",
        key=f"drag_board_{selected_date.isoformat()}_{'_'.join(time_options)}_{max_students_per_timeslot}",
    )

    if drag_result != containers:
        ok, msg = _apply_drag_layout(
            bookings_data,
            pool_data,
            selected_date,
            drag_result,
            time_options,
            schedule_config,
        )
        if ok:
            _save_data(XML_PATH, bookings_data, pool_data, schedule_config, company_submissions)
            st.success(msg)
            st.rerun()
        else:
            st.error(msg)
else:
    st.info("No active slots for this date based on the saved schedule.")

st.subheader("Detailed Slot View")

# Style the dataframe to highlight occupied slots with parrot green
def style_occupied_slots(val):
    if val == "-":
        return ""
    else:
        return "background-color: #00A651; color: white; font-weight: bold;"

styled_grid = grid_df.style.applymap(style_occupied_slots)
st.dataframe(styled_grid, use_container_width=True, hide_index=True)

st.caption(f"XML storage file: {XML_PATH}")
