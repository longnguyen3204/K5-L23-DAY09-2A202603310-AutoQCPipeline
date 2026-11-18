"""BƯỚC 4 — Cửa chặn: quyết định Release / Hold / Rework.   ★

Test:  pytest tests/test_gate.py -q

Cây quyết định Day 07 (slide Day 09: "Lỗi bắt buộc chặn pipeline; lỗi cảnh báo chuyển người xem"):

  còn ≥ 1 lỗi bắt buộc (severity ERROR)                          -> "Rework"
  không còn lỗi bắt buộc, nhưng tỉ lệ ẢNH còn cảnh báo
      >= cfg["gate"]["warn_ratio_hold"]                          -> "Hold"
  còn lại                                                        -> "Release"

Tỉ lệ cảnh báo = (số ẢNH khác nhau có ≥ 1 cảnh báo) / (tổng số ảnh).  Chú ý:
- chỉ đếm issue có `image` nằm trong `image_stems` (bỏ "<dataset>", "data.yaml");
- bỏ qua ảnh nằm trong `reviewed` (người đã xem, cảnh báo của ảnh đó coi như đã xử lý) — nhưng LỖI BẮT BUỘC thì không bao giờ được bỏ qua;
- mẫu số là số ảnh, không phải số issue.

Trả về dict: decision, n_errors, n_warn_images, n_images, warn_ratio (làm tròn 4 chữ số), reasons (list[str], giải thích bằng tiếng Việt, có số liệu).
"""
from collections import Counter

from ..common import ERROR, WARN

_EPS = 1e-9  # tránh lệch số thực ở đúng ngưỡng (ví dụ 3/30 so với 0.10)


def decide(issues, image_stems, cfg, reviewed=frozenset()):
    threshold = cfg["gate"]["warn_ratio_hold"]
    stems = set(image_stems)
    reviewed = set(reviewed)
    n_images = len(stems)

    # Lỗi bắt buộc: đếm TẤT CẢ (kể cả lỗi cấp dataset như data.yaml, kể cả ảnh đã duyệt)
    errors = [i for i in issues if i.severity == ERROR]
    n_errors = len(errors)

    # Cảnh báo: chỉ tính ảnh có thật trong lô và chưa được người duyệt; đếm ẢNH, không đếm issue
    warn_images = {
        i.image for i in issues
        if i.severity == WARN and i.image in stems and i.image not in reviewed
    }
    n_warn_images = len(warn_images)
    ratio = n_warn_images / n_images if n_images else 0.0

    reasons = []
    if n_errors > 0:
        decision = "Rework"
        top = ", ".join(f"{code} ×{n}" for code, n in Counter(i.code for i in errors).most_common(3))
        reasons.append(f"Còn {n_errors} lỗi bắt buộc chưa xử lý ({top}): không được phát hành.")
    elif ratio >= threshold - _EPS:
        decision = "Hold"
        reasons.append(
            f"Không còn lỗi bắt buộc, nhưng {n_warn_images}/{n_images} ảnh còn cảnh báo "
            f"({ratio:.1%}) ≥ ngưỡng {threshold:.0%}: giữ lại chờ người duyệt thêm."
        )
    else:
        decision = "Release"
        reasons.append(
            f"Không còn lỗi bắt buộc; {n_warn_images}/{n_images} ảnh còn cảnh báo "
            f"({ratio:.1%}) < ngưỡng {threshold:.0%}: đủ điều kiện phát hành."
        )
    if reviewed:
        reasons.append(f"Đã tính {len(reviewed & stems)} ảnh do người duyệt (bỏ qua cảnh báo của các ảnh này).")

    return {
        "decision": decision,
        "n_errors": n_errors,
        "n_warn_images": n_warn_images,
        "n_images": n_images,
        "warn_ratio": round(ratio, 4),
        "reasons": reasons,
    }