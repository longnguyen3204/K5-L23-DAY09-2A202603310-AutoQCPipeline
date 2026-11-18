"""CHECK 2 — Dòng nhãn YOLO: sai định dạng, ID lớp lạ, box tràn ảnh, box rỗng, box lặp.   (Script 2 trong slide)   ★★

Test:  pytest tests/test_label_format.py -q

Mỗi dòng nhãn: `id cx cy w h` (5 số, toạ độ 0–1). Trả về list[Issue]; `Issue.line` = số dòng (đếm từ 1).

| code             | severity | khi nào                                                                  |
|------------------|----------|--------------------------------------------------------------------------|
| BAD_FORMAT       | ERROR    | không đúng 5 cột số (dùng `parse_yolo_line`, bắt `ValueError`)           |
| BAD_CLASS_ID     | ERROR    | id lớp ngoài 0..len(ds.classes)-1                                        |
| BOX_ZERO         | ERROR    | w <= 0 hoặc h <= 0                                                       |
| BOX_OUT_OF_IMAGE | ERROR    | mép box vượt [0,1] quá `cfg["label_format"]["overflow_tol"]`; extra={"overflow": mức tràn} |
| DUP_BOX          | ERROR    | cùng lớp với một dòng TRƯỚC ĐÓ và IoU > `dup_box_iou`; báo ở dòng SAU    |
| BOX_TINY         | WARN     | cạnh ngắn của box (px) < `min_box_px`  (cần `ds.image_size(stem)`)       |
| BOX_HUGE         | WARN     | w*h > `max_box_frac`                                                     |

Gợi ý
- Mép trái = x - w/2, mép phải = x + w/2 (xem câu hỏi "dòng YOLO nào lỗi?" trong slide).
- Một dòng hỏng (BAD_FORMAT, BAD_CLASS_ID, BOX_ZERO) thì `continue`, đừng kiểm tiếp hình học của dòng đó.
- Dòng thiếu cột làm script của slide dừng giữa chừng: đây là lý do phải `try/except`.
- `iou_xywh(a, b)` có sẵn trong common.py.
- Ngưỡng nằm trong `cfg["label_format"]` — đừng viết cứng số vào code.
"""
from ..common import ERROR, WARN, Issue, iou_xywh, parse_yolo_line

CHECK = "label_format"


def _issue(severity, code, stem, line, message, extra=None):
    return Issue(check=CHECK, severity=severity, code=code, image=stem,
                 message=message, line=line, extra=extra or {})


def run(ds, cfg):
    lf = cfg["label_format"]
    n_classes = len(ds.classes)
    issues = []

    for label_file in ds.label_files():
        stem = label_file.stem
        rows = ds.read_label_lines(stem)   # [(số dòng gốc, nội dung)], đã bỏ dòng trống
        if rows is None:
            continue                       # không có file nhãn: việc của check missing_labels
        size = ds.image_size(stem)         # (rộng, cao) px hoặc None nếu ảnh không mở được
        seen = []                          # [(class_id, (x, y, w, h))] các dòng hợp lệ đã duyệt

        for line_no, text in rows:
            # 1) Định dạng: sai thì báo rồi bỏ qua dòng này
            try:
                cid, x, y, w, h = parse_yolo_line(text)
            except ValueError as e:
                issues.append(_issue(ERROR, "BAD_FORMAT", stem, line_no, f"dòng nhãn sai định dạng: {e}"))
                continue

            # 2) ID lớp
            if cid < 0 or cid >= n_classes:
                issues.append(_issue(ERROR, "BAD_CLASS_ID", stem, line_no,
                                     f"ID lớp {cid} ngoài 0..{n_classes - 1}"))
                continue

            # 3) Box rỗng
            if w <= 0 or h <= 0:
                issues.append(_issue(ERROR, "BOX_ZERO", stem, line_no, f"box rỗng (w={w}, h={h})"))
                continue

            # 4) Tràn ảnh: mức tràn = đoạn vượt xa nhất ra ngoài [0,1] trong 4 mép
            overflow = max(0.0,
                           -(x - w / 2), -(y - h / 2),
                           (x + w / 2) - 1.0, (y + h / 2) - 1.0)
            if overflow > lf["overflow_tol"]:
                issues.append(_issue(ERROR, "BOX_OUT_OF_IMAGE", stem, line_no,
                                     f"box tràn ra ngoài ảnh {overflow:.4f}",
                                     extra={"overflow": overflow}))

            # 5) Box lặp: cùng lớp với dòng TRƯỚC và IoU cao -> báo ở dòng SAU (dòng hiện tại)
            box = (x, y, w, h)
            for prev_cid, prev_box in seen:
                if prev_cid == cid and iou_xywh(prev_box, box) > lf["dup_box_iou"]:
                    issues.append(_issue(ERROR, "DUP_BOX", stem, line_no,
                                         "trùng với một box cùng lớp ở dòng trước"))
                    break
            seen.append((cid, box))

            # 6) Cảnh báo: box nhỏ (cạnh ngắn theo px) / box quá lớn
            if size is not None:
                short_px = min(w * size[0], h * size[1])
                if short_px < lf["min_box_px"]:
                    issues.append(_issue(WARN, "BOX_TINY", stem, line_no,
                                         f"cạnh ngắn của box {short_px:.1f}px < {lf['min_box_px']}px"))
            if w * h > lf["max_box_frac"]:
                issues.append(_issue(WARN, "BOX_HUGE", stem, line_no,
                                     f"box phủ {w * h:.0%} diện tích ảnh"))

    return issues