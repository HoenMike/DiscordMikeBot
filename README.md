# 🤖 MikeDaBot - Discord Summary Bot

MikeDaBot là một bot Discord thông minh được tích hợp AI (Gemini/Gemma 4) chuyên tóm tắt nội dung các cuộc hội thoại trong các kênh chat một cách nhanh chóng, sạch sẽ và hiệu quả.

## 🚀 Tính Năng Nổi Bật

- **Tóm tắt cuộc trò chuyện thông minh**: Hỗ trợ hai chế độ tóm tắt:
  - **Tóm tắt ngắn gọn (`short`)**: Tóm lược nhanh các chủ đề chính và quyết định quan trọng.
  - **Tóm tắt dài & Timeline chi tiết (`long`)**: Bố cục các diễn biến hội thoại theo từng ngày, gộp nhóm tin nhắn thông minh và phân tách dòng thời gian bằng các mốc giờ hoạt động sôi nổi.
- **Tập trung sâu (Focus Mode)**: Khả năng "laser-focus" vào một chủ đề hoặc câu chuyện cụ thể (ví dụ: drama, lỗi deploy, game mới) theo yêu cầu của người dùng để phân tích sâu hơn, lược bỏ bớt các thông tin ngoài lề.
- **Web Dashboard trực quan**: Giao diện dashboard hiện đại giúp giám sát thời gian thực (Uptime, độ trễ API, số lượng máy chủ, RAM sử dụng, log console trực tiếp).
- **Graceful Shutdown**: Tự động hoãn tắt máy tối đa 15 giây khi có lệnh cập nhật hệ thống để hoàn thành các tác vụ tóm tắt đang chạy dở.
- **Thông báo thông minh**: Tự động tag người dùng khi tóm tắt xong, tinh giản tối đa các thông báo thừa.

## 🛠️ Lệnh Slash Command

### `/tomtat`
Dùng để tóm tắt lịch sử trò chuyện của kênh chat.

**Các tham số tùy chọn:**
- `channel`: Kênh chat cần tóm tắt (Mặc định là kênh hiện tại).
- `hours`: Quét tin nhắn trong X giờ qua (Tối đa 168 giờ - 7 ngày).
- `limit`: Giới hạn số lượng tin nhắn quét tối đa (Tối đa 500 tin nhắn).
- `summary_type`: Chọn kiểu tóm tắt `short` (Ngắn gọn) hoặc `long` (Chi tiết kèm Timeline).
- `focus`: Từ khóa/chủ đề cụ thể cần bot tập trung phân tích sâu.

## ⚙️ Cài Đặt và Khởi Chạy

### 1. Yêu Cầu Hệ Thống
- Python 3.10+
- Các thư viện cần thiết trong `requirements.txt`

### 2. Cấu Hình Environment
Tạo file `.env` tại thư mục gốc với các khóa sau:
```env
DISCORD_TOKEN=your_discord_bot_token
GEMINI_API_KEY=your_gemini_api_key
PORT=8080
```

### 3. Chạy Cục Bộ (Local)
Cài đặt dependencies:
```bash
pip install -r requirements.txt
```
Khởi chạy bot và máy chủ web:
```bash
python app.py
```

## 🌐 Triển Khai (Deployment)
Dự án được tối ưu hóa cấu hình để chạy dễ dàng trên **Render** (hoặc bất kỳ nền tảng PaaS nào hỗ trợ Gunicorn/Flask và các tiến trình chạy ngầm). Cấu hình Render được khai báo sẵn tại file `render.yaml`.
