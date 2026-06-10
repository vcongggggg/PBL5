from __future__ import annotations

import csv
import re
from pathlib import Path

import matplotlib.pyplot as plt


ROOT = Path(__file__).resolve().parent
WORK_DIR = ROOT / "ocr_train_work"
OUTPUT_DIR = WORK_DIR / "visualizations"
TRAIN_LOG = WORK_DIR / "output" / "vn_plate_rec_ppocrv4_full" / "train.log"
DATATEST_PREDICTIONS = WORK_DIR / "datatest_predictions_full.txt"


TRAIN_PATTERN = re.compile(
    r"epoch: \[(?P<epoch>\d+)/(?P<total>\d+)\], global_step: (?P<step>\d+), "
    r"lr: (?P<lr>[0-9.]+), acc: (?P<acc>[0-9.]+), "
    r"norm_edit_dis: (?P<norm>[0-9.]+), CTCLoss: (?P<ctc>[0-9.]+), "
    r"NRTRLoss: (?P<nrtr>[0-9.]+), loss: (?P<loss>[0-9.]+)"
)
CUR_METRIC_PATTERN = re.compile(
    r"cur metric, acc: (?P<acc>[0-9.]+), norm_edit_dis: (?P<norm>[0-9.]+), fps: (?P<fps>[0-9.]+)"
)
BEST_METRIC_PATTERN = re.compile(
    r"best metric, acc: (?P<acc>[0-9.]+), .*norm_edit_dis: (?P<norm>[0-9.]+), "
    r"fps: (?P<fps>[0-9.]+), best_epoch: (?P<epoch>\d+)"
)


def moving_average(values: list[float], window: int) -> list[float]:
    averaged: list[float] = []
    for index in range(len(values)):
        start = max(0, index - window + 1)
        averaged.append(sum(values[start : index + 1]) / (index - start + 1))
    return averaged


def parse_log() -> tuple[list[dict], list[dict], dict | None]:
    train_rows: list[dict] = []
    val_rows: list[dict] = []
    best_row: dict | None = None

    for line in TRAIN_LOG.read_text(encoding="utf-8", errors="ignore").splitlines():
        train_match = TRAIN_PATTERN.search(line)
        if train_match:
            data = train_match.groupdict()
            train_rows.append(
                {
                    "epoch": int(data["epoch"]),
                    "step": int(data["step"]),
                    "lr": float(data["lr"]),
                    "acc": float(data["acc"]),
                    "norm_edit_dis": float(data["norm"]),
                    "ctc_loss": float(data["ctc"]),
                    "nrtr_loss": float(data["nrtr"]),
                    "loss": float(data["loss"]),
                }
            )
            continue

        cur_match = CUR_METRIC_PATTERN.search(line)
        if cur_match:
            data = cur_match.groupdict()
            val_rows.append(
                {
                    "index": len(val_rows) + 1,
                    "acc": float(data["acc"]),
                    "norm_edit_dis": float(data["norm"]),
                    "fps": float(data["fps"]),
                }
            )
            continue

        best_match = BEST_METRIC_PATTERN.search(line)
        if best_match:
            data = best_match.groupdict()
            best_row = {
                "epoch": int(data["epoch"]),
                "acc": float(data["acc"]),
                "norm_edit_dis": float(data["norm"]),
                "fps": float(data["fps"]),
            }

    return train_rows, val_rows, best_row


def parse_datatest() -> list[dict]:
    if not DATATEST_PREDICTIONS.is_file():
        return []

    rows: list[dict] = []
    for line in DATATEST_PREDICTIONS.read_text(encoding="utf-8", errors="ignore").splitlines():
        parts = line.split("\t")
        if len(parts) >= 3:
            rows.append(
                {
                    "image": Path(parts[0]).name,
                    "prediction": parts[1],
                    "confidence": float(parts[2]),
                }
            )
    return rows


def save_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def style_plot(title: str, xlabel: str, ylabel: str) -> None:
    plt.title(title)
    plt.xlabel(xlabel)
    plt.ylabel(ylabel)
    plt.grid(True, alpha=0.25)
    plt.tight_layout()


