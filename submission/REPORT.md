# Báo cáo Day 09 — Nguyễn Nhân Thành Long, 2A202603310

## 1. Kết luận trước
Pipeline đã xử lý 224 ảnh ở intake, loại 22 ảnh do lỗi ảnh/kích thước/trùng/rò rỉ, còn 202 ảnh cho bước kiểm tra nhãn. Sau khi sửa tự động và duyệt tối đa 80 ảnh, kết quả là **Release**: 0 lỗi bắt buộc còn lại và 16/202 ảnh còn cảnh báo (7,9%), thấp hơn ngưỡng Hold 10%. Quyết định này chỉ phản ánh các gate và báo cáo hiện có; các cảnh báo ngữ nghĩa vẫn cần được hiểu là nghi vấn do model, không phải xác nhận lỗi.

## 2. Lỗi và phân việc
Bảng dưới tổng hợp số dòng lỗi ở v1 theo mã (`02_error_list_v1.txt`). Máy xử lý các lỗi có quy tắc chắc chắn; cảnh báo cần hiểu nội dung ảnh được đưa cho người duyệt. “Số dòng” là số phát hiện, không nhất thiết là số ảnh duy nhất.

| Mã lỗi | Số ảnh/dòng | Ai sửa | Vì sao |
|---|---:|---|---|
| BAD_CLASS_ID | 6 | Máy | ID ngoài danh sách lớp, có thể loại dòng sai định dạng khỏi bản làm việc và ghi log. |
| BAD_CLASS_NAME | 2 | Người | Tên lớp cấu hình cần xác nhận theo bộ lớp hợp lệ. |
| BAD_FORMAT | 3 | Người | Không thể suy ra an toàn nội dung bị thiếu/không phải số. |
| BAD_SIZE | 3 | Người | Ảnh quá nhỏ; cần quyết định loại hoặc thay nguồn ảnh. |
| BOX_OUT_OF_IMAGE | 8 | Máy | Có thể kẹp tọa độ trong phạm vi ảnh; thay đổi phải được ghi nhận. |
| BOX_ZERO | 4 | Người | Hộp suy biến, không đủ thông tin để tự khôi phục. |
| CORRUPT_IMAGE | 2 | Người | Cần thay hoặc loại ảnh không đọc được. |
| DUP_BOX | 7 | Máy | Có thể bỏ dòng trùng hoàn toàn, giữ một bản. |
| DUP_IMAGE_EXACT | 8 | Máy | Trùng byte; giữ một ảnh đại diện và loại bản sao. |
| DUP_IMAGE_NEAR | 4 | Người | Ảnh gần trùng có thể khác nội dung hữu ích; cần xem trước khi loại. |
| LEAK_TEST | 5 | Người | Trùng với kho test/val là nguy cơ rò rỉ; cần xử lý theo quy tắc chia tập. |
| MISSING_LABEL_FILE | 6 | Người | Không thể tự tạo nhãn đáng tin cậy; cần gán nhãn hoặc loại ảnh. |
| POSSIBLE_FALSE_POS | 29 | Người | Model không khớp nhãn chưa đủ chứng minh nhãn sai. |
| POSSIBLE_LOOSE_BOX | 12 | Người | Độ lệch hộp cần đối chiếu vật thể thật. |
| POSSIBLE_MISSING | 32 | Người | Model có thể nhầm; cần kiểm tra ảnh trước khi thêm box. |
| POSSIBLE_WRONG_CLASS | 14 | Người | Phân lớp của model chỉ là ý kiến thứ hai. |
| BOX_TINY / BOX_HUGE | 6 / 3 | Người | Ngưỡng kích thước chỉ đánh dấu bất thường, không khẳng định nhãn sai. |
| EMPTY_LABEL / CLASS_RARE | 12 / 4 | Người | Cần xác định ảnh nền hay thiếu nhãn; lớp hiếm cần xem theo ngữ cảnh. |

`05_review_queue.csv` xếp theo tổng trọng số ưu tiên của các mã trên từng ảnh. Vì vậy ảnh có lỗi bắt buộc như `NEEDS_LABEL` (trọng số 10), hoặc nhiều cảnh báo cùng lúc, đứng trước ảnh chỉ có cảnh báo nhẹ. Ngân sách 80 ảnh là 80 ảnh đầu hàng đợi; log cho biết đã duyệt đủ 80/80. Đây là số ảnh được xem, không phải số lỗi ngữ nghĩa đã xác nhận.

## 3. Calibration (2 ngưỡng)

| Tham số | Khởi đầu | Đã chọn | Precision / Recall (trước → sau) | Lý do (đánh đổi) |
|---|---:|---:|---|---|
| `duplicates.phash_dist` | 2 | 12 | `DUP_IMAGE_NEAR`: 1.00 / 0.50 → 1.00 / 0.67 (F1 0.67 → 0.80); `DUP_IMAGE_EXACT` giữ 1.00 / 1.00 | Từ 4 đến 14 kết quả không đổi; chọn 12 trong vùng ổn định để hạn chế loại nhầm ảnh khác nhau. Đổi lại vẫn bỏ sót 2/6 ảnh gần trùng trong calib. 16 bắt thêm một ảnh nhưng 20 làm giảm khả năng bắt cả ảnh trùng chính xác. |
| `second_opinion.conf` | 0.25 | 0.8 | `WRONG_CLASS`: 0.56 / 0.83 → 1.00 / 0.83; `MISSING`: 0.50 / 1.00 → 0.67 / 0.75; `LOOSE_BOX`: 0.29 / 0.40 → 0.50 / 0.20; `FALSE_POS`: 0.31 / 1.00 → không đổi | Ở raw, conf=0.7 để lại 29/202 ảnh cảnh báo (14,4%), vượt ngưỡng 10% nên Hold; conf=0.8 để lại 16/202 (7,9%) nên Release. Chấp nhận recall thấp hơn cho `MISSING` và `LOOSE_BOX`; đây là đánh đổi để giảm hàng đợi. `FALSE_POS` dùng `fp_conf` riêng nên không đổi theo sweep này. |

