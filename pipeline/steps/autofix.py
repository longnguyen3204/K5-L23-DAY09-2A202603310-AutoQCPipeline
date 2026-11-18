"""BƯỚC 2/4 — Sửa tự động những lỗi bắt buộc mà máy sửa được AN TOÀN.   ★★

Test:  pytest tests/test_autofix.py -q

`fix(ds, issues, cfg) -> list[dict]`: duyệt `issues` (chỉ lỗi severity ERROR), sửa thẳng vào thư mục `ds`,
và trả về danh sách thay đổi; mỗi phần tử có khoá: image, line, action, before, after
(đây chính là file `03_fixes.csv` — bằng chứng pipeline đã làm gì, người có thể kiểm lại).

| code lỗi                                       | cách sửa                                    | action           |
|------------------------------------------------|---------------------------------------------|------------------|
| BAD_FORMAT, BAD_CLASS_ID, BOX_ZERO, DUP_BOX    | xoá dòng đó khỏi file nhãn                  | "drop_line"      |
| BOX_OUT_OF_IMAGE                               | cắt box về trong [0,1] (giữ nguyên lớp)     | "clip_box"       |
| MISSING_LABEL_FILE                             | KHÔNG sửa file (máy không thể bịa nhãn): ghi 1 dòng fix, before="(không có file)", after="chuyển người gán" | "needs_label" |
| BAD_CLASS_NAME                                 | ghi lại `names` trong data.yaml đúng `cfg["classes"]` | "rename_classes" |
| DUP_IMAGE_*, LEAK_TEST, CORRUPT_IMAGE, BAD_SIZE| xoá ảnh + nhãn khỏi `ds`                    | "remove_image"   |

Bẫy cần nghĩ tới (có test cho từng cái)
- Một file có NHIỀU dòng lỗi: số dòng trong `issues` là số dòng GỐC. Nếu xoá từng dòng một thì số dòng lệch.
  Gom theo file, rồi ghi lại MỘT lần.
- Sau khi cắt, box có thể không còn diện tích (nằm hẳn ngoài ảnh): lúc đó xoá dòng thay vì ghi box rỗng.
- Một dòng có 2 lỗi (vd. BOX_OUT_OF_IMAGE + DUP_BOX): xoá dòng thắng, chỉ ghi 1 fix `drop_line`, không ghi thêm `clip_box`. Dòng trống ở giữa file vẫn đếm vào số dòng gốc.
- Ảnh vừa bị xoá (DUP_IMAGE_*...) mà còn issue dòng của chính nó: bỏ qua êm, không được báo lỗi/chết.
- Không động tới lỗi WARN (cảnh báo là việc của người). Không sửa file ở `data/raw/` — chỉ sửa `ds`.
- Chạy lần 2 trên dữ liệu đã sửa phải không làm gì thêm (idempotent) — NGOẠI LỆ duy nhất: `needs_label` được ghi lại mỗi lần còn lỗi `MISSING_LABEL_FILE` (vì ảnh vẫn chưa có nhãn).

- `needs_label` KHÔNG tạo file nhãn rỗng (rỗng = "ảnh nền", khác với "chưa gán"). `review_queue` sẽ đẩy ảnh này lên đầu hàng đợi cho người.

Gợi ý: `yaml.safe_load / safe_dump`.
"""
from collections import defaultdict

import yaml

from ..common import ERROR, parse_yolo_line

REMOVE_CODES = {"DUP_IMAGE_EXACT", "DUP_IMAGE_NEAR", "LEAK_TEST", "CORRUPT_IMAGE", "BAD_SIZE"}
DROP_CODES = {"BAD_FORMAT", "BAD_CLASS_ID", "BOX_ZERO", "DUP_BOX"}


def _fix(image, line, action, before, after):
    return {"image": image, "line": line, "action": action, "before": before, "after": after}


def _clip_line(text):
    """Cắt box về trong [0,1]. Trả về dòng mới, hoặc None nếu box không còn diện tích."""
    try:
        cid, x, y, w, h = parse_yolo_line(text)
    except ValueError:        # không parse được thì không thể cắt: để caller xoá dòng
        return None
    x1, x2 = max(0.0, x - w / 2), min(1.0, x + w / 2)
    y1, y2 = max(0.0, y - h / 2), min(1.0, y + h / 2)
    if x2 - x1 <= 0 or y2 - y1 <= 0:
        return None
    return f"{cid} {(x1 + x2) / 2:.6f} {(y1 + y2) / 2:.6f} {x2 - x1:.6f} {y2 - y1:.6f}"


