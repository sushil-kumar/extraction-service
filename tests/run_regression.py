import asyncio
import json
import sys
from pathlib import Path

def find_project_root(start: Path) -> Path:
    current = start.resolve()
    for _ in range(5):
        if (current / "app").is_dir() and any((current / "app").glob("*.py")):
            return current
        current = current.parent
    raise RuntimeError(f"Could not locate project root (a directory containing 'app/') above {start}")


PROJECT_ROOT = find_project_root(Path(__file__).parent)
sys.path.insert(0, str(PROJECT_ROOT))

from app.extractor import extract_fields_from_bytes

SAMPLE_DIR = PROJECT_ROOT / "sample_doc"
EXPECTED_DIR = Path(__file__).parent / "expected"

CONTENT_TYPES = {
    ".pdf": "application/pdf",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
}


async def run_one(doc_path: Path, module: str | None) -> dict:
    content_type = CONTENT_TYPES.get(doc_path.suffix.lower())
    if not content_type:
        raise ValueError(f"Unsupported file type: {doc_path.suffix}")
    file_bytes = doc_path.read_bytes()
    return await extract_fields_from_bytes(file_bytes, content_type, module=module)


def compare(actual_fields: dict, expected: dict) -> list[tuple[str, str, str]]:
    critical = expected.get("critical_fields") or {}
    failures = []
    for field, exp_value in critical.items():
        act_value = actual_fields.get(field)
        if str(act_value) != str(exp_value):
            failures.append((field, str(exp_value), str(act_value)))
    return failures


async def main(bless: bool = False, name_filter: list[str] | None = None):
    if not SAMPLE_DIR.exists():
        print(f"No sample_doc folder found at {SAMPLE_DIR}")
        return

    EXPECTED_DIR.mkdir(parents=True, exist_ok=True)
    results = []

    for doc_path in sorted(SAMPLE_DIR.iterdir()):
        if doc_path.suffix.lower() not in CONTENT_TYPES:
            continue

        if name_filter and not any(f.lower() in doc_path.name.lower() for f in name_filter):
            continue

        expected_path = EXPECTED_DIR / (doc_path.stem + ".json")

        if not expected_path.exists():
            if not bless:
                print(f"SKIP  - {doc_path.name} (no expected file — run with --bless to create one)")
                continue
            # brand new document under --bless: create a minimal expected file to fill in below
            expected = {"module": None, "critical_fields": {}}
        else:
            expected = json.loads(expected_path.read_text())

        print(f"Running {doc_path.name} ...")

        try:
            result = await run_one(doc_path, expected.get("module"))
        except Exception as e:
            print(f"ERROR - {doc_path.name}: {e}")
            results.append((doc_path.name, "ERROR", []))
            continue

        actual_fields = result["extracted_fields"]

        if bless:
            existing_critical = expected.get("critical_fields") or {}
            if not existing_critical:
                # nothing defined yet — snapshot everything, so it can be trimmed down manually later
                expected["critical_fields"] = dict(actual_fields)
                note = "(full snapshot — no critical_fields were defined yet, trim manually as needed)"
            else:
                # already has a defined set — only refresh those specific fields
                expected["critical_fields"] = {k: actual_fields.get(k) for k in existing_critical}
                note = f"({len(existing_critical)} tracked field(s) refreshed)"

            expected_path.write_text(json.dumps(expected, indent=2, ensure_ascii=False))
            print(f"BLESSED - {doc_path.name} {note}")
            results.append((doc_path.name, "BLESSED", []))
            continue

        failures = compare(actual_fields, expected)
        status = "PASS" if not failures else "FAIL"
        results.append((doc_path.name, status, failures))

        print(f"{status}  - {doc_path.name}")
        for field, exp, act in failures:
            print(f"         {field}: expected={exp!r}  actual={act!r}")

        if result.get("fields_requiring_review"):
            flagged_and_failed = set(f for f, _, _ in failures) & set(result["fields_requiring_review"])
            if flagged_and_failed:
                print(f"         (note: {sorted(flagged_and_failed)} already flagged for manual review — known-flaky)")

    print()
    passed = sum(1 for _, s, _ in results if s == "PASS")
    failed = sum(1 for _, s, _ in results if s == "FAIL")
    errored = sum(1 for _, s, _ in results if s == "ERROR")
    blessed = sum(1 for _, s, _ in results if s == "BLESSED")

    if bless:
        print(f"{blessed} blessed, {errored} errored, {len(results)} total")
    else:
        print(f"{passed} passed, {failed} failed, {errored} errored, {len(results)} total")
        if failed or errored:
            sys.exit(1)


if __name__ == "__main__":
    bless_mode = "--bless" in sys.argv
    filter_args = [a for a in sys.argv[1:] if not a.startswith("--")]
    asyncio.run(main(bless=bless_mode, name_filter=filter_args or None))