Một điểm calibration có thể gây hiểu nhầm: `POSSIBLE_FALSE_POS` giữ 11 FP và precision 0.31 ở mọi mức `second_opinion.conf`, vì ngưỡng riêng của loại này là `fp_conf=0.1`. Trong 13 cảnh báo loại này ở raw v3, đã xem 7 ảnh bằng `viz_labels.py`: 5 box thực tế đúng và 2 có lỗi nhãn. Đây là mẫu xem thủ công nhỏ, không đủ để suy rộng rằng toàn bộ cảnh báo còn lại là nhầm.

## 4. Cửa chặn và điểm mù

**(a) Cửa chặn hoạt động đúng.** Lần chạy chính (ngân sách duyệt 80 ảnh): Release, 0 lỗi bắt buộc, 16/202 ảnh còn cảnh báo (7,9% < 10%). Để chứng minh gate chặn thật, tôi chạy `python -m pipeline.run --budget 0 --reports work/rep_nb --export-dir work/exp_nb` (không có người duyệt). Vòng 1 có 36 lỗi bắt buộc; tự sửa được 35 thay đổi, còn 6 lỗi bắt buộc (MISSING_LABEL_FILE ×6) vì máy không được bịa nhãn cho ảnh thiếu file nhãn. Không ai gán nên kết luận là **REWORK**, mã thoát **20**, log ghi "KHÔNG xuất: còn lỗi bắt buộc" và không có dataset trong `work/exp_nb`. Khi chạy bình thường, người duyệt gán nhãn cho 6 ảnh này nên cổng cho Release.

**(b) Điểm mù (có bằng chứng).**
1. *Box lỏng nhẹ lọt lưới:* trong calibration, LOOSE_BOX recall chỉ 0,20 ở conf 0,8 (bỏ sót 4/5).
   Chỉ box có IoU < 0,5 mới bị báo (vd. img_0021, IoU 0,49); box IoU 0,5–0,6 vẫn lọt.
2. *Ảnh trùng biến đổi mạnh:* với phash_dist=12, DUP_IMAGE_NEAR recall 0,67 (sót 2/6); ở 16 vẫn sót 1/6.
   Ảnh bị crop/đổi màu mạnh có khoảng cách phash lớn nên vẫn vào dataset. Calibration chỉ có 39 ảnh nên không đo được mức này chính xác.
3. *Model lớn không phải đáp án vàng:* trong 7/13 cảnh báo POSSIBLE_FALSE_POS tôi đã mở, 5 box thực ra đúng
   (người bị che, ở mép ảnh hoặc ở nền mà yolo26l bỏ sót), chỉ 2 là lỗi nhãn thật. Ngược lại, lỗi mà model cũng không thấy
   sẽ không bao giờ bị báo, nên cần mắt người kiểm tra trước khi sửa hoặc thêm box.

## 5. Train: raw vs clean
Chưa chạy huấn luyện hoặc chưa có bảng `submission/results/comparison.md` trong thư mục kết quả hiện có, nên chưa thể so sánh mAP50 giữa raw và clean hay độ lệch giữa các seed. Không kết luận clean tốt hơn chỉ từ việc pipeline Release. Khi có kết quả, cần so chênh lệch clean − raw với biến động giữa seed; nếu chênh lệch nằm trong mức biến động thì kết luận chưa đủ bằng chứng. Hai giả thuyết cần kiểm tra là (1) ảnh trùng/rò rỉ test trong raw làm điểm raw bị lệch, đối chiếu danh sách duplicate/leak với split; (2) nhãn máy còn lại trong clean tạo nhiễu, kiểm tra mẫu dự đoán và nhãn sau làm sạch. Test chỉ có 100 ảnh cũng khiến mAP biến động đáng kể; nên dùng cùng split và nhiều seed.

## 6. Quyết định và ghi chú AI
Quyết định theo báo cáo hiện tại là **Release**: 0 lỗi bắt buộc còn lại, 16/202 ảnh cảnh báo (7,9%) dưới ngưỡng 10%, sau khi dùng đủ ngân sách duyệt 80 ảnh. Nếu yêu cầu độ tin cậy cao hơn trước khi phát hành, bước tiếp theo là xem nốt các ảnh cảnh báo chưa được duyệt, ưu tiên `POSSIBLE_FALSE_POS`, `POSSIBLE_MISSING` và `POSSIBLE_WRONG_CLASS`, rồi chạy lại pipeline và kiểm tra manifest export.

- **Prompt chính:** Dùng Claude gợi ý cho 4 module.
- **Cách kiểm:** Đọc code theo checklist (không hard-code ngưỡng, không `except: pass`, autofix chỉ sửa trong `ds`). Theo ghi chú hiện có, đã chạy `pytest` và thử thêm 3 ca ngoài test: dòng có hai lỗi, dòng trống giữa file, ảnh có nhiều dự đoán. Cần thay câu này bằng kết quả/thông tin cụ thể nếu các bước đó chưa thực sự chạy.
- **Một lần AI sai:** Bản `label_format` đầu tiên giả định sai API (`Issue(stem=, msg=)`, `ds.stems`); lỗi được phát hiện khi đọc `common.py` và đã sửa lại.
