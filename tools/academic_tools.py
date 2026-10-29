"""Read-only course lookup and counting tools for the academic agents.

Course rows are loaded lazily and cached for this Python process.  The tools
read the source files under ``data/`` and return their source location so an
agent can cite the evidence it used.
"""

from __future__ import annotations

import csv
import re
from functools import lru_cache
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"

_COURSE_CODE_RE = re.compile(r"\b([A-Za-z]{2,8})\s*-?\s*(\d{3,5}|[xX]{3,5})\b")
_MARKDOWN_COURSE_RE = re.compile(
    r"^\s*\d+[.)]\s+\*\*"
    r"(?P<code>[A-Za-z]{2,8}\s*-?\s*\d{3,5})\s*[—–-]\s*"
    r"(?P<title>[^*|]+?)\*\*"
)
_QUERY_STOPWORDS = {
    "a", "an", "and", "are", "available", "course", "courses", "does",
    "find", "for", "have", "how", "in", "is", "lookup", "many", "of",
    "offered", "offering", "on", "semester", "slot", "slots", "the",
    "this", "what", "which",
}


def _normalize_text(value: str) -> str:
    return "".join(re.findall(r"[a-z0-9]+", value.casefold()))


def _normalize_code(value: str) -> str:
    return "".join(re.findall(r"[a-z0-9]+", value.casefold())).upper()


def _normalize_department(value: str | None) -> str | None:
    if not value or not value.strip():
        return None
    key = _normalize_text(value)
    for prefix in ("departmentof", "department", "deptof", "dept"):
        if key.startswith(prefix):
            key = key[len(prefix) :]
            break
    for suffix in ("department", "dept"):
        if key.endswith(suffix):
            key = key[: -len(suffix)]
            break
    aliases = {
        "hss": "humanities",
        "humanitiesandsocialsciences": "humanities",
        "humanitiessola": "humanities",
        "schoolofliberalarts": "humanities",
        "sola": "humanities",
        "computerscience": "cse",
        "computerscienceandengineering": "cse",
    }
    return aliases.get(key, key)


def _display_department(value: str | None) -> str | None:
    key = _normalize_department(value)
    if key == "humanities":
        return "Humanities / SoLA"
    if key == "cse":
        return "CSE"
    return value.strip() if value and value.strip() else None


def _normalize_semester(value: str | None) -> str | None:
    if not value:
        return None
    match = re.search(r"\b(?:semester|sem)?\s*(i{1,2}|[12])\b", value, re.IGNORECASE)
    if not match:
        return None
    token = match.group(1).casefold()
    return {"i": "1", "ii": "2"}.get(token, token)


def _infer_semester(value: str) -> str | None:
    match = re.search(
        r"(?<![a-z])sem(?:ester)?[\s_-]*(i{1,2}|[12])\b", value, re.IGNORECASE
    )
    if not match:
        return None
    token = match.group(1).casefold()
    return {"i": "1", "ii": "2"}.get(token, token)


def _infer_academic_year(value: str) -> str | None:
    match = re.search(r"\b(20\d{2})\s*[-–/]\s*(\d{2,4})\b", value)
    if not match:
        return None
    return f"{match.group(1)}-{match.group(2)[-2:]}"


def _infer_department(path: Path) -> str | None:
    path_text = " ".join(path.parts + (path.stem,))
    normalized = _normalize_text(path_text)
    if any(token in normalized for token in ("humanities", "sola", "liberalarts")):
        return "Humanities / SoLA"

    finalized = re.search(r"finalizedcourseslist(.+)", _normalize_text(path.stem))
    if finalized:
        code = finalized.group(1)
        return _display_department(code)
    return None


def _course_level(course_code: str) -> int | None:
    match = _COURSE_CODE_RE.search(course_code)
    if not match:
        return None
    digits = match.group(2)
    if not digits.isdigit() or len(digits) < 4:
        return None
    return int(digits[0]) * 100


def _header_kind(value: str) -> str | None:
    header = " ".join(re.findall(r"[a-z0-9]+", value.casefold()))
    compact = header.replace(" ", "")
    if header in {"course code", "subject code"} or compact in {
        "coursecode", "subjectcode",
    }:
        return "course_code"
    if header in {
        "course title", "course name", "subject name", "name of the course",
        "name of course", "title of course",
    }:
        return "course_name"
    if header in {"department", "offering department", "dept"}:
        return "department"
    if header in {"slot", "preferred slot", "preferred slots"}:
        return "slot"
    if header.startswith("instructor") or "faculty" in header or "coordinator" in header:
        return "instructor"
    if "credit" in header:
        return "credits"
    if "category" in header or header in {"course type", "type"}:
        return "category"
    if "semester" in header or header == "sem":
        return "semester"
    if "academic year" in header or header == "year":
        return "academic_year"
    return None


