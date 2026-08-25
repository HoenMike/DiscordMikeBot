import asyncio
from google.genai import types
import config
from core.ai import get_ai_client

# Cấu hình generation mặc định cho tất cả các lệnh gọi AI tóm tắt
# temperature thấp để giảm thiểu hallucination, buộc AI bám sát dữ liệu
SUMMARY_CONFIG = types.GenerateContentConfig(
    temperature=config.SUMMARY_TEMPERATURE,
)
# QA Evaluator có thể linh hoạt hơn một chút
QA_CONFIG = types.GenerateContentConfig(
    temperature=config.QA_TEMPERATURE,
)


async def summarize_chunk(chunk_index, total_chunks, chunk_messages, focus_instruction):
    chunk_text = "\n".join(chunk_messages)
    prompt = f"""
    Bạn là một trợ lý phân tích dữ liệu chat chuyên nghiệp, thông minh, sâu sắc và tinh tế.
    Dưới đây là một phần lịch sử trò chuyện của nhóm chat (phần {chunk_index + 1}/{total_chunks}, được sắp xếp theo thứ tự thời gian tăng dần từ cũ đến mới).
    Hãy tóm tắt chi tiết các hoạt động diễn ra trong phần chat này.

    🚨 QUY TẮC TUYỆT ĐỐI - CHỐNG ẢO GIÁC (ANTI-HALLUCINATION):
    - CHỈ được phép tóm tắt các nội dung, sự kiện, mốc thời gian và tên người dùng THỰC SỰ xuất hiện trong văn bản được cung cấp dưới đây.
    - TUYỆT ĐỐI KHÔNG thêm thông tin ngoài văn bản đầu vào.
    - TUYỆT ĐỐI KHÔNG bịa ra tên người dùng, ngày tháng, sự kiện hay quyết định không có trong văn bản.

    {focus_instruction}

    🧠 NGUYÊN TẮC PHÂN TÍCH THÔNG MINH & GIÀU DỮ KIỆN (SMART & SUBSTANTIVE SYNTHESIS):
    1. **GỠ RỐI NGỮ CẢNH (DISENTANGLE CONTEXT)**: Tách bạch các câu chuyện diễn ra song song hoặc chọt ngang, không trộn lẫn các chủ đề khác nhau.
    2. **GIÀU DỮ KIỆN, LÝ DO & QUAN ĐIỂM CỤ THỂ**:
       - Tránh tóm tắt chung chung vô hồn kiểu "A và B bàn về game".
       - Hãy ghi rõ: Ai nói gì, thích/chê điều gì, vì lý do gì, số liệu/dẫn chứng cụ thể ra sao để người đọc hiểu ngay bối cảnh mà không cần cuộn lại chat gốc.
    3. **PHÂN BIỆT ĐÙA CỢT, NÓI KHÁY & TỪ NGỮ CÔNG SỞ MỈA MAI (BANTER & SARCASM DETECTION)**:
       - Các thành viên Discord thường xuyên trêu chọc, nói kháy, châm biếm hoặc mượn các thuật ngữ công sở/chính trị một cách hài hước (ví dụ: "viết request ticket gửi BA PM", "ngon vô code đê", "cán bộ", "người có tiền góp tiền người có sức góp sức").
       - Phải hiểu đúng ngầm ý (subtext) của câu đùa thay vì hiểu nghĩa đen cứng nhắc. Tuyệt đối không biến câu nói đùa thành quyết định công việc thực tế.
    4. **BỌC 100% TÊN THÀNH VIÊN TRONG DẤU BACKTICK**: Luôn dùng `Tên` (ví dụ: `Vũ Lưu`, `Tuan🐤`). TUYỆT ĐỐI KHÔNG dùng ký tự `@`.

    Yêu cầu đầu ra (BẮT BUỘC):
    1. **Các chủ đề chính**: Liệt kê các chủ đề chính được thảo luận trong đoạn này.
    2. **Diễn biến chính & Timeline (Sắp xếp theo thứ tự thời gian TĂNG DẦN - từ cũ nhất đến mới nhất)**:
       - Phân nhóm rõ theo từng ngày nếu đoạn chat trải qua nhiều ngày (dạng `### 📅 [Thứ], DD/MM`).
       - Mốc thời gian dạng: `• [HH:MM - HH:MM] **Chủ đề**: Tường thuật giàu dữ kiện, lý do và quan điểm cụ thể, bọc 100% tên thành viên trong `Tên`.`
       - Giữ chính xác mốc ngày/tháng để pha tổng hợp không bị nhầm lẫn.
    3. **Quyết định & Kết luận**: Các quyết định, thống nhất hoặc công việc thực tế được chốt (nếu có).

    Lịch sử trò chuyện cần phân tích:
    \"\"\"
    {chunk_text}
    \"\"\"
    """
    print(f"🧠 [MapReduce] Đang phân tích phân đoạn {chunk_index + 1}/{total_chunks} ({len(chunk_messages)} tin nhắn)...", flush=True)
    try:
        response = await asyncio.to_thread(
            get_ai_client().models.generate_content,
            model=config.GEMINI_DATA_MODEL,
            contents=prompt,
            config=SUMMARY_CONFIG,
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

    # Phân chia luồng xử lý: Single-Pass (nếu <= limit) hoặc MapReduce (nếu > limit)
    if len(raw_messages) <= config.SINGLE_PASS_MSG_LIMIT:
        print(f"🧠 [Single-Pass] Bắt đầu phân tích trực tiếp {len(raw_messages)} tin nhắn (Model: {config.GEMINI_SUMMARY_MODEL})...", flush=True)
        chat_history_text = "\n".join(raw_messages)
        if summary_type == "long":
            prompt = f"""
            Bạn là một trợ lý ảo quản lý cộng đồng Discord thông minh, sâu sắc, tinh tế và chuyên nghiệp.
            Dưới đây là lịch sử trò chuyện của một nhóm chat ({scan_info}).
            Hãy tóm tắt lại nội dung cuộc trò chuyện này một cách CHI TIẾT, GIÀU DỮ KIỆN, ĐẦY ĐỦ, MẠCH LẠC và THÔNG MINH nhất bằng Tiếng Việt.

            {focus_instruction}

            🚨 QUY TẮC TUYỆT ĐỐI - CHỐNG ẢO GIÁC (ANTI-HALLUCINATION) - VI PHẠM = THẤT BẠI HOÀN TOÀN:
            - CHỈ được phép tóm tắt các nội dung, sự kiện, mốc thời gian và tên người dùng THỰC SỰ có trong văn bản dữ liệu đầu vào.
            - TUYỆT ĐỐI KHÔNG thêm thông tin từ kiến thức huấn luyện, từ các phiên hội thoại trước, hoặc từ bất kỳ nguồn nào ngoài văn bản đầu vào.
            - TUYỆT ĐỐI KHÔNG bịa ra ngày tháng, tên người dùng, sự kiện hay quyết định không xuất hiện trong văn bản.
            - Nếu lịch sử trò chuyện chỉ có dữ liệu ngày X → tuyệt đối không đề cập đến ngày X+1 hay bất kỳ ngày nào khác.

            🧠 NGUYÊN TẮC TÓM TẮT THÔNG MINH, TINH TẾ & GIÀU DỮ KIỆN (SMART & SUBSTANTIVE CONTEXT):
            1. **GỠ RỐI HỘI THOẠI SONG SONG (DISENTANGLE CONVERSATIONS)**:
               - Các thành viên Discord thường nói chuyện chéo, chêm vào nhau hoặc bàn nhiều chủ đề cùng lúc.
               - Hãy phân tích và hiểu rõ từng mạch câu chuyện riêng biệt. KHÔNG ĐƯỢC trộn lẫn (blend context) các chủ đề không liên quan vào nhau.
            2. **GIÀU DỮ KIỆN, NÊU RÕ LÝ DO & QUAN ĐIỂM CỤ THỂ (SUBSTANTIVE CONTEXT)**:
               - TUYỆT ĐỐI TRÁNH tóm tắt chung chung, hời hợt kiểu: "A và B bàn về game", "nhóm nói về việc đi chơi", "Vũ Lưu chia sẻ bàn phím cơ".
               - HÃY NÊU RÕ CHI TIẾT CỐT LÕI:
                 • Ai thích / chê cái gì và VÌ LÝ DO GÌ? (Ví dụ: `Miraei` ngại đi Đầm Sen vì trời nắng sau lần chụp kỷ yếu; `Vũ Lưu`, `Tuan🐤` và `fearsofevil` chê Slack nặng nề và Zalo khó tích hợp webhook, khen Discord mượt và chill).
                 • Ai chia sẻ thông tin gì và NỘI DUNG/SỐ LIỆU CỤ THỂ là gì? (Ví dụ: `Vũ Lưu` tìm thấy phím cơ giá siêu rẻ trên Facebook gửi `jun` xem; `Regiko` thắc mắc câu hỏi Microservices vs Monolith của thầy Việt được `129600` giải đáp để làm slide).
                 • Ai có dự định gì, TÍNH TOÁN CỤ THỂ THẾ NÀO? (Ví dụ: `Tuan🐤` tính mua đất ở Vĩnh Long rẻ hơn và xuống Cần Thơ lập nghiệp gần gia đình vì sợ layoff ở TP.HCM; `Stelle` nhắc lưu ý quy hoạch).
               - **MỤC TIÊU**: Người đọc đọc xong bản tóm tắt là hiểu trọn vẹn diễn biến và lý do của từng bên mà **KHÔNG CẦN cuộn lên đọc lại tin nhắn gốc**.
            3. **PHÂN BIỆT ĐÙA CỢT, NÓI KHÁY & TỪ NGỮ CÔNG SỞ MỈA MAI (BANTER & SARCASM DETECTION)**:
               - Thành viên Discord thường nói đùa, cà khịa, châm biếm hoặc mượn các thuật ngữ công sở/chính trị một cách hài hước (ví dụ: "viết request ticket gửi BA PM", "ngon vô code đê", "cán bộ", "người có tiền góp tiền người có sức góp sức", "quy trình").
               - **HIỂU ĐÚNG NGẦM Ý (SUBTEXT)**:
                 • Hãy nhận diện và tường thuật đúng bản chất là trêu đùa/nói kháy thay vì chép lại nguyên văn thô kệch hoặc hiểu theo nghĩa đen.
                 • Ví dụ: Khi một thành viên chê bot và người tạo bot nói *"vậy thì viết request ticket đi để BA PM review rồi đẩy cho dev"* hay *"m ngon m vô code đê"*, bản chất là người tạo bot đang **kháy lại rằng muốn góp ý thì phải nói chi tiết cụ thể ra chứ đừng nhận xét chung chung/suông**.
               - **TUYỆT ĐỐI KHÔNG BIẾN CÂU ĐÙA THÀNH QUYẾT ĐỊNH CÔNG VIỆC**: Trong phần **KẾT LUẬN & QUYẾT ĐỊNH**, tuyệt đối KHÔNG liệt kê các câu đùa công sở/kháy nhau thành quyết định công việc chính thức!
            4. **LỌC BỎ NHIỄU**:
               - Tự động bỏ qua các câu chào hỏi xã giao, đùa cụt lủn hoặc chêm lời vô nghĩa không mang lại thông tin.

            🎨 QUY ĐỊNH ĐỊNH DẠNG & HIỂN THỊ TÊN THÀNH VIÊN (BẮT BUỘC):
            - TUYỆT ĐỐI KHÔNG DÙNG KÝ TỰ `@` trước tên thành viên (không dùng `@User`).
            - TUYỆT ĐỐI KHÔNG để sót ID mention thô của Discord (như `<@123456789>`).
            - TUYỆT ĐỐI KHÔNG liệt kê một danh sách dài tên người ở đầu mốc thời gian (ví dụ cấm viết: `[15:30] @A, @B, @C, @D: ...`).
            - BỌC 100% TÊN THÀNH VIÊN TRONG DẤU BACKTICK: MỌI LẦN nhắc đến bất kỳ thành viên nào (ở đầu câu, thân câu, sau liên từ, sau "nhắc đến...", "được..."), BẮT BUỘC phải bọc trong dấu backtick như `Tên` (ví dụ: `Vũ Lưu`, `Tuan🐤`, `129600`, `jun`, `Poop`, `Miraei`, `Stelle`, `Regiko`) để làm nổi bật trên Discord. Tuyệt đối không để sót tên nào dạng plain text không có backtick.

            📐 BỐ CỤC BÀI VIẾT (BẮT BUỘC TUÂN THỦ):
            - TUYỆT ĐỐI KHÔNG chứa lời chào, lời mở đầu hay lời cảm ơn xã giao. Đi thẳng vào nội dung.
            - ĐỘ DÀI BÀI VIẾT: Dưới 3500 ký tự. Viết cô đọng, súc tích, giàu thông tin.
            - CẤU TRÚC:
              1. **TỔNG QUAN CHỦ ĐỀ**: Tóm tắt ngắn gọn bức tranh toàn cảnh, các chủ đề nổi bật và không khí chung của cuộc trò chuyện. (TUYỆT ĐỐI KHÔNG liệt kê toàn bộ danh sách thành viên trong ngoặc đơn ở đầu bài).
              2. **TIMELINE DIỄN BIẾN**:
                 - **SẮP XẾP THỜI GIAN XUÔI (CHRONOLOGICAL: TỪ CŨ NHẤT ĐẾN MỚI NHẤT)**:
                   - Thứ tự ngày: Bắt đầu từ ngày cũ nhất và tiến dần đến ngày mới nhất (ví dụ: `### 📅 T7, 23/08` trước, sau đó mới đến `### 📅 CN, 24/08`).
                   - Thứ tự mốc giờ trong từng ngày: Bắt đầu từ mốc giờ sớm nhất đến mốc giờ muộn nhất (ví dụ: `16:13` ➔ `17:05` ➔ `19:08` ➔ `21:40` ➔ `23:19` ➔ `23:54`... sang ngày mới: `00:05` ➔ `00:13` ➔ `00:26` ➔ `00:39`).
                 - **PHÂN CHIA THEO NGÀY (KÈM THỨ) & RANH GIỚI NỬA ĐÊM**:
                   - Tiêu đề mỗi ngày (CÓ KÈM THỨ TRONG TUẦN): `### 📅 [Thứ], DD/MM` (Ví dụ: `### 📅 T7, 23/08`, `### 📅 CN, 24/08`, `### 📅 T2, 25/08`...). Thứ trong tuần lấy từ mốc thời gian của tin nhắn.
                   - GIỮA CÁC NGÀY KHÁC NHAU: Phải có một dòng kẻ ngang markdown `---`.
                   - Ranh giới ngày chuẩn xác: Mọi tin nhắn từ `00:00` đến `23:59` của ngày nào BẮT BUỘC phải nằm trọn vẹn dưới tiêu đề của ngày đó. Không được để lẫn tin nhắn 23:xx sang ngày hôm sau.
                 - **ĐỊNH DẠNG MỐC THỜI GIAN**:
                   - Mỗi mốc thời gian bắt đầu bằng dấu chấm tròn `•`.
                   - Nếu là một khoảng thời gian: `• [Giờ_bắt_đầu - Giờ_kết_thúc] **Chủ đề chính ngắn gọn**: Nội dung tường thuật giàu dữ kiện, lý do và quan điểm cụ thể, bọc 100% tên thành viên trong `Tên`.`
                   - Nếu là một mốc/tin nhắn đơn lẻ (hoặc bắt đầu và kết thúc cùng 1 phút): CHỈ ghi `• [HH:MM] **Chủ đề**: ...` (TUYỆT ĐỐI KHÔNG ghi `[HH:MM - HH:MM]` nếu 2 giờ giống nhau).
                   - Ví dụ đúng:
                     `• [16:13 - 16:15] **Chia sẻ code**: `Yato` gửi đoạn code try-catch nhờ mọi người xem giúp, `Poop` thả cảm xúc hưởng ứng và nhận xét vui.`
                     `• [22:10] **Chênh lệch mức lương**: `Miraei` chia sẻ bài báo phản ánh mức lương khởi điểm của fresher khối Big4 kiểm toán và IT hiện đang phân hóa mạnh.`
                     `• [23:19 - 23:58] **Hoàn thành bài tập & Đánh giá công cụ làm việc**: `Regiko` thông báo đã hoàn thành slide phản biện môn Kiến trúc phần mềm và được `129600` khích lệ. `Vũ Lưu`, `Tuan🐤` và `fearsofevil` cùng thảo luận, so sánh các nền tảng công việc, trong đó chê bai sự nặng nề của Slack và sự bất tiện của Zalo, đồng thời ca ngợi Discord là chân ái để làm việc và chill.`
              3. **KẾT LUẬN & QUYẾT ĐỊNH**:
                 - CHỈ ghi nhận các quyết định, thống nhất, lịch hẹn hoặc dự định THỰC TẾ (ví dụ: chốt kèo đi chơi, thống nhất giờ nộp bài, quyết định học chứng chỉ/chuyển việc).
                 - Nếu toàn bộ cuộc trò chuyện chỉ là trò chuyện phiếm, đùa giỡn, cà khịa hoặc tâm sự mà KHÔNG có quyết định thực tế nào được chốt lại, HÃY GHI RÕ: "Cuộc trò chuyện chủ yếu là trò chuyện phiếm, chia sẻ quan điểm cá nhân và trêu đùa giữa các thành viên, không có quyết định hoặc công việc quan trọng nào được chốt lại."

            Dữ liệu trò chuyện (mốc thời gian Việt Nam [Thứ Ngày/Tháng Giờ:Phút]):
            \"\"\"
            {chat_history_text}
            \"\"\"
            """
        else:
            prompt = f"""
            Bạn là một trợ lý ảo quản lý cộng đồng Discord chuyên nghiệp, tinh tế.
            Dưới đây là lịch sử trò chuyện của một nhóm chat ({scan_info}).
            Hãy tóm tắt lại nội dung cuộc trò chuyện này một cách NGẮN GỌN, SÚC TÍCH, MẠCH LẠC và DỄ HIỂU nhất bằng Tiếng Việt.

            {focus_instruction}

            🚨 QUY TẮC TUYỆT ĐỐI - CHỐNG ẢO GIÁC (ANTI-HALLUCINATION) - VI PHẠM = THẤT BẠI HOÀN TOÀN:
            - CHỈ được phép tóm tắt các nội dung THỰC SỰ có trong văn bản đầu vào. TUYỆT ĐỐI KHÔNG thêm thông tin ngoài dữ liệu.

            🧠 NGUYÊN TẮC TÓM TẮT:
            - Tường thuật ngắn gọn, mượt mà theo diễn biến câu chuyện, nêu rõ chi tiết/lý do cốt lõi, lọc bỏ tán gẫu vụn vặt.
            - Hiểu đúng ngữ cảnh đùa cợt, cà khịa, châm biếm thay vì hiểu nghĩa đen cứng nhắc.
            - Bọc 100% tên thành viên trong dấu backtick `Tên` (tuyệt đối không dùng @ và không để sót ID mention).
            - Không chứa lời chào hay kết luận xã giao. Đi thẳng vào nội dung.
            - Giữ độ dài dưới 1000 ký tự.
            - Tóm tắt các chủ đề chính dưới dạng các gạch đầu dòng ngắn gọn kèm kết luận/quyết định thực tế (nếu có).

            Dữ liệu trò chuyện (mốc thời gian Việt Nam [Thứ Ngày/Tháng Giờ:Phút]):
            \"\"\"
            {chat_history_text}
            \"\"\"
            """

        response = await asyncio.to_thread(
            get_ai_client().models.generate_content,
            model=config.GEMINI_SUMMARY_MODEL,
            contents=prompt,
            config=SUMMARY_CONFIG,
        )
        return response.text

    else:
        # Bắt đầu MapReduce
        print(f"🧠 [MapReduce] Nhận thấy có {len(raw_messages)} tin nhắn (>{config.SINGLE_PASS_MSG_LIMIT}). Chia làm nhiều phần để phân tích song song (Model: {getattr(config, 'GEMINI_DATA_MODEL', config.GEMINI_SUMMARY_MODEL)} & {config.GEMINI_SUMMARY_MODEL})...", flush=True)
        chunk_size = getattr(config, "MAPREDUCE_CHUNK_SIZE", 200)
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
            Bạn là một trợ lý ảo quản lý cộng đồng Discord thông minh, sâu sắc, tinh tế và chuyên nghiệp.
            Dưới đây là tổng hợp các bản tóm tắt phân đoạn từ lịch sử trò chuyện của một nhóm chat kéo dài trong thời gian qua.
            Hãy kết hợp chúng thành một bản tóm tắt toàn diện, CHI TIẾT, GIÀU DỮ KIỆN, ĐẦY ĐỦ, MẠCH LẠC và THÔNG MINH nhất bằng Tiếng Việt.

            {focus_instruction}

            🚨 QUY TẮC TUYỆT ĐỐI - CHỐNG ẢO GIÁC (ANTI-HALLUCINATION) - VI PHẠM = THẤT BẠI HOÀN TOÀN:
            - CHỈ được phép tổng hợp lại nội dung từ các bản tóm tắt phân đoạn được cung cấp ở dưới.
            - TUYỆT ĐỐI KHÔNG thêm nội dung mới, ngày tháng mới, sự kiện mới hay tên người dùng mới không có trong các bản tóm tắt đầu vào.
            - Chỉ các ngày, giờ và tên người dùng xuất hiện trong các tóm tắt phân đoạn mới được phép đưa vào bản tổng hợp cuối.

            🧠 NGUYÊN TẮC TỔNG HỢP THÔNG MINH & GIÀU DỮ KIỆN (SMART & SUBSTANTIVE SYNTHESIS):
            1. **GỠ RỐI HỘI THOẠI SONG SONG**: Tách bạch các chủ đề diễn ra cùng lúc, không trộn lẫn ngữ cảnh.
            2. **GIÀU DỮ KIỆN, LÝ DO & QUAN ĐIỂM CỤ THỂ**: Nêu rõ ai nói gì, lý do/quan điểm cụ thể, chi tiết cốt lõi của cuộc trò chuyện để người đọc hiểu trọn vẹn mà không cần đọc lại tin nhắn gốc.
            3. **PHÂN BIỆT ĐÙA CỢT, NÓI KHÁY & TỪ NGỮ CÔNG SỞ MỈA MAI (BANTER & SARCASM DETECTION)**:
               - Hiểu đúng ngầm ý các màn trêu đùa, cà khịa, dùng từ công sở châm biếm ("viết ticket gửi BA PM", "ngon vô code", "cán bộ").
               - Tuyệt đối KHÔNG biến các câu đùa thành quyết định công việc chính thức trong phần kết luận.
            4. **BỌC 100% TÊN THÀNH VIÊN TRONG DẤU BACKTICK**: Luôn dùng `Tên` (ví dụ: `Vũ Lưu`, `Tuan🐤`, `129600`, `jun`, `Poop`, `Miraei`). Tuyệt đối KHÔNG dùng ký tự `@`, không để sót ID mention `<@...>` và KHÔNG liệt kê danh sách tên thô ở đầu mốc thời gian.

            📐 BỐ CỤC BÀI VIẾT (BẮT BUỘC TUÂN THỦ):
            - TUYỆT ĐỐI KHÔNG chứa lời chào, lời mở đầu hay lời kết xã giao. Đi thẳng vào nội dung.
            - ĐỘ DÀI BÀI VIẾT: Dưới 3500 ký tự. Viết cô đọng, súc tích, tránh lặp ý.
            - CẤU TRÚC:
              1. **TỔNG QUAN CHỦ ĐỀ**: Tóm tắt tổng thể các chủ đề chính đã thảo luận trong suốt toàn bộ cuộc trò chuyện và không khí chung. (Không liệt kê danh sách thành viên trong ngoặc đơn ở đầu bài).
              2. **TIMELINE DIỄN BIẾN**:
                 - **SẮP XẾP THỜI GIAN XUÔI (CHRONOLOGICAL: TỪ CŨ NHẤT ĐẾN MỚI NHẤT)**:
                   - Thứ tự ngày: Bắt đầu từ ngày cũ nhất và tiến dần đến ngày mới nhất (ví dụ: `### 📅 T7, 23/08` trước, sau đó mới đến `### 📅 CN, 24/08`).
                   - Thứ tự mốc giờ trong từng ngày: Bắt đầu từ mốc giờ sớm nhất đến mốc giờ muộn nhất (ví dụ: `16:13` ➔ `17:05` ➔ `19:08` ➔ `21:40` ➔ `23:19` ➔ `23:54`... sang ngày mới: `00:05` ➔ `00:13` ➔ `00:26` ➔ `00:39`).
                 - **PHÂN CHIA THEO NGÀY (KÈM THỨ) & RANH GIỚI NỬA ĐÊM**:
                   - Tiêu đề mỗi ngày (CÓ KÈM THỨ TRONG TUẦN): `### 📅 [Thứ], DD/MM` (Ví dụ: `### 📅 T7, 23/08`, `### 📅 CN, 24/08`, `### 📅 T2, 25/08`...).
                   - GIỮA CÁC NGÀY KHÁC NHAU: Phải có một dòng kẻ ngang markdown `---`.
                   - Ranh giới ngày chuẩn xác: Mọi tin nhắn từ `00:00` đến `23:59` của ngày nào BẮT BUỘC phải nằm trọn vẹn dưới tiêu đề của ngày đó. Không được để lẫn tin nhắn 23:xx sang ngày hôm sau.
                 - **GỘP & TỔNG HỢP TIMELINE THÔNG MINH**:
                   - Hợp nhất các mốc thời gian từ các phân đoạn thành các mốc thảo luận lớn, liền mạch, giàu dữ kiện và có ý nghĩa.
                   - Nếu là khoảng thời gian: `• [Giờ_bắt_đầu - Giờ_kết_thúc] **Chủ đề chính ngắn gọn**: Nội dung tường thuật giàu dữ kiện, lý do và quan điểm cụ thể, bọc 100% tên thành viên trong `Tên`.`
                   - Nếu là mốc/tin nhắn đơn lẻ (cùng phút): CHỈ ghi `• [HH:MM] **Chủ đề**: ...` (tuyệt đối không ghi `[HH:MM - HH:MM]`).
                   - Ví dụ đúng: `• [23:19 - 23:58] **Hoàn thành bài tập & Đánh giá công cụ làm việc**: `Regiko` thông báo đã hoàn thành slide phản biện và được `129600` khích lệ. `Vũ Lưu`, `Tuan🐤` và `fearsofevil` cùng thảo luận, so sánh các nền tảng công việc, trong đó chê bai sự nặng nề của Slack và sự bất tiện của Zalo, đồng thời ca ngợi Discord là chân ái để làm việc và chill.`
              3. **KẾT LUẬN & QUYẾT ĐỊNH**:
                 - CHỈ ghi nhận các quyết định, thống nhất, lịch hẹn hoặc dự định THỰC TẾ.
                 - Nếu toàn bộ cuộc trò chuyện chỉ là trò chuyện phiếm, đùa giỡn, cà khịa hoặc tâm sự mà KHÔNG có quyết định thực tế nào được chốt lại, HÃY GHI RÕ: "Cuộc trò chuyện chủ yếu là trò chuyện phiếm, chia sẻ quan điểm cá nhân và trêu đùa giữa các thành viên, không có quyết định hoặc công việc quan trọng nào được chốt lại."

            Dữ liệu tóm tắt phân đoạn:
            \"\"\"
            {intermediate_summaries}
            \"\"\"
            """
        else:
            reduce_prompt = f"""
            Bạn là một trợ lý ảo quản lý cộng đồng Discord chuyên nghiệp.
            Dưới đây là tổng hợp các bản tóm tắt phân đoạn từ lịch sử trò chuyện của một nhóm chat.
            Hãy kết hợp chúng thành một bản tóm tắt NGẮN GỌN, SÚC TÍCH, MẠCH LẠC và DỄ HIỂU nhất bằng Tiếng Việt.

            {focus_instruction}

            🚨 QUY TẮC TUYỆT ĐỐI - CHỐNG ẢO GIÁC: CHỈ tổng hợp nội dung từ các tóm tắt phân đoạn được cung cấp. KHÔNG thêm bất kỳ thông tin mới nào.

            🧠 NGUYÊN TẮC TÓM TẮT:
            - Tường thuật ngắn gọn, mượt mà theo diễn biến câu chuyện, nêu rõ chi tiết/lý do cốt lõi, lọc bỏ tán gẫu vụn vặt.
            - Bọc 100% tên thành viên trong dấu backtick `Tên` (tuyệt đối không dùng @).
            - Không chứa lời chào hay kết luận xã giao. Đi thẳng vào nội dung.
            - Giữ độ dài dưới 1000 ký tự.
            - Tóm tắt các chủ đề chính dưới dạng các gạch đầu dòng ngắn gọn kèm kết luận/quyết định (nếu có).

            Dữ liệu tóm tắt phân đoạn:
            \"\"\"
            {intermediate_summaries}
            \"\"\"
            """
        response = await asyncio.to_thread(
            get_ai_client().models.generate_content,
            model=config.GEMINI_SUMMARY_MODEL,
            contents=reduce_prompt,
            config=SUMMARY_CONFIG,
        )
        print("✅ [MapReduce] Pha Reduce hoàn tất thành công.", flush=True)
        return response.text


MOCK_CHAT_HISTORY = [
    "[T6 13/06 09:15] Miraei: Chào mọi người, hôm nay chúng ta bàn về dự án bot nhé.",
    "[T6 13/06 09:17] Tuan🐤: Ok, bot hiện tại đang chạy tốt nhưng tôi thấy hình như nếu quét dài quá nó chỉ lấy được ngày cũ nhất thôi.",
    "[T6 13/06 09:18] Miraei: Đúng rồi, đó là do discord history query sử dụng after=start_time_utc, nó bị giới hạn ở 300 tin đầu tiên tính từ ngày cũ. Để tôi sửa lại.",
    "[T6 13/06 09:20] FearsOfEvil: Nên tách code ra nữa Miraei ơi, app.py giờ phình to hơn 1000 dòng rồi, khó đọc lắm.",
    "[T6 13/06 09:22] Miraei: Đồng ý. Tôi sẽ tách thành config, bot_instance, ai_service, và web_dashboard.",
    "[T6 13/06 10:05] jun: Mọi người ơi có ai làm bài Lab 10 môn Machine Learning của thầy Dũ chưa?",
    "[T6 13/06 10:08] Mizu: Bài đó chia 10 dataset theo số cuối MSSV đúng không? Hạn nộp là 1 tuần nữa.",
    "[T6 13/06 10:10] jun: Đúng rồi lo quá, phần này tôi chưa hiểu thuật toán lắm.",
    "[T6 13/06 15:30] Poop: Có ai làm ván ARAM LoL không? Lên đồ Velkoz kiểu mới vui cực.",
    "[T6 13/06 15:32] jun: Đi ông ơi, đợi tôi mở máy.",
    "[T6 13/06 15:35] Poop: Ok vào game thôi."
]


async def evaluate_summary(raw_history_text, generated_summary, summary_type, clean_focus):
    eval_prompt = f"""
    Bạn là một kỹ sư đảm bảo chất lượng AI (AI QA Engineer) khó tính.
    Nhiệm vụ của bạn là đánh giá và chấm điểm một bản tóm tắt được tạo bởi một AI Summary Bot từ lịch sử trò chuyện Discord.

    Dưới đây là cấu hình quét:
    - Kiểu tóm tắt: {summary_type}
    - Chủ đề tập trung (Focus): {clean_focus or "Không có"}

    Lịch sử trò chuyện gốc:
    \"\"\"
    {raw_history_text[:4000]} (đã lược bớt nếu quá dài)
    \"\"\"

    Bản tóm tắt cần đánh giá:
    \"\"\"
    {generated_summary}
    \"\"\"

    Hãy kiểm tra nghiêm ngặt bản tóm tắt dựa trên các tiêu chí sau:
    1. **Lời mở đầu & Lời kết rườm rà (Fluff Check)**: Bản tóm tắt có chứa các câu xã giao, chào hỏi hoặc dẫn dắt thừa thãi ở đầu hoặc cuối không? (Quy định là phải đi thẳng vào nội dung).
    2. **Định dạng Timeline & Thứ tự thời gian (Chronology & Timeline Check)**:
       - Có sắp xếp theo thứ tự thời gian XUÔI (từ cũ nhất đến mới nhất, cả về ngày lẫn mốc giờ trong ngày) không?
       - Có phân chia theo ngày dạng `### 📅 NGÀY DD/MM` và ngăn cách giữa các ngày bằng `---` không?
       - Mốc thời gian gạch đầu dòng có đúng dạng `• [HH:MM - HH:MM] **Chủ đề**:` (không bị thừa ngày ở mốc giờ) không?
       - Ranh giới giữa các ngày có chuẩn xác (không bị lẫn lộn mốc giờ 23:xx của ngày cũ vào ngày mới) không?
    3. **Thẩm mỹ & Hiển thị Tên người dùng (Aesthetics & User Tag Check)**:
       - Tên người dùng có được bọc trong dấu backtick `Tên` để làm nổi bật tinh tế không?
       - Có bị spam ký tự `@` hoặc bị liệt kê một tràng danh sách tên người dùng ở đầu mốc thời gian không? (Quy định là tuyệt đối KHÔNG dùng `@` và KHÔNG liệt kê danh sách tên thô).
    4. **Chất lượng nội dung & Gỡ rối ngữ cảnh (Smart Synthesis & Disentanglement Check)**:
       - AI có hiểu và tách rõ các mạch hội thoại song song, gỡ rối ngữ cảnh thông minh không, hay bị trộn lẫn (blend context) các câu chuyện vào nhau?
       - Lối hành văn có tường thuật mạch lạc, cô đọng câu chuyện không, hay chỉ chép lại máy móc từng tin nhắn?
       - Nếu có chủ đề Focus, bản tóm tắt có tập trung cao độ vào chủ đề đó không?
    5. **Độ dài & Trực quan (Length & Readability Check)**: Bản tóm tắt có quá dài (vượt 3500 ký tự) hay khó đọc không?

    Định dạng báo cáo đánh giá của bạn (BẮT BUỘC bằng Tiếng Việt, định dạng Markdown):
    ### 📊 BÁO CÁO ĐÁNH GIÁ CHẤT LƯỢNG TÓM TẮT
    - **Điểm số**: [Chấm điểm từ 1 đến 10]
    - **Fluff Check**: [ĐẠT / KHÔNG ĐẠT - Lý do ngắn gọn]
    - **Chronology & Timeline Check**: [ĐẠT / KHÔNG ĐẠT - Lý do ngắn gọn]
    - **User Tag & Aesthetics Check**: [ĐẠT / KHÔNG ĐẠT - Lý do ngắn gọn]
    - **Smart Synthesis & Focus Check**: [ĐẠT / KHÔNG ĐẠT / KHÔNG ÁP DỤNG - Lý do ngắn gọn]

    #### 📝 Chi tiết đánh giá:
    - [Ghi chú chi tiết về những điểm tốt]
    - [Ghi chú chi tiết về những điểm lỗi hoặc chưa tốt]

    #### 💡 Đề xuất cải tiến cụ thể:
    - [Gợi ý cải tiến cụ thể cho AI để cấu hình prompt khôn hơn hoặc xử lý tốt hơn]
    """

    try:
        response = await asyncio.to_thread(
            get_ai_client().models.generate_content,
            model=config.GEMINI_QA_MODEL,
            contents=eval_prompt,
            config=QA_CONFIG,
        )
        return response.text
    except Exception as e:
        print(f"❌ [AI Critique] Lỗi khi đánh giá bản tóm tắt: {e}", flush=True)
        return f"### 📊 BÁO CÁO ĐÁNH GIÁ CHẤT LƯỢNG TÓM TẮT\n- **Điểm số**: N/A\n- **Lỗi hệ thống**: Không thể đánh giá do lỗi gọi API: {e}"
