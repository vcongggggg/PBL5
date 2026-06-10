from __future__ import annotations

import csv
import random
import re
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DATASET_DIR = ROOT / "Dataset"
CROP_DIR = DATASET_DIR / "croped"
LABEL_CSV = DATASET_DIR / "crop_labels.csv"
WORK_DIR = ROOT / "ocr_train_work"
DICT_PATH = WORK_DIR / "vn_plate_dict.txt"

TRAIN_PATH = WORK_DIR / "rec_train.txt"
VAL_PATH = WORK_DIR / "rec_val.txt"
TEST_PATH = WORK_DIR / "rec_test.txt"

RANDOM_SEED = 42
TRAIN_RATIO = 0.8
VAL_RATIO = 0.1
MAX_TEXT_LENGTH = 12
ALLOWED_CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def normalize_label(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z]", "", value or "").upper()


def split_counts(total: int) -> tuple[int, int, int]:
    train_count = int(total * TRAIN_RATIO)
    val_count = int(round(total * VAL_RATIO))
    test_count = total - train_count - val_count
    return train_count, val_count, test_count


def write_split(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(f"Dataset/croped/{row['name']}\t{row['label']}\n")


def main() -> None:
    if not LABEL_CSV.is_file():
        raise FileNotFoundError(f"Label CSV not found: {LABEL_CSV}")
    if not CROP_DIR.is_dir():
        raise FileNotFoundError(f"Crop image directory not found: {CROP_DIR}")

    existing_images = {p.name for p in CROP_DIR.iterdir() if p.is_file()}
    rows: list[dict[str, str]] = []
    rejected: Counter[str] = Counter()
    chars: set[str] = set()

    with LABEL_CSV.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for raw in reader:
            name = (raw.get("Name") or "").strip()
            label = normalize_label(raw.get("Label") or "")
            type_name = (raw.get("Type") or "unknown").strip() or "unknown"

            if name not in existing_images:
                rejected["missing_image"] += 1
                continue
            if not label:
                rejected["empty_label"] += 1
                continue
            if len(label) > MAX_TEXT_LENGTH:
                rejected["too_long"] += 1
                continue
            invalid = set(label) - set(ALLOWED_CHARS)
            if invalid:
                rejected["invalid_chars"] += 1
                continue

            chars.update(label)
            rows.append({"name": name, "label": label, "type": type_name})

    by_type: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        by_type[row["type"]].append(row)

    rng = random.Random(RANDOM_SEED)
    train_rows: list[dict[str, str]] = []
    val_rows: list[dict[str, str]] = []
    test_rows: list[dict[str, str]] = []

    for type_name in sorted(by_type):
        bucket = by_type[type_name]
        rng.shuffle(bucket)
        train_count, val_count, _ = split_counts(len(bucket))
        train_rows.extend(bucket[:train_count])
        val_rows.extend(bucket[train_count : train_count + val_count])
        test_rows.extend(bucket[train_count + val_count :])

    rng.shuffle(train_rows)
    rng.shuffle(val_rows)
    rng.shuffle(test_rows)

    WORK_DIR.mkdir(parents=True, exist_ok=True)
    write_split(TRAIN_PATH, train_rows)
    write_split(VAL_PATH, val_rows)
    write_split(TEST_PATH, test_rows)
    DICT_PATH.write_text("\n".join(ALLOWED_CHARS) + "\n", encoding="utf-8", newline="\n")

    print(f"csv_rows={sum(1 for _ in LABEL_CSV.open('r', encoding='utf-8-sig')) - 1}")
    print(f"image_files={len(existing_images)}")
    print(f"accepted={len(rows)}")
    print(f"rejected={dict(rejected)}")
    print(f"train={len(train_rows)} val={len(val_rows)} test={len(test_rows)}")
    print(f"chars={''.join(sorted(chars))}")
    print("type_distribution:")
    for type_name in sorted(by_type):
        total = len(by_type[type_name])
        train_count = sum(1 for row in train_rows if row["type"] == type_name)
        val_count = sum(1 for row in val_rows if row["type"] == type_name)
        test_count = sum(1 for row in test_rows if row["type"] == type_name)
        print(
            f"  type={type_name} total={total} "
            f"train={train_count} val={val_count} test={test_count}"
        )


if __name__ == "__main__":
    main()
