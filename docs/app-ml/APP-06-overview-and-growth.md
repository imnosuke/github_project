# APP-06 — Overview và Growth Analytics

Ngày: 14/11/2026. Trạng thái: **hoàn tất local trên fixture**; chưa tích hợp nguồn thật APP-07.

## Overview

- Tracked repos: distinct registry IDs có tracking interval giao với kỳ.
- Active repos, tổng events, star/fork events: chỉ công bố toàn kỳ khi mọi ngày complete và metrics đầy đủ.
- Daily trend giữ khoảng trống ngày missing/provisional; complete day không activity là zero.
- Không cộng daily distinct actors thành unique contributors toàn kỳ. Counts gồm bot.

## Growth

Dùng ngày kết thúc bộ lọc làm anchor T; cửa sổ N chọn 7 hoặc 30. Current là T−N+1…T, previous là T−2N+1…T−N, inclusive UTC. Start date của bộ lọc chung không cắt lookback cần cho growth; giao diện giải thích điều này.

- Xếp hạng mặc định current giảm, delta giảm, ID tăng; hỗ trợ sort absolute delta hoặc growth % với baseline dương.
- Growth % = 100 × (current−previous)/previous khi previous > 0.
- Cả hai zero: no_activity, 0%; baseline zero/current dương: new_activity, % null.
- Repo thiếu lịch sử hoặc ngày incomplete bị loại, hiển thị số lượng và danh sách nguyên nhân.
- Có bảng current/previous/delta/%/state và chart top 20 theo thứ tự chọn; không gọi ranking này là prediction ML.

## Kiểm tra

`apps/streamlit/tests/test_analytics.py` kiểm tra overview có 6 tracked/5 active repo, 119 star events từ 26/10 đến 01/11/2026; trend missing không thành zero; ranking và UI loại dữ liệu incomplete. Chạy chung bộ test ứng dụng/data:

```bash
python3 -m pytest apps/streamlit/tests -q
```

AppTest chưa là visual browser QA. Fixture chủ yếu có star events, chưa xác minh tính đúng parser/Gold thật. Overview hiện aggregate fixture trong memory; APP-07 cần đẩy aggregation/filter vào serving adapter với giới hạn truy vấn phù hợp. Chưa benchmark latency.

## Tiếp theo

APP-07 cần contract được DE xác nhận, registry/status/publication và kết nối Gold. Có thể tiếp tục ML-01/02 hoặc chuẩn bị adapter live độc lập; không giả định pipeline hiện đã đáp ứng contract.