def create_plots(train_rows: list[dict], val_rows: list[dict], datatest_rows: list[dict]) -> None:
    steps = [row["step"] for row in train_rows]

    plt.figure(figsize=(10, 5))
    plt.plot(steps, moving_average([row["loss"] for row in train_rows], 20), label="Total loss")
    plt.plot(steps, moving_average([row["ctc_loss"] for row in train_rows], 20), label="CTC loss")
    plt.plot(steps, moving_average([row["nrtr_loss"] for row in train_rows], 20), label="NRTR loss")
    plt.legend()
    style_plot("Training Loss", "Global step", "Loss")
    plt.savefig(OUTPUT_DIR / "training_loss.png", dpi=160)
    plt.close()

    plt.figure(figsize=(10, 5))
    plt.plot(steps, moving_average([row["acc"] for row in train_rows], 20), label="Train acc")
    plt.plot(steps, moving_average([row["norm_edit_dis"] for row in train_rows], 20), label="Train norm edit distance")
    plt.legend()
    style_plot("Training Accuracy Metrics", "Global step", "Score")
    plt.savefig(OUTPUT_DIR / "training_metrics.png", dpi=160)
    plt.close()

    eval_indexes = [row["index"] for row in val_rows]
    plt.figure(figsize=(10, 5))
    plt.plot(eval_indexes, [row["acc"] for row in val_rows], marker="o", markersize=3, label="Validation acc")
    plt.plot(eval_indexes, [row["norm_edit_dis"] for row in val_rows], marker="o", markersize=3, label="Validation norm edit distance")
    plt.legend()
    style_plot("Validation Metrics", "Evaluation checkpoint", "Score")
    plt.savefig(OUTPUT_DIR / "validation_metrics.png", dpi=160)
    plt.close()

    if datatest_rows:
        plt.figure(figsize=(10, 5))
        plt.hist([row["confidence"] for row in datatest_rows], bins=10, color="#2878b5", edgecolor="white")
        style_plot("Datatest Confidence Distribution", "Confidence", "Image count")
        plt.savefig(OUTPUT_DIR / "datatest_confidence.png", dpi=160)
        plt.close()


def write_report(train_rows: list[dict], val_rows: list[dict], best_row: dict | None, datatest_rows: list[dict]) -> None:
    final_train = train_rows[-1]
    best_val_by_acc = max(val_rows, key=lambda row: (row["acc"], row["norm_edit_dis"])) if val_rows else None
    confidences = [row["confidence"] for row in datatest_rows]

    report = [
        "# PaddleOCR Training Visualization",
        "",
        "## Summary",
        "",
        f"- Training log: `{TRAIN_LOG}`",
        f"- Train samples logged: {len(train_rows)}",
        f"- Validation checkpoints: {len(val_rows)}",
        f"- Last logged epoch: {final_train['epoch']}",
        f"- Last logged step: {final_train['step']}",
    ]

    if best_row:
        report.extend(
            [
                f"- Best validation epoch: {best_row['epoch']}",
                f"- Best validation acc: {best_row['acc']:.4f}",
                f"- Best validation norm_edit_dis: {best_row['norm_edit_dis']:.4f}",
                f"- Best validation fps: {best_row['fps']:.2f}",
            ]
        )

    if best_val_by_acc:
        report.extend(
            [
                "",
                "## Best Validation Checkpoint",
                "",
                f"- Accuracy: {best_val_by_acc['acc']:.4f}",
                f"- Norm edit distance: {best_val_by_acc['norm_edit_dis']:.4f}",
                f"- FPS: {best_val_by_acc['fps']:.2f}",
            ]
        )

    if confidences:
        report.extend(
            [
                "",
                "## Datatest Inference",
                "",
                f"- Images: {len(confidences)}",
                f"- Average confidence: {sum(confidences) / len(confidences):.4f}",
                f"- Min confidence: {min(confidences):.4f}",
                f"- Max confidence: {max(confidences):.4f}",
            ]
        )

    report.extend(
        [
            "",
            "## Figures",
            "",
            "![Training loss](training_loss.png)",
            "",
            "![Training metrics](training_metrics.png)",
            "",
            "![Validation metrics](validation_metrics.png)",
            "",
            "![Datatest confidence](datatest_confidence.png)",
            "",
        ]
    )

    (OUTPUT_DIR / "training_visual_report.md").write_text("\n".join(report), encoding="utf-8")


def main() -> None:
    if not TRAIN_LOG.is_file():
        raise FileNotFoundError(f"Training log not found: {TRAIN_LOG}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    train_rows, val_rows, best_row = parse_log()
    datatest_rows = parse_datatest()

    if not train_rows:
        raise RuntimeError("No training rows parsed from train.log")

    save_csv(OUTPUT_DIR / "training_points.csv", train_rows)
    save_csv(OUTPUT_DIR / "validation_points.csv", val_rows)
    save_csv(OUTPUT_DIR / "datatest_predictions.csv", datatest_rows)
    create_plots(train_rows, val_rows, datatest_rows)
    write_report(train_rows, val_rows, best_row, datatest_rows)

    print(f"output_dir={OUTPUT_DIR}")
    print(f"train_points={len(train_rows)}")
    print(f"validation_points={len(val_rows)}")
    if best_row:
        print(
            "best_validation="
            f"epoch:{best_row['epoch']} "
            f"acc:{best_row['acc']:.4f} "
            f"norm_edit_dis:{best_row['norm_edit_dis']:.4f} "
            f"fps:{best_row['fps']:.2f}"
        )
    if datatest_rows:
        confidences = [row["confidence"] for row in datatest_rows]
        print(
            "datatest="
            f"count:{len(confidences)} "
            f"avg_conf:{sum(confidences) / len(confidences):.4f} "
            f"min_conf:{min(confidences):.4f} "
            f"max_conf:{max(confidences):.4f}"
        )


if __name__ == "__main__":
    main()
