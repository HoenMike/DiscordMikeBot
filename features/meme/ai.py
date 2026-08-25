import json
import re
import aiohttp
from typing import List, Dict, Optional, Any
from core.ai import get_ai_client
import config

EMBEDDING_MODEL = "gemini-embedding-001"
MEME_FALLBACK_MODELS = [
    getattr(config, "GEMINI_MEME_MODEL", "gemini-3.6-flash"),
    "gemini-3.6-flash",
    "gemini-3.5-flash",
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
]


class MemeAI:
    """Xử lý Trí Tuệ Nhân Tạo cho Meme: Sinh Vector Embedding, Phân Tích Ngữ Cảnh & Vision LLM."""

    @staticmethod
    async def get_embedding(text: str) -> List[float]:
        """Tạo vector embedding (3072 chiều) từ chuỗi văn bản sử dụng Gemini Embedding."""
        try:
            client = get_ai_client()
            clean_text = text.strip()
            if not clean_text:
                return []
            response = client.models.embed_content(
                model=EMBEDDING_MODEL,
                contents=clean_text
            )
            if response and response.embeddings:
                return list(response.embeddings[0].values)
            return []
        except Exception as e:
            print(f"[MemeAI] Lỗi khi sinh vector embedding: {e}", flush=True)
            return []

    @staticmethod
    async def reason_meme_context(prompt: str, chat_context: Optional[str] = None) -> Dict[str, Any]:
        """
        Phân tích sâu ngữ cảnh, cảm xúc, tiếng lóng, sắc thái văn hóa (Việt Nam & Quốc Tế)
        để chọn ra mẫu meme chuẩn vibe nhất cùng từ khóa tìm kiếm và caption hài hước.
        """
        client = get_ai_client()

        system_instruction = (
            "Bạn là 'Meme Master' & Chuyên gia Bách khoa toàn thư Meme Internet (Pop Culture & Meme Researcher).\n"
            "Nhiệm vụ của bạn là đọc yêu cầu, cảm xúc hoặc câu nói của người dùng và chọn ra meme hoặc reaction image/GIF chuẩn xác nhất.\n\n"
            "QUY TẮC QUAN TRỌNG:\n"
            "1. NẾU NGƯỜI DÙNG NHẬP TÊN MEME / SLANG INTERNET NỔI TIẾNG:\n"
            "   (Ví dụ: 'kek', 'kekw', 'pepe', 'gigachad', 'wojak', 'doge', 'cheems', 'bruh', 'facepalm', 'shrek', 'omedetou', 'smug', 'bonk', 'rickroll', 'độ mixi', 'trấn thành', 'meme chê'...)\n"
            "   -> BẮT BUỘC nhận diện chính xác meme gốc đó! KHÔNG ĐƯỢC thay thế bằng meme mèo ngẫu nhiên hay thứ khác.\n"
            "   -> 'matched_meme': Tên chuẩn của meme (VD: 'KEKW / Pepe Laugh' cho 'kek' hoặc 'kekw').\n"
            "   -> 'en_keywords': Từ khóa meme chuẩn quốc tế (VD: 'kekw laughing meme gif', 'pepe kek meme').\n"
            "   -> 'vi_keywords': Luôn thêm chữ 'meme' (VD: 'kekw meme', 'pepe kek meme') để tránh nhầm sang bánh ngọt (kek = cake).\n\n"
            "2. NẾU NGƯỜI DÙNG NHẬP CẢM XÚC / TÌNH HUỐNG / CÂU NÓI:\n"
            "   -> Phân tích sắc thái (vui, buồn, cay đắng, mỉa mai, bất lực, cà khịa...) và chọn meme biểu cảm khớp 100%.\n\n"
            "Hãy trả về định dạng JSON thuần túy (không bọc codeblock):\n"
            "{\n"
            '  "vibe": "Mô tả ngắn cảm xúc cốt lõi",\n'
            '  "matched_meme": "Tên meme hoặc nhân vật nổi tiếng",\n'
            '  "vi_keywords": "Từ khóa tìm kiếm ảnh chế tiếng Việt trên Web (luôn có chữ meme)",\n'
            '  "en_keywords": "Từ khóa tìm kiếm ảnh/GIF quốc tế (luôn có chữ meme hoặc gif)",\n'
            '  "caption": "Một câu caption ngắn gọn, dí dỏm, đúng chất Gen Z / Internet meme"\n'
            "}"
        )

        user_content = f"Yêu cầu / Ngữ cảnh của người dùng: '{prompt}'"
        if chat_context:
            user_content += f"\nNgữ cảnh tin nhắn trong kênh chat: '{chat_context}'"

        last_error = None
        for model_name in MEME_FALLBACK_MODELS:
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=user_content,
                    config={
                        "system_instruction": system_instruction,
                        "temperature": 0.4,
                        "response_mime_type": "application/json"
                    }
                )
                raw_text = response.text.strip()
                data = json.loads(raw_text)
                return {
                    "vibe": data.get("vibe", "Hài hước châm biếm"),
                    "matched_meme": data.get("matched_meme", "Reaction Meme"),
                    "vi_keywords": data.get("vi_keywords", f"{prompt} meme"),
                    "en_keywords": data.get("en_keywords", f"{prompt} meme gif"),
                    "caption": data.get("caption", f"Tâm trạng lúc này: {prompt}")
                }
            except Exception as e:
                last_error = e
                continue

        print(f"[MemeAI] Tất cả model phân tích thất bại: {last_error}", flush=True)
        return {
            "vibe": "Hài hước",
            "matched_meme": prompt,
            "vi_keywords": f"{prompt} meme",
            "en_keywords": f"{prompt} meme gif",
            "caption": f"💡 {prompt}"
        }

    @staticmethod
    async def analyze_image_with_vision(image_url: str) -> Dict[str, Any]:
        """
        Dùng Gemini Multimodal để tải và phân tích hình ảnh/GIF,
        trích xuất tên meme, cảm xúc, mô tả và các tag để tự động nạp vào Vector DB.
        """
        client = get_ai_client()
        image_bytes = None
        mime_type = "image/jpeg"

        try:
            headers = {"User-Agent": "Mozilla/5.0"}
            async with aiohttp.ClientSession(headers=headers) as session:
                async with session.get(image_url, timeout=10) as resp:
                    if resp.status == 200:
                        image_bytes = await resp.read()
                        content_type = resp.headers.get("Content-Type", "")
                        if "png" in content_type:
                            mime_type = "image/png"
                        elif "gif" in content_type:
                            mime_type = "image/gif"
                        elif "webp" in content_type:
                            mime_type = "image/webp"
        except Exception as download_err:
            print(f"[MemeAI] Không thể tải ảnh để phân tích Vision: {download_err}", flush=True)
            return {
                "title": "Meme người dùng đóng góp",
                "vibe": "Meme hài hước",
                "tags": ["meme", "reaction", "user_upload"],
                "caption": "Meme mới được thêm vào kho!"
            }

        if not image_bytes:
            return {
                "title": "Meme người dùng đóng góp",
                "vibe": "Meme hài hước",
                "tags": ["meme", "reaction", "user_upload"],
                "caption": "Meme mới được thêm vào kho!"
            }

        prompt = (
            "Hãy nhìn vào bức ảnh/meme này và đóng vai trò Chuyên gia phân tích Meme.\n"
            "Trả về JSON định dạng chuẩn (không bọc codeblock):\n"
            "{\n"
            '  "title": "Tên ngắn gọn của meme hoặc nhân vật trong ảnh (ví dụ: Mèo khóc like, Độ Mixi gật gù...)",\n'
            '  "vibe": "Mô tả sắc thái cảm xúc (ví dụ: Đau khổ gượng cười, Tức giận bất lực...)",\n'
            '  "tags": ["danh", "sách", "5_den_8", "tu_khoa", "tieng_viet_va_anh"],\n'
            '  "caption": "Một câu chú thích dí dỏm hợp nhất với biểu cảm trong ảnh"\n'
            "}"
        )

        try:
            from google.genai import types
            part = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
            response = client.models.generate_content(
                model=REASONING_MODEL,
                contents=[part, prompt],
                config={
                    "temperature": 0.2,
                    "response_mime_type": "application/json"
                }
            )
            data = json.loads(response.text.strip())
            return {
                "title": data.get("title", "Ảnh chế Meme"),
                "vibe": data.get("vibe", "Hài hước"),
                "tags": data.get("tags", ["meme", "funny"]),
                "caption": data.get("caption", "Meme được thêm vào kho!")
            }
        except Exception as e:
            print(f"[MemeAI] Lỗi khi chạy Vision AI: {e}", flush=True)
            return {
                "title": "Meme người dùng đóng góp",
                "vibe": "Hài hước",
                "tags": ["meme", "reaction"],
                "caption": "Meme được thêm vào kho!"
            }