def _citation(source: str, row_number: int | None = None, line_number: int | None = None) -> str:
    if line_number is not None:
        return f"{source}, line {line_number}"
    if row_number is not None:
        return f"{source}, row {row_number}"
    return source


def _make_record(
    *,
    course_code: str,
    course_name: str,
    department: str | None,
    semester: str | None,
    academic_year: str | None,
    slot: str | None,
    instructor: str | None,
    credits: str | None,
    category: str | None,
    source: str,
    row_number: int | None = None,
    line_number: int | None = None,
    heading_level: int | None = None,
    heading_elective: bool = False,
) -> dict[str, Any]:
    level = _course_level(course_code) or heading_level
    category_text = category or ""
    category_tokens = set(re.findall(r"[a-z]+", category_text.casefold()))
    is_elective = (
        heading_elective
        or "elective" in category_text.casefold()
        or bool(category_tokens & {"oe", "pe"})
    )
    record: dict[str, Any] = {
        "course_code": course_code.strip(),
        "course_name": course_name.strip(),
        "department": _display_department(department),
        "semester": semester,
        "academic_year": academic_year,
        "level": level,
        "is_elective": is_elective,
        "category": category_text.strip() or None,
        "slot": slot.strip() if slot and slot.strip() else None,
        "instructor": instructor.strip() if instructor and instructor.strip() else None,
        "credits": credits.strip() if credits and credits.strip() else None,
        "source": source,
        "row_number": row_number,
        "line_number": line_number,
        "citation": _citation(source, row_number, line_number),
    }
    return record


def _csv_course_records(path: Path) -> list[dict[str, Any]]:
    try:
        with path.open("r", newline="", encoding="utf-8-sig") as csv_file:
            rows = list(csv.reader(csv_file))
    except (OSError, UnicodeError, csv.Error):
        return []

    header_index: int | None = None
    header_map: dict[int, str] = {}
    for candidate_index, row in enumerate(rows[:40]):
        candidate_map = {
            index: kind
            for index, cell in enumerate(row)
            if (kind := _header_kind(cell)) is not None
        }
        if "course_code" in candidate_map.values() and "course_name" in candidate_map.values():
            header_index = candidate_index
            header_map = candidate_map
            break
    if header_index is None:
        return []

    relative_source = path.relative_to(DATA_DIR).as_posix()
    file_context = f"{path.name} {' '.join(','.join(row) for row in rows[:3])}"
    default_semester = _infer_semester(file_context)
    default_year = _infer_academic_year(file_context)
    default_department = _infer_department(path)
    records: list[dict[str, Any]] = []

    for row_index, row in enumerate(rows[header_index + 1 :], start=header_index + 2):
        if not any(cell.strip() for cell in row):
            continue
        values: dict[str, str] = {}
        for column_index, kind in header_map.items():
            if column_index < len(row) and row[column_index].strip():
                values.setdefault(kind, row[column_index].strip())

        code = values.get("course_code", "").strip()
        name = values.get("course_name", "").strip()
        if not code and not name:
            continue
        if _header_kind(code) == "course_code" or _header_kind(name) == "course_name":
            continue

        semester = _normalize_semester(values.get("semester")) or default_semester
        year = _infer_academic_year(values.get("academic_year", "")) or default_year
        department = values.get("department") or default_department
        records.append(
            _make_record(
                course_code=code,
                course_name=name,
                department=department,
                semester=semester,
                academic_year=year,
                slot=values.get("slot"),
                instructor=values.get("instructor"),
                credits=values.get("credits"),
                category=values.get("category"),
                source=relative_source,
                row_number=row_index,
            )
        )
    return records