def _remove_image(ds, stem):
    """Xoá ảnh + nhãn khỏi ds. Trả về fix dict, hoặc None nếu chẳng còn gì để xoá."""
    img, lbl = ds.image_path(stem), ds.label_path(stem)
    had_label = lbl.exists()
    if img is None and not had_label:
        return None
    before = img.name if img is not None else f"{stem} (chỉ có nhãn)"
    if img is not None:
        img.unlink()
    if had_label:
        lbl.unlink()
    getattr(ds, "_size_cache", {}).pop(stem, None)   # quên kích thước đã nhớ của ảnh vừa xoá
    return _fix(stem, None, "remove_image", before, "(đã xoá ảnh và nhãn)")


def _rename_classes(ds, cfg):
    d = {}
    if ds.yaml_path.exists():
        d = yaml.safe_load(ds.yaml_path.read_text(encoding="utf-8")) or {}
    before = d.get("names")
    d["names"] = list(cfg["classes"])
    ds.yaml_path.write_text(yaml.safe_dump(d, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return _fix("data.yaml", None, "rename_classes", str(before), str(d["names"]))


def _fix_label_lines(ds, stem, per_line):
    """per_line: {số dòng gốc: tập mã lỗi}. Đọc file MỘT lần, sửa theo số dòng gốc, ghi lại MỘT lần."""
    path = ds.label_path(stem)
    if not path.exists():
        return []
    raw = path.read_text(encoding="utf-8", errors="replace").splitlines()   # cùng cách đếm với read_label_lines
    out, drop = [], set()
    fixes = []
    for line_no in sorted(per_line):
        if not 1 <= line_no <= len(raw):
            continue                                       # số dòng không còn khớp: bỏ qua êm
        codes, text = per_line[line_no], raw[line_no - 1]
        if codes & DROP_CODES:                             # xoá thắng: chỉ 1 fix drop_line
            drop.add(line_no)
            fixes.append(_fix(stem, line_no, "drop_line", text, "(đã xoá dòng)"))
        elif "BOX_OUT_OF_IMAGE" in codes:
            new = _clip_line(text)
            if new is None:                                # cắt xong không còn diện tích -> xoá
                drop.add(line_no)
                fixes.append(_fix(stem, line_no, "drop_line", text, "(đã xoá dòng)"))
            else:
                raw[line_no - 1] = new
                fixes.append(_fix(stem, line_no, "clip_box", text, new))
    if fixes:
        kept = [ln for i, ln in enumerate(raw, 1) if i not in drop]
        path.write_text(("\n".join(kept) + "\n") if kept else "", encoding="utf-8")
    return fixes


def fix(ds, issues, cfg):
    errors = [i for i in issues if i.severity == ERROR]   # cảnh báo là việc của người: không đụng tới
    fixes = []

    # 1) Xoá ảnh trước: các issue dòng của ảnh đã xoá sẽ bị bỏ qua ở các bước sau
    removed = set()
    for i in errors:
        if i.code in REMOVE_CODES and i.image not in removed:
            removed.add(i.image)
            f = _remove_image(ds, i.image)
            if f:
                fixes.append(f)

    # 2) Tên lớp trong data.yaml (làm tối đa 1 lần)
    if any(i.code == "BAD_CLASS_NAME" for i in errors):
        fixes.append(_rename_classes(ds, cfg))

    # 3) Thiếu file nhãn: KHÔNG tạo file, chỉ ghi lại để chuyển người gán (mỗi ảnh 1 dòng)
    seen_missing = set()
    for i in errors:
        if i.code == "MISSING_LABEL_FILE" and i.image not in removed and i.image not in seen_missing:
            seen_missing.add(i.image)
            fixes.append(_fix(i.image, None, "needs_label", "(không có file)", "chuyển người gán"))

    # 4) Lỗi theo dòng: gom theo ảnh -> theo số dòng gốc, rồi sửa mỗi file một lần
    by_image = defaultdict(lambda: defaultdict(set))
    for i in errors:
        if (i.code in DROP_CODES or i.code == "BOX_OUT_OF_IMAGE") and i.line is not None and i.image not in removed:
            by_image[i.image][i.line].add(i.code)
    for stem in sorted(by_image):
        fixes.extend(_fix_label_lines(ds, stem, by_image[stem]))

    return fixes