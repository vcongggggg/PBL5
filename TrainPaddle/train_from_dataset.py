from __future__ import annotations

import csv
import os
import random
import re
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

import yaml


SEED = 42
PRETRAINED_URL = (
    "https://paddle-model-ecology.bj.bcebos.com/"
    "paddlex/official_pretrained_model/en_PP-OCRv4_mobile_rec_pretrained.pdparams"
)

ROOT = Path(__file__).resolve().parents[1]
TRAIN_DIR = ROOT / "TrainPaddle"
PADDLEOCR_REPO = TRAIN_DIR / "PaddleOCR"
DATASET_DIR = TRAIN_DIR / "Dataset"
DATASET_IMAGE_DIR = DATASET_DIR / "croped"
DATASET_LABEL_CSV = DATASET_DIR / "crop_labels.csv"
DATATEST_DIR = TRAIN_DIR / "Datatest"

WORK_DIR = TRAIN_DIR / "ocr_train_work"
PRETRAINED_DIR = TRAIN_DIR / "pretrained"
PRETRAINED_MODEL = PRETRAINED_DIR / "en_PP-OCRv4_mobile_rec_pretrained.pdparams"
BASE_CONFIG = PADDLEOCR_REPO / "configs" / "rec" / "PP-OCRv4" / "en_PP-OCRv4_mobile_rec.yml"
CHAR_DICT_PATH = PADDLEOCR_REPO / "ppocr" / "utils" / "en_dict.txt"

TRAIN_LABEL = WORK_DIR / "rec_train.txt"
VAL_LABEL = WORK_DIR / "rec_val.txt"
TEST_LABEL = WORK_DIR / "rec_test.txt"
TRAIN_CONFIG = WORK_DIR / "vn_plate_rec_ppocrv4.yml"
TEST_CONFIG = WORK_DIR / "vn_plate_rec_ppocrv4_test.yml"
EXPORT_CONFIG = WORK_DIR / "vn_plate_rec_ppocrv4_export.yml"
OUTPUT_DIR = WORK_DIR / "output" / "vn_plate_rec_ppocrv4"
CANDIDATE_EXPORT_DIR = WORK_DIR / "export_candidate"
PREVIOUS_EXPORT_BACKUP_DIR = WORK_DIR / "previous_backend_export_backup"
DATATEST_PREDICTIONS = WORK_DIR / "datatest_predictions.txt"

BACKEND_EXPORT_DIR = ROOT / "backend" / "models" / "paddleocr_vn_plate_rec"
BACKEND_DICT_PATH = BACKEND_EXPORT_DIR / "vn_plate_dict.txt"

ALLOWED_RE = re.compile(r"[^0-9A-Z]")


def normalize_plate_text(text: str) -> str:
    return ALLOWED_RE.sub("", str(text or "").upper())


def run(cmd: list[str], cwd: Path | None = None, capture: bool = False) -> str:
    print(" ".join(str(part) for part in cmd))
    completed = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        check=True,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.STDOUT if capture else None,
    )
    return completed.stdout or ""


def ensure_paths() -> None:
    required = [
        PADDLEOCR_REPO / "tools" / "train.py",
        PADDLEOCR_REPO / "tools" / "eval.py",
        PADDLEOCR_REPO / "tools" / "export_model.py",
        PADDLEOCR_REPO / "tools" / "infer" / "predict_rec.py",
        DATASET_IMAGE_DIR,
        DATASET_LABEL_CSV,
        BASE_CONFIG,
        CHAR_DICT_PATH,
    ]
    missing = [path for path in required if not path.exists()]
    if missing:
        raise FileNotFoundError("Missing required paths:\n" + "\n".join(str(path) for path in missing))

    WORK_DIR.mkdir(parents=True, exist_ok=True)
    PRETRAINED_DIR.mkdir(parents=True, exist_ok=True)
    BACKEND_EXPORT_DIR.mkdir(parents=True, exist_ok=True)


def ensure_pretrained_model() -> None:
    if PRETRAINED_MODEL.exists() and PRETRAINED_MODEL.stat().st_size > 0:
        print("Using pretrained:", PRETRAINED_MODEL)
        return

    print("Downloading pretrained model:")
    print(PRETRAINED_URL)
    urllib.request.urlretrieve(PRETRAINED_URL, PRETRAINED_MODEL)
    print("Downloaded:", PRETRAINED_MODEL)