def _markdown_course_records(path: Path) -> list[dict[str, Any]]:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return []

    lines = text.splitlines()
    relative_source = path.relative_to(DATA_DIR).as_posix()
    file_context = f"{path.name} {text[:1000]}"
    semester = _infer_semester(file_context)
    year = _infer_academic_year(file_context)
    department = _infer_department(path) or (
        "Humanities / SoLA" if "humanit" in text.casefold() else None
    )
    heading_level: int | None = None
    heading_elective = False
    records: list[dict[str, Any]] = []

    for index, line in enumerate(lines):
        if line.lstrip().startswith("#"):
            level_match = re.search(r"(\d{3})\s*[- ]?level", line, re.IGNORECASE)
            heading_level = int(level_match.group(1)) if level_match else None
            heading_elective = "elective" in line.casefold()

        match = _MARKDOWN_COURSE_RE.match(line)
        if not match:
            continue

        details = [line]
        for following in lines[index + 1 :]:
            if re.match(r"^\s*\d+[.)]\s+\*\*", following) or following.lstrip().startswith("#"):
                break
            details.append(following)
        block = "\n".join(details)

        def field(pattern: str) -> str | None:
            found = re.search(pattern, block, re.IGNORECASE)
            return found.group(1).strip() if found else None

        instructor = field(r"\bInstructors?\s*:\s*([^|\n]+)")
        slot = field(r"\bSlot\s*:\s*([^|\n]+)")
        credits = field(r"\bCredits?\s*:\s*([^|\n]+)")
        category = field(r"\bCategory\s*:\s*([^|\n]+)")
        records.append(
            _make_record(
                course_code=match.group("code"),
                course_name=match.group("title"),
                department=department,
                semester=semester,
                academic_year=year,
                slot=slot,
                instructor=instructor,
                credits=credits,
                category=category,
                source=relative_source,
                line_number=index + 1,
                heading_level=heading_level,
                heading_elective=heading_elective,
            )
        )
    return records


@lru_cache(maxsize=1)
def _load_course_records() -> tuple[dict[str, Any], ...]:
    """Read timetable/course files once, on the first tool call in this process."""
    records: list[dict[str, Any]] = []
    if not DATA_DIR.is_dir():
        return ()

    for path in sorted(DATA_DIR.rglob("*.csv")):
        records.extend(_csv_course_records(path))
    course_details_dir = DATA_DIR / "course_details"
    if course_details_dir.is_dir():
        for path in sorted(course_details_dir.rglob("*.md")):
            records.extend(_markdown_course_records(path))
    return tuple(records)


def _record_matches_filters(
    record: dict[str, Any],
    department: str | None,
    semester: str | None,
    academic_year: str | None,
) -> bool:
    if department and _normalize_department(record.get("department")) != _normalize_department(department):
        return False
    if semester and record.get("semester") != semester:
        return False
    if academic_year and record.get("academic_year") != academic_year:
        return False
    return True


def _query_terms(query: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]+", query.casefold())
        if token not in _QUERY_STOPWORDS
    }


def lookup_course(
    query: str,
    department: str | None = None,
    semester: str | None = None,
    academic_year: str | None = None,
    limit: int = 10,
) -> dict[str, Any]:
    """Look up a course by code or name in the cached course tables.

    Args:
        query: Course code or distinctive part of its name, such as ``CSL7570``
            or ``Autonomous Systems``.
        department: Optional department filter, such as ``CSE`` or ``Humanities``.
        semester: Optional semester, accepted as ``1``, ``2``, ``I`` or ``II``.
        academic_year: Optional year such as ``2026-27``.
        limit: Maximum number of matching records to return.

    Returns records with their source file and CSV row or Markdown line citation.
    This tool reads source files only; its parsed records are cached in memory.
    """
    if not query.strip():
        return {"status": "invalid_query", "message": "Provide a course code or name.", "results": []}
    if not 1 <= limit <= 50:
        return {"status": "invalid_limit", "message": "limit must be between 1 and 50.", "results": []}

    normalized_semester = _normalize_semester(semester) if semester else None
    normalized_year = _infer_academic_year(academic_year or "") if academic_year else None
    if semester and not normalized_semester:
        return {"status": "invalid_semester", "message": "Use semester 1, 2, I, or II.", "results": []}
    if academic_year and not normalized_year:
        return {"status": "invalid_academic_year", "message": "Use a year such as 2026-27.", "results": []}
    code_match = _COURSE_CODE_RE.search(query)
    query_code = _normalize_code("".join(code_match.groups())) if code_match else _normalize_code(query)
    query_key = _normalize_text(" ".join(sorted(_query_terms(query))))
    query_terms = _query_terms(query)

    matches: list[tuple[int, dict[str, Any]]] = []
    for record in _load_course_records():
        if not _record_matches_filters(record, department, normalized_semester, normalized_year):
            continue
        code = _normalize_code(record.get("course_code", ""))
        title = _normalize_text(record.get("course_name", ""))
        score = 0
        if query_code and code == query_code:
            score = 100
        elif query_key and title == query_key:
            score = 90
        elif query_key and (query_key in title or title in query_key):
            score = 70
        else:
            title_terms = set(re.findall(r"[a-z0-9]+", record.get("course_name", "").casefold()))
            overlap = len(query_terms & title_terms)
            if query_terms and overlap / len(query_terms) >= 0.75:
                score = 40 + overlap
        if score:
            matches.append((score, record))

    matches.sort(key=lambda item: (-item[0], item[1].get("course_code", ""), item[1].get("source", "")))
    results = [record for _, record in matches[:limit]]
    if not results:
        return {
            "status": "not_found",
            "query": query,
            "message": "No matching course was found in the available course tables and course-detail Markdown files.",
            "results": [],
        }
    return {
        "status": "ok",
        "query": query,
        "result_count": len(results),
        "truncated": len(matches) > limit,
        "results": results,
    }


