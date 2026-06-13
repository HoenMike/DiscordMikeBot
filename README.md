# MikeDaBot - Discord Summary Agent 🤖

**MikeDaBot** là một bot Discord thông minh giúp tự động quét lịch sử trò chuyện trong một kênh và tạo bản tóm tắt súc tích, chi tiết kèm timeline hoặc tập trung vào một câu chuyện cụ thể sử dụng mô hình AI **Gemma 4** (`gemma-4-31b-it`). Dự án đi kèm một Web Dashboard tối giản để theo dõi trạng thái hoạt động thực tế của bot (Uptime, độ trễ API, dung lượng RAM sử dụng, log console trực tiếp).

---

## ✨ Tính năng nổi bật
- **Tóm tắt thông minh**: 
  - Chế độ ngắn gọn (`short`) giúp nắm nhanh nội dung chính.
  - Chế độ chi tiết (`long`) tạo Timeline diễn biến chia theo từng ngày rõ ràng, gộp nhóm các tin nhắn liên quan.
- **Tập trung chủ đề (Focus)**: Cho phép truyền từ khóa (ví dụ: `drama`, `lỗi deploy`) để AI tập trung phân tích sâu vào chủ đề đó và bỏ qua nội dung rác ngoài lề.
- **Tag người dùng**: Tự động thông báo (tag) cho người yêu cầu ngay khi tóm tắt xong.
- **Web Dashboard**: Xem tài nguyên hệ thống (RAM, Uptime, Latency, Guilds/Users count) và theo dõi Live Console Logs trực tiếp trên giao diện Web.
- **Graceful Shutdown**: Tự động chờ các tác vụ đang chạy dở hoàn tất (tối đa 15 giây) trước khi tắt máy hoặc cập nhật code mới, hạn chế lỗi treo bot.

---

## 🛠️ Yêu cầu hệ thống
- Python 3.10 trở lên.
- Tài khoản bot Discord (cần bật **Message Content Intent** trên Discord Developer Portal).
- Google Gemini API Key.

---

## 🚀 Hướng dẫn cài đặt & Chạy cục bộ

1. **Clone mã nguồn dự án**:
   ```bash
   git clone https://github.com/your-username/DiscordMikeBot.git
   cd DiscordMikeBot
   ```

2. **Cài đặt thư viện dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Cấu hình môi trường**:
   - Sao chép tệp mẫu cấu hình:
     ```bash
     cp .env.example .env
     ```
   - Mở tệp `.env` vừa tạo và điền các thông số Token và API Key của bạn.

4. **Khởi chạy bot**:
   ```bash
   python app.py
   ```
   - Truy cập giao diện Dashboard tại: `http://localhost:8080`

---

## 🌐 Deploy lên Render
Dự án đã được cấu hình sẵn tệp `render.yaml`. Bạn chỉ cần:
1. Đưa dự án lên kho lưu trữ GitHub của bạn.
2. Kết nối tài khoản Render với kho lưu trữ GitHub.
3. Render sẽ tự động nhận diện và deploy ứng dụng. Hãy nhớ thêm các biến môi trường (`DISCORD_TOKEN`, `GEMINI_API_KEY`) trong phần cấu hình Environment của Render.

---

## 📜 Giấy phép
Dự án được phân phối dưới giấy phép **MIT License**. Bạn hoàn toàn có thể sử dụng, sửa đổi và phân phối lại cho mục đích cá nhân hoặc thương mại.
