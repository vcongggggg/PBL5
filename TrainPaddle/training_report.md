# PaddleOCR VN Plate Training Report

## Dataset

- Source labels: `TrainPaddle/Dataset/crop_labels.csv`
- Source images: `TrainPaddle/Dataset/croped`
- Usable rows with existing images: 360
- Split seed: 42
- Train/val/test split: 288 / 36 / 36
- Label normalization: uppercase, remove characters outside `[0-9A-Z]`

## Training

- Base config: `TrainPaddle/PaddleOCR/configs/rec/PP-OCRv4/en_PP-OCRv4_mobile_rec.yml`
- Pretrained model: `TrainPaddle/pretrained/en_PP-OCRv4_mobile_rec_pretrained.pdparams`
- Character dictionary: `TrainPaddle/PaddleOCR/ppocr/utils/en_dict.txt`
- Algorithm: `SVTR_LCNet`
- Image shape: `3,48,320`
- Max text length: 12
- Use space char: false
- Epochs: 80
- Batch size: 32

## Internal Test

- Best epoch: 79
- Accuracy: 0.0
- Normalized edit distance: 0.32254485456187576

## Datatest Export Check

- Export path: `backend/models/paddleocr_vn_plate_rec`
- Datatest images: 50
- Non-empty predictions: 50/50
- Result quality note: predictions are no longer empty/zero-confidence, but many outputs are still partial strings such as `30`, `390`, or `3230`; the model likely needs more/cleaner labeled crop data for accurate full-plate recognition.

## Backend Check

- `backend.app.ai_service` loads the exported recognition model as `CustomPlateOcrReader`.