def load_rows() -> list[dict[str, str]]:
    rows = []
    skipped_missing = 0

    with DATASET_LABEL_CSV.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = str(row.get("Name", "")).strip()
            label = normalize_plate_text(str(row.get("Label", "")))
            image_path = DATASET_IMAGE_DIR / name
            if not name or not image_path.exists():
                skipped_missing += 1
                continue
            if not label or len(label) > 12:
                continue
            rows.append({
                "image": f"Dataset/croped/{name}",
                "label": label,
            })

    if not rows:
        raise RuntimeError(f"No usable rows found from {DATASET_LABEL_CSV}")

    print(f"Usable rows: {len(rows)}")
    print(f"Skipped rows with missing images: {skipped_missing}")
    return rows


def write_label_file(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(f"{row['image']}\t{row['label']}\n")


def prepare_splits(rows: list[dict[str, str]]) -> None:
    rng = random.Random(SEED)
    shuffled = rows[:]
    rng.shuffle(shuffled)

    n = len(shuffled)
    n_train = int(n * 0.8)
    n_val = int(n * 0.1)
    train_rows = shuffled[:n_train]
    val_rows = shuffled[n_train:n_train + n_val]
    test_rows = shuffled[n_train + n_val:]

    write_label_file(TRAIN_LABEL, train_rows)
    write_label_file(VAL_LABEL, val_rows)
    write_label_file(TEST_LABEL, test_rows)

    print(f"train={len(train_rows)} {TRAIN_LABEL}")
    print(f"val={len(val_rows)} {VAL_LABEL}")
    print(f"test={len(test_rows)} {TEST_LABEL}")


def detect_gpu() -> bool:
    try:
        import paddle

        return bool(paddle.is_compiled_with_cuda())
    except Exception:
        return False


def build_config(use_gpu: bool) -> dict:
    with BASE_CONFIG.open("r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    config["Global"].update({
        "use_gpu": use_gpu,
        "epoch_num": 80,
        "print_batch_step": 5,
        "save_model_dir": str(OUTPUT_DIR).replace("\\", "/"),
        "save_epoch_step": 10,
        "eval_batch_step": [0, 50],
        "pretrained_model": str(PRETRAINED_MODEL).replace("\\", "/"),
        "checkpoints": None,
        "save_inference_dir": None,
        "character_dict_path": str(CHAR_DICT_PATH).replace("\\", "/"),
        "max_text_length": 12,
        "use_space_char": False,
        "distributed": False,
        "infer_img": None,
    })

    config["Optimizer"]["lr"]["learning_rate"] = 0.0001
    config["Optimizer"]["lr"]["warmup_epoch"] = 2

    config["Train"]["dataset"]["data_dir"] = str(TRAIN_DIR).replace("\\", "/")
    config["Train"]["dataset"]["label_file_list"] = [str(TRAIN_LABEL).replace("\\", "/")]
    config["Train"]["loader"].update({
        "batch_size_per_card": 32,
        "drop_last": False,
        "num_workers": 0,
    })
    if "sampler" in config["Train"]:
        config["Train"]["sampler"]["first_bs"] = 32

    config["Eval"]["dataset"]["data_dir"] = str(TRAIN_DIR).replace("\\", "/")
    config["Eval"]["dataset"]["label_file_list"] = [str(VAL_LABEL).replace("\\", "/")]
    config["Eval"]["loader"].update({
        "batch_size_per_card": 32,
        "drop_last": False,
        "num_workers": 0,
    })

    return config


def write_yaml(path: Path, config: dict) -> None:
    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(config, f, sort_keys=False, allow_unicode=True)
    print("Wrote:", path)


