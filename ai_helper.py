import asyncio
from google import genai
import config

ai_client = genai.Client(api_key=config.GEMINI_API_KEY)

def split_text(text, limit=3500):
    chunks = []
    current_chunk = []
    current_length = 0
    for line in text.split('\n'):
        if current_length + len(line) + 1 > limit:
            if current_chunk:
                chunks.append('\n'.join(current_chunk))
            current_chunk = [line]
            current_length = len(line)
        else:
            current_chunk.append(line)
            current_length += len(line) + 1
    if current_chunk:
        chunks.append('\n'.join(current_chunk))
    return chunks

async def summarize_chunk(chunk_index, total_chunks, chunk_messages, focus_instruction):
    chunk_text = "\n".join(chunk_messages)
    prompt = f"""
    Bạn là một trợ lý phân tích dữ liệu chat chuyên nghiệp.
    Dưới đây là một phần lịch sử trò chuyện của nhóm chat (phần {chunk_index + 1}/{total_chunks}, được sắp xếp theo thứ tự thời gian tăng dần).
    Hãy tóm tắt chi tiết các hoạt động diễn ra trong phần chat này.

    {focus_instruction}

    Yêu cầu đầu ra (BẮT BUỘC):
    1. **Các chủ đề chính**: Liệt kê các chủ đề chính được thảo luận trong đoạn này.
    2. **Diễn biến chính & Timeline**: Ghi nhận các sự kiện chính kèm theo mốc thời gian [DD/MM HH:MM] và các thành viên tham gia thảo luận. Nhóm các tin nhắn liên tục lại thành các mốc chính.
    3. **Quyết định & Kết luận**: Các quyết định, thống nhất hoặc công việc được chốt (nếu có).

    Lịch sử trò chuyện cần phân tích:
    \"\"\"
    {chunk_text}
    \"\"\"
    """
    print(f"🧠 [MapReduce] Đang phân tích phân đoạn {chunk_index + 1}/{total_chunks} ({len(chunk_messages)} tin nhắn)...", flush=True)
    try:
        response = await asyncio.to_thread(
            ai_client.models.generate_content,
            model='gemma-4-31b-it',
            contents=prompt,
        )
        print(f"✅ [MapReduce] Hoàn thành phân đoạn {chunk_index + 1}/{total_chunks}.", flush=True)
        return response.text
    except Exception as e:
        print(f"❌ [MapReduce] Lỗi ở phân đoạn {chunk_index + 1}: {e}", flush=True)
        return f"[Lỗi: Không thể phân tích phân đoạn {chunk_index + 1} do lỗi hệ thống API]"

