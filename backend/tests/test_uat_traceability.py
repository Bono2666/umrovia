"""S19: setiap test yang dirujuk matriks UAT MVP harus ada (keterlacakan PRD/Spec → bukti otomatis)."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MATRIX = ROOT / "docs" / "uat" / "MVP_UAT_MATRIX.md"
REQUIRED = [f"TR{n:02d}" for n in range(1, 11)] + [f"PAY{n:02d}" for n in range(1, 11)] + [
    "INV01", "INV02", "POR01", "POR02", "OPS01", "OPS02", "OPS03", "NTF01", "RPT01", "RPT02", "SEC01", "SEC02", "SEC03", "E2E",
]


def test_every_required_scenario_is_mapped():
    text = MATRIX.read_text()
    rows = {match.group(1) for match in re.finditer(r"^\| ([A-Z0-9-]+) \|", text, re.MULTILINE)}
    assert not set(REQUIRED) - rows, sorted(set(REQUIRED) - rows)


def test_every_referenced_test_exists():
    text = MATRIX.read_text()
    references = re.findall(r"`tests/(test_\w+\.py)::(test_\w+)`", text)
    assert len(references) >= 40
    missing = [f"{file}::{name}" for file, name in references
               if not re.search(rf"^def {name}\(", (ROOT / "backend" / "tests" / file).read_text(), re.MULTILINE)]
    assert not missing, missing
