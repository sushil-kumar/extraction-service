import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))  # so `app.*` imports resolve

from app.extractor import extract_fields_from_bytes

SAMPLE_DIR = Path(__file__).parent.parent / "sample_doc"
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
    critical = expected.get("critical_fields", {})
    failures = []
    for field, exp_value in critical.items():
        act_value = actual_fields.get(field)
        if str(act_value) != str(exp_value):
            failures.append((field, str(exp_value), str(act_value)))
    return failures


async def main(bless: bool = False):
    if not SAMPLE_DIR.exists():
        print(f"No sample_doc folder found at {SAMPLE_DIR}")
        return

    results = []

    for doc_path in sorted(SAMPLE_DIR.iterdir()):
        if doc_path.suffix.lower() not in CONTENT_TYPES:
            continue

        expected_path = EXPECTED_DIR / (doc_path.stem + ".json")
        if not expected_path.exists():
            print(f"SKIP  - {doc_path.name} (no expected file — run with --bless to create one)")
            continue

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
            expected["critical_fields"] = {
                k: actual_fields.get(k) for k in expected.get("critical_fields", {})
            }
            expected_path.write_text(json.dumps(expected, indent=2, ensure_ascii=False))
            print(f"BLESSED - {doc_path.name} (baseline updated)")
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
    print(f"{passed} passed, {failed} failed, {errored} errored, {len(results)} total")

    if failed or errored:
        sys.exit(1)


if __name__ == "__main__":
    bless_mode = "--bless" in sys.argv
    asyncio.run(main(bless=bless_mode))