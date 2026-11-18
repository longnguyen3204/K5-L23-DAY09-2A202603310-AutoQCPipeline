"""CHECK 6 — Ý kiến thứ hai: so nhãn với một model LỚN HƠN (yolo26l).   ★★★ (khó nhất, đáng điểm nhất)

Test:  pytest tests/test_second_opinion.py -q

Máy kiểm quy tắc, người kiểm ý nghĩa (slide). Các lỗi như thiếu nhãn / gán nhầm lớp hợp lệ / box lỏng
KHÔNG bắt được bằng quy tắc cú pháp. Ta nhờ một model mạnh hơn "nhìn lại" và CHỈ CẢNH BÁO (model cũng có thể sai):
những ảnh bị cờ sẽ vào hàng đợi cho NGƯỜI duyệt.

`preds[stem]` = list `[id_lớp, conf, cx, cy, w, h]` của model (lấy qua `get_preds(ds, cfg, "checker")` nếu preds=None).
`L = ds.valid_boxes(stem)` = list `(id_lớp, cx, cy, w, h)` của nhãn (đã bỏ dòng hỏng).
Ngưỡng ở `cfg["second_opinion"]`: conf, min_area_px, fp_conf, iou_missing, iou_match, iou_loose.

Thuật toán gợi ý, với từng ảnh (bỏ qua ảnh không có trong preds hoặc không có file nhãn):
  P = dự đoán có conf >= conf  VÀ diện tích px (w*W * h*H) >= min_area_px
  Với mỗi dự đoán r trong P: lấy các nhãn có IoU(r, nhãn) >= iou_missing  (cands)
   - không có cands                            -> POSSIBLE_MISSING     (model thấy vật mà nhãn không có box)
   - có cands cùng lớp, tốt nhất IoU < iou_loose -> POSSIBLE_LOOSE_BOX  (đúng vật, box lỏng/lệch)
   - không có cands cùng lớp, nhưng cands tốt nhất IoU >= iou_match (khác lớp) -> POSSIBLE_WRONG_CLASS
  Với mỗi dòng nhãn hợp lệ: nếu IoU với MỌI dự đoán (conf >= fp_conf, không lọc diện tích) đều < iou_missing
                                             -> POSSIBLE_FALSE_POS  (box nhãn không khớp vật nào model thấy; Issue.line = số dòng)

Chi tiết các ca biên (test kiểm đúng các ca này)
- `cands` gồm nhãn MỌI lớp có IoU >= iou_missing; "tốt nhất cùng lớp" = cands cùng lớp có IoU lớn nhất; "tốt nhất khác lớp" tương tự với cands khác lớp.
- Thứ tự quyết định cho mỗi dự đoán: (1) cands rỗng -> MISSING. (2) có cands cùng lớp: IoU tốt nhất < iou_loose -> LOOSE_BOX, ngược lại KHÔNG cờ
  (nhãn đúng lớp đã phủ vật này, kể cả khi còn nhãn khác lớp chồng lên). (3) không có cands cùng lớp: nếu IoU tốt nhất khác lớp >= iou_match -> WRONG_CLASS;
  nếu chỉ có khác lớp với IoU trong [iou_missing, iou_match) -> không cờ gì (mơ hồ: để cho FALSE_POS / lần duyệt khác).
- Một dự đoán sinh tối đa MỘT issue (MISSING / LOOSE_BOX / WRONG_CLASS); một ảnh có thể có nhiều issue.
- Thứ tự issue: theo `ds.image_files()` rồi theo thứ tự dự đoán trong `preds[stem]`, cuối cùng là các FALSE_POS theo số dòng; `Issue.image` = stem, `Issue.line` chỉ đặt cho FALSE_POS.

Lưu ý số dòng: dùng `ds.read_label_lines(stem)` (giữ số dòng gốc, kể cả dòng hỏng/trống) để lấy `Issue.line`; `valid_boxes` KHÔNG giữ số dòng.

Tất cả severity WARN; `Issue.extra` nên có {"conf": ...} hoặc {"iou": ...} (hàng đợi duyệt dùng conf để xếp ưu tiên).

Gợi ý
- `iou_xywh` có sẵn. Dòng nhãn hỏng không được làm script chết (dùng `ds.valid_boxes` và `parse_yolo_line` trong try).
- Kết quả phụ thuộc mạnh vào ngưỡng: calibrate chúng ở Bước 3 thay vì đoán.
"""
from ..common import WARN, Issue, iou_xywh, parse_yolo_line
from ..model_cache import get_preds