def _deduplicate_offerings(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Count a course once per department, semester, and academic year."""
    grouped: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for record in records:
        identity = _normalize_code(record.get("course_code", "")) or _normalize_text(
            record.get("course_name", "")
        )
        key = (
            identity,
            _normalize_department(record.get("department")) or "",
            record.get("semester") or "",
            record.get("academic_year") or "",
        )
        existing = grouped.get(key)
        if existing is None:
            grouped[key] = {**record, "sources": [record["citation"]]}
        elif record["citation"] not in existing["sources"]:
            existing["sources"].append(record["citation"])
    return list(grouped.values())


def count_courses(
    department: str,
    semester: str,
    level: int | None = None,
    elective_only: bool = False,
    academic_year: str | None = None,
) -> dict[str, Any]:
    """Count distinct offered courses matching department and offering filters.

    Args:
        department: Department name or abbreviation, such as ``Humanities``,
            ``SoLA`` or ``CSE``.
        semester: Required semester, accepted as ``1``, ``2``, ``I`` or ``II``.
        level: Optional course level, for example ``400`` for 400-level courses.
        elective_only: If true, include records explicitly identified as electives.
        academic_year: Optional year such as ``2026-27``.

    Returns the count, matching courses, and source citations. Records without a
    known semester or year are not counted when that filter is requested.
    """
    normalized_department = _normalize_department(department)
    normalized_semester = _normalize_semester(semester)
    normalized_year = _infer_academic_year(academic_year or "") if academic_year else None
    if not normalized_department:
        return {"status": "invalid_department", "message": "Provide a department name.", "count": 0, "courses": []}
    if not normalized_semester:
        return {"status": "invalid_semester", "message": "Provide semester 1, 2, I, or II.", "count": 0, "courses": []}
    if level is not None and (level < 100 or level > 900 or level % 100 != 0):
        return {"status": "invalid_level", "message": "level must be a hundred-level value such as 400.", "count": 0, "courses": []}
    if academic_year and not normalized_year:
        return {"status": "invalid_academic_year", "message": "Use an academic year such as 2026-27.", "count": 0, "courses": []}

    department_records = [
        record
        for record in _load_course_records()
        if _normalize_department(record.get("department")) == normalized_department
    ]
    filtered: list[dict[str, Any]] = []
    for record in department_records:
        if record.get("semester") != normalized_semester:
            continue
        if normalized_year and record.get("academic_year") != normalized_year:
            continue
        if level is not None and record.get("level") != level:
            continue
        if elective_only and not record.get("is_elective"):
            continue
        filtered.append(record)

    courses = _deduplicate_offerings(filtered)
    unknown_semester_count = sum(1 for record in department_records if not record.get("semester"))
    unknown_year_count = (
        sum(1 for record in department_records if not record.get("academic_year"))
        if normalized_year
        else 0
    )
    return {
        "status": "ok" if courses else "no_matches",
        "filters": {
            "department": department,
            "semester": normalized_semester,
            "level": level,
            "elective_only": elective_only,
            "academic_year": normalized_year,
        },
        "count": len(courses),
        "courses": courses,
        "coverage_note": (
            f"{unknown_semester_count} course record(s) for this department have no semester tagged and were excluded."
            if unknown_semester_count
            else None
        ),
        "year_coverage_note": (
            f"{unknown_year_count} course record(s) have no academic year tagged and were excluded."
            if unknown_year_count
            else None
        ),
        "message": (
            "Count is based only on matching source records; inspect the returned citations if sources conflict."
            if courses
            else "No source records matched all supplied filters; do not infer a count from missing data."
        ),
    }