async def generate_summary(raw_messages, summary_type, clean_focus, scan_info):
    focus_instruction = ""
    if clean_focus:
        focus_instruction = f"""
        ⚠️ BẮT BUỘC TẬP TRUNG SÂU (FOCUS): Người dùng yêu cầu tập trung phân tích đặc biệt sâu vào chủ đề/câu chuyện: "{clean_focus}".
        Yêu cầu:
        1. Trọng tâm toàn bộ bài tóm tắt phải hướng về chủ đề này.
        2. Dành phần lớn nội dung của cả phần Tổng quan, Timeline và Kết luận để làm rõ diễn biến, các tình tiết, ý kiến, tranh luận và phản ứng của các thành viên xoay quanh câu chuyện này.
        3. Các đoạn hội thoại khác không liên quan đến chủ đề "{clean_focus}" hãy bỏ qua hoặc chỉ tóm tắt cực kỳ ngắn gọn (1-2 câu) để tránh làm loãng thông tin.
        """

    # Phân chia luồng xử lý: Single-Pass (nếu <= 300 tin nhắn) hoặc MapReduce (nếu > 300 tin nhắn)
    if len(raw_messages) <= 300:
        print(f"🧠 [Single-Pass] Bắt đầu phân tích trực tiếp {len(raw_messages)} tin nhắn...", flush=True)
        chat_history_text = "\n".join(raw_messages)
        if summary_type == "long":
            prompt = f"""
            Bạn là một trợ lý ảo quản lý cộng đồng Discord chuyên nghiệp. 
            Dưới đây là lịch sử trò chuyện của một nhóm chat ({scan_info}). 
            Hãy tóm tắt lại nội dung cuộc trò chuyện này một cách CHI TIẾT, ĐẦY ĐỦ và THÔNG MINH nhất bằng Tiếng Việt.

            {focus_instruction}

            Yêu cầu nghiêm ngặt về định dạng và cấu trúc (BẮT BUỘC TUÂN THỦ):
            - TUYỆT ĐỐI KHÔNG chứa lời chào, lời mở đầu (ví dụ: "Dưới đây là...", "Đây là tóm tắt...") hay lời chào kết, cảm ơn xã giao ở cuối. Đi thẳng vào nội dung chính.
            - ĐỘ DÀI BÀI VIẾT: Dưới 3500 ký tự. Viết cô đọng, súc tích, tránh rườm rà hay lặp từ.
            - BỐ CỤC BÀI VIẾT:
              1. **TỔNG QUAN CHỦ ĐỀ**: Tóm tắt ngắn gọn các chủ đề chính đang được thảo luận và không khí chung của cuộc trò chuyện.
              2. **TIMELINE DIỄN BIẾN**:
                 - PHÂN CHIA THEO NGÀY: Nếu lịch sử trò chuyện kéo dài nhiều ngày, bạn PHẢI nhóm các timeline theo từng ngày. Dù chỉ có 1 ngày duy nhất hay nhiều ngày, bạn đều phải sử dụng cấu trúc nhóm theo ngày.
                 - Mỗi ngày bắt đầu bằng tiêu đề định dạng: `### 📅 NGÀY DD/MM` (Ví dụ: `### 📅 NGÀY 09/06`).
                 - GIỮA CÁC NGÀY KHÁC NHAU: Phải ngăn cách bằng một dòng kẻ ngang markdown `---` (để phân tách rõ ràng).
                 - CÁC MỐC THỜI GIAN TRONG NGÀY: Sắp xếp theo trình tự THỜI GIAN ĐẢO NGƯỢC (mốc mới nhất lên đầu ngày, mốc cũ hơn xuống dưới).
                 - GỘP TIN NHẮN THÔNG MINH: KHÔNG liệt kê máy móc từng tin nhắn riêng lẻ. Hãy gộp nhóm các tin nhắn diễn ra liên tục/gần nhau (cùng một cuộc đối thoại hoặc chủ đề) thành một mốc thời gian.
                 - CHỈ TẬP TRUNG vào những khoảng thời gian mọi người hoạt động nhiều (lúc thảo luận sôi nổi). Tránh liệt kê các tin nhắn đơn lẻ, tán gẫu xã giao vô thưởng vô phạt hoặc các mốc thời gian không có hoạt động đáng kể.
                 - ĐỊNH DẠNG MỐC THỜI GIAN: Vì tiêu đề ngày đã có `DD/MM`, mốc thời gian ở các gạch đầu dòng CHỈ ghi giờ và phút.
                   Định dạng: `- [Giờ_bắt_đầu - Giờ_kết_thúc] @ThànhViên1, @ThànhViên2: Nội dung tóm tắt diễn biến.` (hoặc `- [Giờ:Phút]` nếu chỉ là 1 mốc ngắn).
                   Ví dụ: `- [15:31 - 15:34] @Subeo, @Mike: Thảo luận về quán trà sữa Koi Thé.` (Tuyệt đối KHÔNG ghi `- [09/06 15:31 - 15:34]`).

              3. **KẾT LUẬN & QUYẾT ĐỊNH**: Tóm tắt ngắn gọn các quyết định, thống nhất hoặc công việc được chốt lại (nếu có).
            
            Dữ liệu trò chuyện (mốc thời gian Việt Nam [Ngày/Tháng Giờ:Phút]):
            \"\"\"
            {chat_history_text}
            \"\"\"
            """
        else:
            prompt = f"""
            Bạn là một trợ lý ảo quản lý cộng đồng Discord chuyên nghiệp. 
            Dưới đây là lịch sử trò chuyện của một nhóm chat ({scan_info}). 
            Hãy tóm tắt lại nội dung cuộc trò chuyện này một cách NGẮN GỌN, SÚC TÍCH và DỄ HIỂU nhất bằng Tiếng Việt.

            {focus_instruction}

            Yêu cầu cấu trúc (BẮT BUỘC TUÂN THỦ):
            - TUYỆT ĐỐI KHÔNG chứa lời chào, lời mở đầu hay lời kết luận xã giao. Đi thẳng vào nội dung tóm tắt.
            - Giữ độ dài bài tóm tắt ngắn gọn, súc tích (dưới 1000 ký tự).
            - Tóm tắt các chủ đề chính đang thảo luận dưới dạng các gạch đầu dòng ngắn gọn.
            - Liệt kê các quyết định, kết luận quan trọng (nếu có).
            
            Dữ liệu trò chuyện (mốc thời gian Việt Nam [Ngày/Tháng Giờ:Phút]):
            \"\"\"
            {chat_history_text}
            \"\"\"
            """

        response = await asyncio.to_thread(
            ai_client.models.generate_content,
            model='gemma-4-31b-it',
            contents=prompt,
        )
        return response.text

    else:
        # Bắt đầu MapReduce
        print(f"🧠 [MapReduce] Nhận thấy có {len(raw_messages)} tin nhắn (>300). Chia làm nhiều phần để phân tích song song...", flush=True)
        chunk_size = 200
        chunks = [raw_messages[i:i + chunk_size] for i in range(0, len(raw_messages), chunk_size)]
        total_chunks = len(chunks)

        # Chạy song song các tasks Map
        tasks = [summarize_chunk(idx, total_chunks, chunk, focus_instruction) for idx, chunk in enumerate(chunks)]
        results = await asyncio.gather(*tasks)

        # Pha Reduce
        print(f"🧠 [MapReduce] Đang tổng hợp (Reduce) kết quả từ {total_chunks} phân đoạn...", flush=True)
        intermediate_summaries = ""
        for idx, res in enumerate(results):
            intermediate_summaries += f"\n\n=== TÓM TẮT PHÂN ĐOẠN ĐOẠN {idx + 1} ===\n{res}"

        if summary_type == "long":
            reduce_prompt = f"""
            Bạn là một trợ lý ảo quản lý cộng đồng Discord chuyên nghiệp. 
            Dưới đây là tổng hợp các bản tóm tắt phân đoạn từ lịch sử trò chuyện của một nhóm chat kéo dài trong thời gian qua.
            Hãy kết hợp chúng thành một bản tóm tắt toàn diện, CHI TIẾT, ĐẦY ĐỦ và THÔNG MINH nhất bằng Tiếng Việt.

            {focus_instruction}

            Yêu cầu nghiêm ngặt về định dạng và cấu trúc (BẮT BUỘC TUÂN THỦ):
            - TUYỆT ĐỐI KHÔNG chứa lời chào, lời mở đầu hay lời kết luận xã giao. Đi thẳng vào nội dung chính.
            - ĐỘ DÀI BÀI VIẾT: Dưới 3500 ký tự. Viết cô đọng, súc tích, tránh lặp ý.
            - BỐ CỤC BÀI VIẾT:
              1. **TỔNG QUAN CHỦ ĐỀ**: Tóm tắt tổng thể các chủ đề chính đã thảo luận trong suốt toàn bộ cuộc trò chuyện và không khí chung.
              2. **TIMELINE DIỄN BIẾN**:
                 - PHÂN CHIA THEO NGÀY: Bạn PHẢI nhóm các timeline theo từng ngày. Dù chỉ có 1 ngày duy nhất hay nhiều ngày, bạn đều phải sử dụng cấu trúc nhóm theo ngày.
                 - Mỗi ngày bắt đầu bằng tiêu đề định dạng: `### 📅 NGÀY DD/MM` (Ví dụ: `### 📅 NGÀY 09/06`).
                 - GIỮA CÁC NGÀY KHÁC NHAU: Phải ngăn cách bằng một dòng kẻ ngang markdown `---` (để phân tách rõ ràng).
                 - CÁC MỐC THỜI GIAN TRONG NGÀY: Sắp xếp theo trình tự THỜI GIAN ĐẢO NGƯỢC (mốc mới nhất lên đầu ngày, mốc cũ hơn xuống dưới).
                 - GỘP TIN NHẮN THÔNG MINH: Hãy tổng hợp và gộp các mốc thời gian tương tự hoặc liên quan với nhau từ các bản tóm tắt phân đoạn thành các mốc thời gian lớn có ý nghĩa. Chỉ giữ lại những khoảng thời gian thảo luận sôi nổi nhất.
                 - ĐỊNH DẠNG MỐC THỜI GIAN: Mốc thời gian ở các gạch đầu dòng CHỈ ghi giờ và phút.
                   Định dạng: `- [Giờ_bắt_đầu - Giờ_kết_thúc] @ThànhViên1, @ThànhViên2: Nội dung tóm tắt diễn biến.` (hoặc `- [Giờ:Phút]` nếu chỉ là 1 mốc ngắn).
                   Ví dụ: `- [15:31 - 15:34] @Subeo, @Mike: Thảo luận về quán trà sữa Koi Thé.` (Tuyệt đối KHÔNG ghi `- [09/06 15:31 - 15:34]`).

              3. **KẾT LUẬN & QUYẾT ĐỊNH**: Tổng hợp tất cả các quyết định, thống nhất hoặc công việc được chốt lại trong suốt cuộc trò chuyện.

            Dữ liệu tóm tắt phân đoạn:
            \"\"\"
            {intermediate_summaries}
            \"\"\"
            """
        else:
            reduce_prompt = f"""
            Bạn là một trợ lý ảo quản lý cộng đồng Discord chuyên nghiệp. 
            Dưới đây là tổng hợp các bản tóm tắt phân đoạn từ lịch sử trò chuyện của một nhóm chat.
            Hãy kết hợp chúng thành một bản tóm tắt NGẮN GỌN, SÚC TÍCH và DỄ HIỂU nhất bằng Tiếng Việt.

            {focus_instruction}

            Yêu cầu cấu trúc (BẮT BUỘC TUÂN THỦ):
            - TUYỆT ĐỐI KHÔNG chứa lời chào, lời mở đầu hay lời kết luận xã giao. Đi thẳng vào nội dung tóm tắt.
            - Giữ độ dài bài tóm tắt ngắn gọn, súc tích (dưới 1000 ký tự).
            - Tóm tắt các chủ đề chính đang thảo luận dưới dạng các gạch đầu dòng ngắn gọn.
            - Liệt kê các quyết định, kết luận quan trọng (nếu có).

            Dữ liệu tóm tắt phân đoạn:
            \"\"\"
            {intermediate_summaries}
            \"\"\"
            """

        response = await asyncio.to_thread(
            ai_client.models.generate_content,
            model='gemma-4-31b-it',
            contents=reduce_prompt,
        )
        print("✅ [MapReduce] Pha Reduce hoàn tất thành công.", flush=True)
        return response.text