CHECK = "second_opinion"


def _issue(code, stem, message, line=None, extra=None):
    return Issue(check=CHECK, severity=WARN, code=code, image=stem,
                 message=message, line=line, extra=extra or {})


def _label_rows(ds, stem):
    """[(số dòng gốc, (id, cx, cy, w, h))] của các dòng parse được và có id lớp hợp lệ.
    Giống ds.valid_boxes nhưng GIỮ số dòng gốc (cần cho POSSIBLE_FALSE_POS)."""
    rows = ds.read_label_lines(stem)
    if rows is None:
        return None
    out = []
    for line_no, text in rows:
        try:
            box = parse_yolo_line(text)
        except ValueError:
            continue                        # dòng hỏng: check label_format đã báo
        if 0 <= box[0] < len(ds.classes):
            out.append((line_no, box))
    return out


def run(ds, cfg, preds=None):
    c = cfg["second_opinion"]
    if preds is None:
        preds = get_preds(ds, cfg, "checker")
    issues = []

    for img in ds.image_files():
        stem = img.stem
        # Chấp nhận cả hai để không âm thầm bỏ qua mọi ảnh nếu get_preds trả khoá có đuôi.
        key = stem if stem in preds else (img.name if img.name in preds else None)
        if key is None:
            continue
        rows = _label_rows(ds, stem)
        if rows is None:                    # không có file nhãn: việc của missing_labels
            continue
        size = ds.image_size(stem)
        if size is None:                    # ảnh không mở được: không tính được diện tích px
            continue
        W, H = size
        labels = [box for _, box in rows]   # (id, cx, cy, w, h)

        # --- Phần 1: với mỗi dự đoán đủ tin cậy và đủ lớn, xem nhãn có phủ nó không
        for r in preds[key]:
            cls, conf = int(r[0]), r[1]
            rbox = tuple(r[2:6])
            if conf < c["conf"] or (rbox[2] * W) * (rbox[3] * H) < c["min_area_px"]:
                continue
            cands = [(iou_xywh(rbox, lb[1:]), lb[0]) for lb in labels]
            cands = [(iou, lcls) for iou, lcls in cands if iou >= c["iou_missing"]]

            if not cands:
                issues.append(_issue("POSSIBLE_MISSING", stem,
                                     f"model thấy lớp {cls} (conf {conf:.2f}) nhưng nhãn không có box nào khớp",
                                     extra={"conf": conf}))
                continue
            same = [iou for iou, lcls in cands if lcls == cls]
            if same:
                best = max(same)
                if best < c["iou_loose"]:
                    issues.append(_issue("POSSIBLE_LOOSE_BOX", stem,
                                         f"đúng vật (lớp {cls}) nhưng box lệch: IoU {best:.2f} < {c['iou_loose']}",
                                         extra={"conf": conf, "iou": round(best, 4)}))
                continue                    # nhãn cùng lớp đã phủ vật này: không cờ
            best_other = max(iou for iou, _ in cands)
            if best_other >= c["iou_match"]:
                issues.append(_issue("POSSIBLE_WRONG_CLASS", stem,
                                     f"cùng vị trí (IoU {best_other:.2f}) nhưng model nói lớp {cls}, nhãn khác lớp",
                                     extra={"conf": conf, "iou": round(best_other, 4)}))
            # còn lại (khác lớp, IoU trong [iou_missing, iou_match)): mơ hồ -> không cờ

        # --- Phần 2: với mỗi dòng nhãn hợp lệ, xem model có thấy vật nào ở đó không
        fp_boxes = [tuple(r[2:6]) for r in preds[key] if r[1] >= c["fp_conf"]]   # không lọc diện tích
        for line_no, box in rows:
            best = max((iou_xywh(box[1:], pb) for pb in fp_boxes), default=0.0)
            if best < c["iou_missing"]:
                issues.append(_issue("POSSIBLE_FALSE_POS", stem,
                                     f"box lớp {box[0]} không khớp vật nào model thấy (IoU tốt nhất {best:.2f})",
                                     line=line_no, extra={"iou": round(best, 4)}))

    return issues