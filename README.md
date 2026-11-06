# Gismeteo HA ☀️

![Gismeteo HA](custom_components/gismeteo_ha/brand/icon.png)

Tích hợp thời tiết Gismeteo cho **Home Assistant 2026.11+**, hỗ trợ **Marketplace/HACS** và có sẵn thẻ Lovelace hai chế độ.

**Tính năng:** Khởi động không chờ truy cập mạng; điều phối cập nhật tập trung; dự báo giờ/ngày; dữ liệu sensor nhiệt độ, cảm nhận*, điểm sương*, độ ẩm, áp suất, gió, gió giật, mây, lượng mưa, UV, bình minh/hoàng hôn và tầm nhìn (nếu nguồn có trường kèm đơn vị); cache an toàn; log và Diagnostics; bản dịch tiếng Việt. Thẻ Lovelace đẹp, responsive, **Chi tiết / Thu gọn**, dự báo giờ/ngày và trình chỉnh sửa trực quan.

*Dấu `*` là kết quả tính toán, không phải phép đo độc lập. Giá trị không có từ nguồn sẽ hiển thị `unknown`, không tự suy đoán.*

<!-- ha-marketplace:exclude-start -->
## Cài đặt

[![Add to Home Assistant Marketplace](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=khaisilk1910&repository=gismeteo_ha&category=integration)

**Marketplace / HACS:** Nhấn nút **Add to Marketplace** ở trên. Hoặc mở **Settings → Marketplace → Custom repositories**, thêm `https://github.com/khaisilk1910/gismeteo_ha`, loại **Integration**, rồi Install. Vào **Settings → Devices & services → Add integration → Gismeteo HA** để thêm vị trí.

**Thủ công:** Tải ZIP của bản phát hành, sao chép `custom_components/gismeteo_ha/` vào `/config/custom_components/gismeteo_ha/`, khởi động lại Home Assistant, rồi thêm tích hợp trong **Devices & services**.

<!-- ha-marketplace:exclude-end -->

## Thẻ Lovelace

Tích hợp tự phục vụ và tự đăng ký module card trong **Lovelace resource storage mode**. Dashboard → Edit → Add card → **Gismeteo HA Weather**, chọn entity `weather.*`. Có nút chuyển **Chi tiết / Thu gọn** ngay trên thẻ.

Với cấu hình resource **YAML** (không thể ghi tự động), thêm thủ công:

```yaml
lovelace:
  resource_mode: yaml
  resources:
    - url: /gismeteo_ha/gismeteo-ha-card.js
      type: module
```

Ví dụ một thẻ:

```yaml
type: custom:gismeteo-ha-card
entity: weather.my_home
mode: detailed          # detailed | compact
show_forecast: true
```

## Lưu ý quan trọng

- **Thay đổi lớn từ 3.x:** Domain cũ `gismeteo` chuyển sang `gismeteo_ha`. **Sao lưu**, ghi lại entity ID/automation, gỡ bản cũ và thư mục `custom_components/gismeteo`, cài bản mới và **cấu hình lại**. Home Assistant không tự chuyển config entry giữa hai domain.
- Gismeteo dùng endpoint **không chính thức**, có thể thay đổi hoặc chặn truy cập; không bảo đảm dữ liệu luôn sẵn có. Có thể tắt dữ liệu HTML mở rộng trong Options khi gặp HTTP 403.
- `visibility_unit: km` không chứng minh có giá trị tầm nhìn: chỉ đọc khi nguồn trả về khoảng cách có đơn vị rõ ràng. `UV` có thể xuất phát từ dự báo ngày hiện tại, không phải phép đo tức thời. Chỉ số cảm nhận và điểm sương là tính toán từ những giá trị đã có.
- Bộ sensor ngày có thể chọn **0–9 ngày** trong Options. Log lỗi và trạng thái có tại **Settings → System → Logs** và **Devices & services → Gismeteo HA → Download diagnostics**.
- Giữ bản quyền [CC BY-NC-SA 4.0](LICENSE) của dự án gốc [Limych/ha-gismeteo](https://github.com/Limych/ha-gismeteo); mã phái sinh này **không** được tự đổi sang MIT.

## Tạo release tự động

Trên GitHub vào **Actions → Publish Gismeteo HA release → Run workflow** trên nhánh `main`, nhập phiên bản như `4.0.1` (không có `v`). Workflow sẽ cập nhật `manifest.json` + `const.py`, kiểm thử, commit lên `main`, **sau đó** tạo tag và GitHub Release `v4.0.1` đúng trên commit đó. Không tạo GitHub Release thủ công trước khi cập nhật manifest.

Báo lỗi: https://github.com/khaisilk1910/gismeteo_ha/issues

### Local time display

`gismeteo_last_refresh`, `gismeteo_sunrise`, and `gismeteo_sunset` on the
weather entity display as ISO 8601 strings in **Settings → System → General →
Time zone**, including the local UTC offset. The built-in timestamp sensors
remain date/time entities; Home Assistant renders them in local time in the UI.
The bundled dashboard card uses the same HA time zone for forecast hours.
If sunrise/sunset hours appear implausible, verify the weather location and
provider data: changing the time zone cannot correct an incorrect source
observation.