def train_eval_export(use_gpu: bool) -> None:
    config = build_config(use_gpu)
    write_yaml(TRAIN_CONFIG, config)

    run([sys.executable, "tools/train.py", "-c", str(TRAIN_CONFIG)], cwd=PADDLEOCR_REPO)

    test_config = yaml.safe_load(TRAIN_CONFIG.read_text(encoding="utf-8"))
    test_config["Global"]["checkpoints"] = str(OUTPUT_DIR / "best_accuracy").replace("\\", "/")
    test_config["Eval"]["dataset"]["label_file_list"] = [str(TEST_LABEL).replace("\\", "/")]
    write_yaml(TEST_CONFIG, test_config)
    run([sys.executable, "tools/eval.py", "-c", str(TEST_CONFIG)], cwd=PADDLEOCR_REPO)

    export_config = yaml.safe_load(TRAIN_CONFIG.read_text(encoding="utf-8"))
    export_config["Global"]["pretrained_model"] = str(OUTPUT_DIR / "best_accuracy").replace("\\", "/")
    export_config["Global"]["save_inference_dir"] = str(CANDIDATE_EXPORT_DIR).replace("\\", "/")
    write_yaml(EXPORT_CONFIG, export_config)

    if CANDIDATE_EXPORT_DIR.exists():
        shutil.rmtree(CANDIDATE_EXPORT_DIR)
    run([sys.executable, "tools/export_model.py", "-c", str(EXPORT_CONFIG)], cwd=PADDLEOCR_REPO)
    remove_export_model_name(CANDIDATE_EXPORT_DIR / "inference.yml")


def remove_export_model_name(inference_yml: Path) -> None:
    """Keep repo-style inference compatible with tools/infer/predict_rec.py."""
    if not inference_yml.exists():
        return
    config = yaml.safe_load(inference_yml.read_text(encoding="utf-8"))
    if isinstance(config, dict) and "Global" in config:
        config.pop("Global", None)
        write_yaml(inference_yml, config)


def test_candidate_export(use_gpu: bool) -> str:
    if not DATATEST_DIR.exists():
        print("Skipping Datatest inference because folder does not exist:", DATATEST_DIR)
        return ""

    output = run([
        sys.executable,
        "tools/infer/predict_rec.py",
        "--image_dir",
        str(DATATEST_DIR),
        "--rec_model_dir",
        str(CANDIDATE_EXPORT_DIR),
        "--rec_char_dict_path",
        str(CHAR_DICT_PATH),
        "--rec_image_shape",
        "3,48,320",
        "--rec_algorithm",
        "SVTR_LCNet",
        "--use_space_char",
        "False",
        "--use_gpu",
        str(use_gpu),
    ], cwd=PADDLEOCR_REPO, capture=True)

    DATATEST_PREDICTIONS.write_text(output, encoding="utf-8")
    non_empty = sum(1 for line in output.splitlines() if "Predicts of" in line and "('', 0.0)" not in line)
    total = sum(1 for line in output.splitlines() if "Predicts of" in line)
    print(f"Datatest non-empty predictions: {non_empty}/{total}")
    print("Wrote:", DATATEST_PREDICTIONS)
    return output


def test_candidate_export_with_cpu_fallback(use_gpu: bool) -> str:
    try:
        return test_candidate_export(use_gpu)
    except subprocess.CalledProcessError:
        if not use_gpu:
            raise
        print("Datatest inference failed on GPU; retrying on CPU.")
        return test_candidate_export(False)


def replace_backend_export() -> None:
    required = ["inference.json", "inference.pdiparams", "inference.yml"]
    missing = [name for name in required if not (CANDIDATE_EXPORT_DIR / name).exists()]
    if missing:
        raise RuntimeError("Candidate export is missing files: " + ", ".join(missing))

    if PREVIOUS_EXPORT_BACKUP_DIR.exists():
        shutil.rmtree(PREVIOUS_EXPORT_BACKUP_DIR)
    if BACKEND_EXPORT_DIR.exists():
        shutil.copytree(BACKEND_EXPORT_DIR, PREVIOUS_EXPORT_BACKUP_DIR)

    for item in BACKEND_EXPORT_DIR.iterdir():
        if item.is_dir():
            shutil.rmtree(item)
        else:
            item.unlink()

    for name in required:
        shutil.copy2(CANDIDATE_EXPORT_DIR / name, BACKEND_EXPORT_DIR / name)
    shutil.copy2(CHAR_DICT_PATH, BACKEND_DICT_PATH)
    print("Updated backend export:", BACKEND_EXPORT_DIR)
    print("Previous backend export backup:", PREVIOUS_EXPORT_BACKUP_DIR)


def main() -> None:
    ensure_paths()
    ensure_pretrained_model()

    rows = load_rows()
    prepare_splits(rows)

    use_gpu = detect_gpu()
    print("USE_GPU:", use_gpu)
    train_eval_export(use_gpu)
    test_candidate_export_with_cpu_fallback(use_gpu)
    replace_backend_export()


if __name__ == "__main__":
    main()
