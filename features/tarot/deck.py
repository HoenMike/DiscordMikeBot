import random
import pathlib
import urllib.request
import urllib.parse
from dataclasses import dataclass
from typing import List, Dict, Tuple, Optional

# Thư mục chứa assets của Tarot
TAROT_DIR = pathlib.Path(__file__).parent
ASSETS_DIR = TAROT_DIR / "assets"
CARDS_DIR = ASSETS_DIR / "cards"
CARDS_DIR.mkdir(parents=True, exist_ok=True)

GITHUB_ASSET_BASE_URL = "https://raw.githubusercontent.com/geraldfingburke/plateau-tarot-api/master/images"

@dataclass
class TarotCard:
    id: str
    name_en: str
    name_vi: str
    arcana: str  # "Major", "Wands", "Cups", "Swords", "Pentacles"
    number: int
    yes_no_affinity: str  # "YES", "NO", "MAYBE"
    keywords_upright: List[str]
    keywords_reversed: List[str]
    description: str
    image_filename: str

    @property
    def local_image_path(self) -> pathlib.Path:
        return CARDS_DIR / self.image_filename


@dataclass
class DrawnCard:
    card: TarotCard
    is_reversed: bool
    position_index: int
    position_title: str
    position_description: str

    @property
    def orientation_str(self) -> str:
        return "Ngược (Reversed)" if self.is_reversed else "Xuôi (Upright)"

    @property
    def display_name(self) -> str:
        tag = "[NGƯỢC]" if self.is_reversed else "[XUÔI]"
        return f"{self.card.name_vi} ({self.card.name_en}) - {tag}"

    @property
    def current_keywords(self) -> List[str]:
        return self.card.keywords_reversed if self.is_reversed else self.card.keywords_upright


# Định nghĩa 78 lá bài Rider-Waite chuẩn
TAROT_DECK: Dict[str, TarotCard] = {
    # =========================================================================
    # 22 LÁ MAJOR ARCANA (ĐẠI ẨN SỐ)
    # =========================================================================
    "major_00": TarotCard(
        id="major_00",
        name_en="The Fool",
        name_vi="Chàng Khờ",
        arcana="Major",
        number=0,
        yes_no_affinity="YES",
        keywords_upright=["Khởi đầu mới", "Sự ngây thơ", "Tự do", "Phiêu lưu mạo hiểm", "Niềm tin"],
        keywords_reversed=["Liều lĩnh", "Bất cẩn", "Ngây ngô mù quáng", "Do dự", "Rủi ro"],
        description="Đại diện cho khởi đầu của một hành trình mới, sự dũng cảm bước vào những điều chưa biết với trái tim thuần khiết.",
        image_filename="The Fool.jpg"
    ),
    "major_01": TarotCard(
        id="major_01",
        name_en="The Magician",
        name_vi="Pháp Sư",
        arcana="Major",
        number=1,
        yes_no_affinity="YES",
        keywords_upright=["Kỹ năng", "Tập trung", "Ý chí mạnh mẽ", "Khả năng sáng tạo", "Hiện thực hóa"],
        keywords_reversed=["Thao túng", "Lãng phí tài năng", "Thiếu kế hoạch", "Ảo tưởng"],
        description="Biểu trưng cho sức mạnh biến ý tưởng thành hiện thực nhờ hội tụ đủ 4 yếu tố và nguồn lực dồi dào.",
        image_filename="The Magician.jpg"
    ),
    "major_02": TarotCard(
        id="major_02",
        name_en="The High Priestess",
        name_vi="Nữ Tư Tế",
        arcana="Major",
        number=2,
        yes_no_affinity="MAYBE",
        keywords_upright=["Trực giác", "Bí ẩn", "Tiềm thức", "Sự tĩnh lặng", "Tri thức nội tâm"],
        keywords_reversed=["Bí mật bị giấu kín", "Bỏ qua trực giác", "Bề ngoài hời hợt", "Cảm xúc dồn nén"],
        description="Đại diện cho tiếng nói trực giác bên trong và sự thấu hiểu các bí ẩn chưa được hé lộ.",
        image_filename="The High Priestess.jpg"
    ),
    "major_03": TarotCard(
        id="major_03",
        name_en="The Empress",
        name_vi="Hoàng Hậu",
        arcana="Major",
        number=3,
        yes_no_affinity="YES",
        keywords_upright=["Phì nhiêu", "Nuôi dưỡng", "Sung túc", "Sáng tạo nghệ thuật", "Tình mẫu tử"],
        keywords_reversed=["Phụ thuộc", "Khô khan sáng tạo", "Bỏ bê bản thân", "Kiểm soát quá mức"],
        description="Biểu tượng của tình yêu thương, sự trù phú của đất mẹ và khả năng nuôi dưỡng mọi hạt mầm phát triển.",
        image_filename="The Empress.jpg"
    ),
    "major_04": TarotCard(
        id="major_04",
        name_en="The Emperor",
        name_vi="Hoàng Đế",
        arcana="Major",
        number=4,
        yes_no_affinity="YES",
        keywords_upright=["Quyền lực", "Kỷ luật", "Cấu trúc vững vàng", "Bảo vệ", "Lãnh đạo"],
        keywords_reversed=["Độc đoán", "Cứng nhắc", "Lạm quyền", "Mất kiểm soát", "Thiếu tổ chức"],
        description="Hiện thân của kỷ cương, ý chí sắt đá, trật tự và năng lực kiến tạo nền tảng vững bền.",
        image_filename="The Emperor.jpg"
    ),
    "major_05": TarotCard(
        id="major_05",
        name_en="The Hierophant",
        name_vi="Giáo Hoàng",
        arcana="Major",
        number=5,
        yes_no_affinity="MAYBE",
        keywords_upright=["Truyền thống", "Quy chuẩn", "Học hỏi", "Lời khuyên đạo đức", "Tổ chức"],
        keywords_reversed=["Phá cách", "Giáo điều hẹp hòi", "Nổi loạn", "Tự tìm con đường riêng"],
        description="Đại diện cho tri thức truyền thống, niềm tin tâm linh và sự chỉ dẫn từ những người thầy uyên bác.",
        image_filename="The Hierophant.jpg"
    ),
    "major_06": TarotCard(
        id="major_06",
        name_en="The Lovers",
        name_vi="Tình Nhân",
        arcana="Major",
        number=6,
        yes_no_affinity="YES",
        keywords_upright=["Tình yêu", "Sự hòa hợp", "Lựa chọn từ trái tim", "Đồng điệu", "Gắn kết"],
        keywords_reversed=["Bất hòa", "Lựa chọn sai lầm", "Mất kết nối", "Xung đột giá trị"],
        description="Biểu thị sự hòa hợp thiêng liêng giữa hai tâm hồn và những quyết định đạo đức xuất phát từ trái tim.",
        image_filename="The Lovers.jpg"
    ),
    "major_07": TarotCard(
        id="major_07",
        name_en="The Chariot",
        name_vi="Cỗ Xe Chiến Thắng",
        arcana="Major",
        number=7,
        yes_no_affinity="YES",
        keywords_upright=["Chiến thắng", "Ý chí kiên định", "Tiến lên", "Kiểm soát hướng đi", "Vượt chướng ngại"],
        keywords_reversed=["Mất phương hướng", "Hung hăng", "Thiếu kiềm chế", "Bế tắc"],
        description="Thông điệp về sự làm chủ bản thân, dũng cảm tiến lên vượt qua nghịch cảnh để chinh phục mục tiêu.",
        image_filename="The Chariot.jpg"
    ),
    "major_08": TarotCard(
        id="major_08",
        name_en="Strength",
        name_vi="Sức Mạnh",
        arcana="Major",
        number=8,
        yes_no_affinity="YES",
        keywords_upright=["Dũng cảm", "Kiên nhẫn", "Tâm thế từ bi", "Làm chủ thú tính", "Sức mạnh nội tâm"],
        keywords_reversed=["Tự ti", "Mất kiên nhẫn", "Bị cảm xúc chi phối", "Yếu lòng"],
        description="Sức mạnh đích thực không đến từ bạo lực mà đến từ sự nhẫn nại, lòng trắc ẩn và bản lĩnh kiểm soát nội tâm.",
        image_filename="Strength.jpg"
    ),
    "major_09": TarotCard(
        id="major_09",
        name_en="The Hermit",
        name_vi="Ẩn Sĩ",
        arcana="Major",
        number=9,
        yes_no_affinity="MAYBE",
        keywords_upright=["Chiêm nghiệm", "Tìm kiếm chân lý", "Tĩnh tâm", "Tự vấn", "Ngọn đèn dẫn lối"],
        keywords_reversed=["Cô lập quá mức", "Lạc lõng", "Từ chối lời khuyên", "Chối bỏ thực tế"],
        description="Thời điểm lùi lại khỏi ồn ào thế tục để nhìn sâu vào tâm hồn và tìm kiếm câu trả lời đích thực.",
        image_filename="The Hermit.jpg"
    ),
    "major_10": TarotCard(
        id="major_10",
        name_en="Wheel of Fortune",
        name_vi="Bánh Xe Số Phận",
        arcana="Major",
        number=10,
        yes_no_affinity="YES",
        keywords_upright=["May mắn", "Bước ngoặt định mệnh", "Chu kỳ thay đổi", "Thời cơ", "Nghiệp quả tốt"],
        keywords_reversed=["Xui xẻo tạm thời", "Chống lại thay đổi", "Chu kỳ tiêu cực lặp lại"],
        description="Cuộc sống luôn vận hành theo những vòng xoay biến đổi. Một bước ngoặt quan trọng đang mở ra.",
        image_filename="The Wheel of Fortune.jpg"
    ),
    "major_11": TarotCard(
        id="major_11",
        name_en="Justice",
        name_vi="Công Lý",
        arcana="Major",
        number=11,
        yes_no_affinity="MAYBE",
        keywords_upright=["Công bằng", "Sự thật", "Nhân quả", "Quyết định sáng suốt", "Minh bạch"],
        keywords_reversed=["Bất công", "Thiên vị", "Trốn tránh trách nhiệm", "Định kiến"],
        description="Mọi hành động đều mang lại kết quả tương xứng. Cân nhắc khách quan và tôn trọng lẽ phải.",
        image_filename="Justice.jpg"
    ),
    "major_12": TarotCard(
        id="major_12",
        name_en="The Hanged Man",
        name_vi="Kẻ Treo Ngược",
        arcana="Major",
        number=12,
        yes_no_affinity="MAYBE",
        keywords_upright=["Đổi góc nhìn", "Chấp nhận buông bỏ", "Tạm dừng", "Hy sinh có ý nghĩa"],
        keywords_reversed=["Trì trệ vô ích", "Cố chấp hy sinh mù quáng", "Kháng cự bài học"],
        description="Sự thông thái khi biết dừng lại, buông bỏ sự kiểm soát để nhìn nhận vấn đề dưới góc độ hoàn toàn mới.",
        image_filename="The Hanged Man.jpg"
    ),
    "major_13": TarotCard(
        id="major_13",
        name_en="Death",
        name_vi="Tử Thần",
        arcana="Major",
        number=13,
        yes_no_affinity="NO",
        keywords_upright=["Kết thúc giai đoạn cũ", "Tái sinh", "Chuyển hóa triệt để", "Buông bỏ quá khứ"],
        keywords_reversed=["Sợ hãi thay đổi", "Níu kéo quá khứ", "Chần chừ tái sinh"],
        description="Không mang nghĩa chết chóc vật lý, mà là sự khép lại một chương cũ để mở ra khởi đầu mới rực rỡ hơn.",
        image_filename="Death.jpg"
    ),
    "major_14": TarotCard(
        id="major_14",
        name_en="Temperance",
        name_vi="Tiết Chế",
        arcana="Major",
        number=14,
        yes_no_affinity="YES",
        keywords_upright=["Cân bằng", "Hài hòa", "Kiên nhẫn", "Chữa lành", "Trung dung"],
        keywords_reversed=["Mất cân bằng", "Cực đoan", "Bốc đồng", "Xung đột nội tại"],
        description="Nghệ thuật dung hòa các dòng chảy đối lập để tạo nên sự hòa quyện và bình an bền vững.",
        image_filename="Temperance.jpg"
    ),
    "major_15": TarotCard(
        id="major_15",
        name_en="The Devil",
        name_vi="Ác Quỷ",
        arcana="Major",
        number=15,
        yes_no_affinity="NO",
        keywords_upright=["Ràng buộc", "Cám dỗ", "Nghiện ngập", "Ảo tưởng kiểm soát", "Vật chất ám ảnh"],
        keywords_reversed=["Thoát khỏi trói buộc", "Nhận ra sự thật", "Lấy lại tự do", "Giải phóng"],
        description="Cảnh báo về những xiềng xích vô hình do chính nỗi sợ, dục vọng hoặc thói quen xấu tạo nên.",
        image_filename="The Devil.jpg"
    ),
    "major_16": TarotCard(
        id="major_16",
        name_en="The Tower",
        name_vi="Tòa Tháp Đổ",
        arcana="Major",
        number=16,
        yes_no_affinity="NO",
        keywords_upright=["Biến cố đột ngột", "Sụp đổ ảo tưởng", "Thức tỉnh đau đớn", "Giải phóng hỗn loạn"],
        keywords_reversed=["Tránh được tai họa", "Kéo dài sự chịu đựng", "Sợ hãi tái thiết"],
        description="Cú sét đánh sụp đổ những nền móng giả tạo để xây dựng lại cuộc sống trên chân lý vững chắc.",
        image_filename="The Tower.jpg"
    ),
    "major_17": TarotCard(
        id="major_17",
        name_en="The Star",
        name_vi="Ngôi Sao",
        arcana="Major",
        number=17,
        yes_no_affinity="YES",
        keywords_upright=["Hy vọng", "Niềm tin", "Chữa lành tâm hồn", "Cảm hứng", "Bình yên"],
        keywords_reversed=["Tuyệt vọng", "Mất niềm tin", "Hoài nghi bản thân", "Tắt cảm hứng"],
        description="Ánh sáng hi vọng lấp lánh soi đường sau giông bão, mang đến sự thanh thản và niềm lạc quan vô tận.",
        image_filename="The Star.jpg"
    ),
    "major_18": TarotCard(
        id="major_18",
        name_en="The Moon",
        name_vi="Mặt Trăng",
        arcana="Major",
        number=18,
        yes_no_affinity="NO",
        keywords_upright=["Hoang mang", "Ảo ảnh", "Nỗi sợ tiềm thức", "Mơ hồ", "Trực giác nhạy bén"],
        keywords_reversed=["Sự thật phơi bày", "Vượt qua sợ hãi", "Sáng tỏ", "Bớt lo âu"],
        description="Màn đêm mờ ảo của tâm trí nơi nỗi sợ và ảo ảnh dễ làm ta lạc lối. Hãy bước đi cẩn trọng.",
        image_filename="The Moon.jpg"
    ),
    "major_19": TarotCard(
        id="major_19",
        name_en="The Sun",
        name_vi="Mặt Trời",
        arcana="Major",
        number=19,
        yes_no_affinity="YES",
        keywords_upright=["Hạnh phúc rạng rỡ", "Thành công", "Năng lượng tích cực", "Sức sống", "Rõ ràng"],
        keywords_reversed=["U ám tạm thời", "Lạc quan thái quá", "Hơi muộn màng nhưng vẫn tốt"],
        description="Lá bài mang năng lượng rạng rỡ, may mắn và thành công trọn vẹn nhất trong toàn bộ bộ bài.",
        image_filename="The Sun.jpg"
    ),
    "major_20": TarotCard(
        id="major_20",
        name_en="Judgement",
        name_vi="Phán Xét",
        arcana="Major",
        number=20,
        yes_no_affinity="YES",
        keywords_upright=["Tiếng gọi thức tỉnh", "Tái sinh", "Phán quyết sáng suốt", "Tha thứ", "Bước lên tầm cao mới"],
        keywords_reversed=["Tự phán xét khắt khe", "Do dự trước cơ hội", "Từ chối lắng nghe tiếng gọi"],
        description="Tiếng kèn thức tỉnh lương tri, thôi thúc bạn gạt bỏ quá khứ để bước vào một sứ mệnh lớn lao hơn.",
        image_filename="Judgement.jpg"
    ),
    "major_21": TarotCard(
        id="major_21",
        name_en="The World",
        name_vi="Thế Giới",
        arcana="Major",
        number=21,
        yes_no_affinity="YES",
        keywords_upright=["Viên mãn", "Hoàn thành trọn vẹn", "Đạt mục tiêu", "Hòa hợp toàn vẹn", "Hành trình mới"],
        keywords_reversed=["Chưa hoàn tất", "Thiếu sót cuối cùng", "Trì hoãn cái kết"],
        description="Đỉnh cao của sự thành toàn và viên mãn, khép lại hành trình đầy tự hào để chuẩn bị cho chu kỳ mới.",
        image_filename="The World.jpg"
    ),

    # =========================================================================
    # 56 LÁ MINOR ARCANA (TIỂU ẨN SỐ)
    # =========================================================================
    # 1. SUIT OF WANDS (BỘ GẬY - HỎA)
    # -------------------------------------------------------------------------
    "wands_01": TarotCard(
        id="wands_01", name_en="Ace of Wands", name_vi="1 Gậy", arcana="Wands", number=1, yes_no_affinity="YES",
        keywords_upright=["Cảm hứng dâng trào", "Cơ hội mới", "Tiềm năng sáng tạo", "Nhiệt huyết"],
        keywords_reversed=["Mất cảm hứng", "Trì hoãn", "Thiếu định hướng", "Bế tắc ý tưởng"],
        description="Tia lửa sáng tạo ban đầu mở ra cơ hội hành động tràn đầy sinh lực.",
        image_filename="Ace of Wands.jpg"
    ),
    "wands_02": TarotCard(
        id="wands_02", name_en="Two of Wands", name_vi="2 Gậy", arcana="Wands", number=2, yes_no_affinity="MAYBE",
        keywords_upright=["Lập kế hoạch tương lai", "Tầm nhìn xa", "Đứng trước lựa chọn lớn", "Mở rộng bờ cõi"],
        keywords_reversed=["Sợ bước ra vùng an toàn", "Kế hoạch kém", "Ngại thử thách"],
        description="Đứng trên đỉnh cao ngắm nhìn chân trời và lên kế hoạch cho những bước đi vươn xa.",
        image_filename="Two of Wands.jpg"
    ),
    "wands_03": TarotCard(
        id="wands_03", name_en="Three of Wands", name_vi="3 Gậy", arcana="Wands", number=3, yes_no_affinity="YES",
        keywords_upright=["Mở rộng cơ hội", "Tầm nhìn thành hiện thực", "Hợp tác phát triển", "Đón nhận thành quả"],
        keywords_reversed=["Trì hoãn tiến độ", "Kỳ vọng bất thành", "Trở ngại từ xa"],
        description="Những con thuyền chở ước mơ bắt đầu ra khơi, mở rộng chân trời thành công.",
        image_filename="Three of Wands.jpg"
    ),
    "wands_04": TarotCard(
        id="wands_04", name_en="Four of Wands", name_vi="4 Gậy", arcana="Wands", number=4, yes_no_affinity="YES",
        keywords_upright=["Ăn mừng", "Đoàn tụ", "Mái ấm bình yên", "Cột mốc thành công", "Hòa thuận"],
        keywords_reversed=["Căng thẳng gia đình", "Lễ kỷ niệm bị hủy", "Bất ổn nơi ở"],
        description="Lá bài của niềm vui sum vầy, ăn mừng chiến thắng và nền tảng gia đình hạnh phúc.",
        image_filename="Four of Wands.jpg"
    ),
    "wands_05": TarotCard(
        id="wands_05", name_en="Five of Wands", name_vi="5 Gậy", arcana="Wands", number=5, yes_no_affinity="NO",
        keywords_upright=["Cạnh tranh gay gắt", "Bất đồng ý kiến", "Xung đột nhỏ", "Tranh cãi"],
        keywords_reversed=["Tránh né xung đột", "Hòa giải", "Thỏa hiệp", "Hạ nhiệt căng thẳng"],
        description="Sự va chạm quan điểm và cạnh tranh giữa các bên. Cần tìm tiếng nói chung.",
        image_filename="Five of Wands.jpg"
    ),
    "wands_06": TarotCard(
        id="wands_06", name_en="Six of Wands", name_vi="6 Gậy", arcana="Wands", number=6, yes_no_affinity="YES",
        keywords_upright=["Vinh quang", "Được công nhận", "Chiến thắng vang dội", "Tự hào"],
        keywords_reversed=["Kiêu ngạo quá mức", "Thất bại trước công chúng", "Bị xem thường"],
        description="Sự công nhận xứng đáng cho những nỗ lực vượt bậc trước tập thể.",
        image_filename="Six of Wands.jpg"
    ),
    "wands_07": TarotCard(
        id="wands_07", name_en="Seven of Wands", name_vi="7 Gậy", arcana="Wands", number=7, yes_no_affinity="YES",
        keywords_upright=["Bảo vệ lập trường", "Kiên cường chiến đấu", "Vượt trên đối thủ", "Bản lĩnh"],
        keywords_reversed=["Kiệt sức", "Bỏ cuộc", "Bị áp đảo", "Lúng túng phòng thủ"],
        description="Đứng vững trên vị trí cao để bảo vệ thành quả và lý tưởng của mình trước thử thách.",
        image_filename="Seven of Wands.jpg"
    ),
    "wands_08": TarotCard(
        id="wands_08", name_en="Eight of Wands", name_vi="8 Gậy", arcana="Wands", number=8, yes_no_affinity="YES",
        keywords_upright=["Tốc độ nhanh", "Tin tức đến mau", "Tiến triển thần tốc", "Du lịch / Di chuyển"],
        keywords_reversed=["Trì hoãn bất ngờ", "Hấp tấp hỏng việc", "Thông tin sai lệch"],
        description="Dòng chảy sự kiện diễn ra nhanh chóng, mang lại những tin tức và cơ hội cấp bách.",
        image_filename="Eight of Wands.jpg"
    ),
    "wands_09": TarotCard(
        id="wands_09", name_en="Nine of Wands", name_vi="9 Gậy", arcana="Wands", number=9, yes_no_affinity="MAYBE",
        keywords_upright=["Phòng thủ cẩn trọng", "Kiên trì đến cùng", "Kinh nghiệm trận mạc", "Cố gắng chặng cuối"],
        keywords_reversed=["Kiệt sức", "Đa nghi thái quá", "Buông xuôi trước vạch đích"],
        description="Dù mang nhiều vết thương thử thách, bạn chỉ còn cách vạch đích một bước kiên trì cuối cùng.",
        image_filename="Nine of Wands.jpg"
    ),
    "wands_10": TarotCard(
        id="wands_10", name_en="Ten of Wands", name_vi="10 Gậy", arcana="Wands", number=10, yes_no_affinity="NO",
        keywords_upright=["Gánh nặng quá tải", "Áp lực trách nhiệm", "Làm việc quá sức", "Ôm đồm"],
        keywords_reversed=["Buông bớt gánh nặng", "Ủy quyền công việc", "Sụp đổ vì kiệt sức"],
        description="Gánh vác quá nhiều trọng trách một mình. Đã đến lúc học cách chia sẻ hoặc buông bớt.",
        image_filename="Ten of Wands.jpg"
    ),
    "wands_11": TarotCard(
        id="wands_11", name_en="Page of Wands", name_vi="Tiểu Đồng Gậy", arcana="Wands", number=11, yes_no_affinity="YES",
        keywords_upright=["Nhiệt tình", "Ý tưởng mới", "Tin vui sáng tạo", "Tò mò khám phá"],
        keywords_reversed=["Thiếu kiên nhẫn", "Bốc đồng", "Ý tưởng viển vông"],
        description="Tinh thần trẻ trung, hào hứng đón nhận những thông điệp và đam mê mới.",
        image_filename="Page of Wands.jpg"
    ),
    "wands_12": TarotCard(
        id="wands_12", name_en="Knight of Wands", name_vi="Hiệp Sĩ Gậy", arcana="Wands", number=12, yes_no_affinity="YES",
        keywords_upright=["Hành động quyết liệt", "Đam mê mãnh liệt", "Dũng cảm xông pha", "Tự tin"],
        keywords_reversed=["Nóng nảy", "Thiếu suy nghĩ", "Nhanh chán", "Liều mạng"],
        description="Nguồn năng lượng hăng hái lao về phía trước, sẵn sàng chinh phục mọi đỉnh cao.",
        image_filename="Knight of Wands.jpg"
    ),
    "wands_13": TarotCard(
        id="wands_13", name_en="Queen of Wands", name_vi="Hoàng Hậu Gậy", arcana="Wands", number=13, yes_no_affinity="YES",
        keywords_upright=["Quyến rũ", "Tự tin rạng rỡ", "Độc lập", "Truyền cảm hứng", "Thân thiện"],
        keywords_reversed=["Ghen tuông", "Thao túng", "Tự ti", "Nóng tính"],
        description="Người phụ nữ rực rỡ, độc lập, đầy nhiệt huyết và luôn làm chủ cuộc sống.",
        image_filename="Queen of Wands.jpg"
    ),
    "wands_14": TarotCard(
        id="wands_14", name_en="King of Wands", name_vi="Vua Gậy", arcana="Wands", number=14, yes_no_affinity="YES",
        keywords_upright=["Lãnh đạo truyền cảm hứng", "Tầm nhìn lớn", "Quyết đoán", "Bản lĩnh"],
        keywords_reversed=["Độc tài", "Áp đặt", "Bất dung thứ", "Nóng vội"],
        description="Nhà lãnh đạo có tầm nhìn vĩ đại, dám nghĩ dám làm và dẫn dắt tập thể bứt phá.",
        image_filename="King of Wands.jpg"
    ),

    # -------------------------------------------------------------------------
    # 2. SUIT OF CUPS (BỘ LY / CỐC - THỦY)
    # -------------------------------------------------------------------------
    "cups_01": TarotCard(
        id="cups_01", name_en="Ace of Cups", name_vi="1 Ly", arcana="Cups", number=1, yes_no_affinity="YES",
        keywords_upright=["Tình yêu tràn đầy", "Cảm xúc dâng trào", "Mối quan hệ mới", "Chữa lành"],
        keywords_reversed=["Cạn kiệt cảm xúc", "Tổn thương lòng trắc ẩn", "Tình yêu đơn phương"],
        description="Nguồn suối cảm xúc trong trẻo, mở ra một tình yêu hay sự hòa hợp tâm hồn sâu sắc.",
        image_filename="Ace of Cups.jpg"
    ),
    "cups_02": TarotCard(
        id="cups_02", name_en="Two of Cups", name_vi="2 Ly", arcana="Cups", number=2, yes_no_affinity="YES",
        keywords_upright=["Tình yêu đôi lứa", "Kết nối tâm giao", "Hợp tác ăn ý", "Thu hút lẫn nhau"],
        keywords_reversed=["Hiểu lầm", "Rạn nứt tình cảm", "Mất cân bằng mối quan hệ"],
        description="Sự hòa hợp tuyệt đẹp và tôn trọng lẫn nhau giữa hai tâm hồn đồng điệu.",
        image_filename="Two of Cups.jpg"
    ),
    "cups_03": TarotCard(
        id="cups_03", name_en="Three of Cups", name_vi="3 Ly", arcana="Cups", number=3, yes_no_affinity="YES",
        keywords_upright=["Tình bạn thân thiết", "Tiệc tùng ăn mừng", "Cộng đồng hỗ trợ", "Niềm vui sẻ chia"],
        keywords_reversed=["Bị cô lập", "Bạn bè giả tạo", "Ăn chơi trác táng"],
        description="Nâng ly chúc mừng cùng bạn bè thân thiết, tận hưởng sự gắn bó cộng đồng ấm áp.",
        image_filename="Three of Cups.jpg"
    ),
    "cups_04": TarotCard(
        id="cups_04", name_en="Four of Cups", name_vi="4 Ly", arcana="Cups", number=4, yes_no_affinity="NO",
        keywords_upright=["Thờ ơ", "Chán chường", "Bỏ lỡ cơ hội trước mắt", "Thu mình u sầu"],
        keywords_reversed=["Nhận ra cơ hội mới", "Thoát khỏi u uất", "Sẵn sàng đón nhận"],
        description="Quá tập trung vào những nỗi buồn cũ mà bỏ qua món quà quý giá đang trao đến tay.",
        image_filename="Four of Cups.jpg"
    ),
    "cups_05": TarotCard(
        id="cups_05", name_en="Five of Cups", name_vi="5 Ly", arcana="Cups", number=5, yes_no_affinity="NO",
        keywords_upright=["Hối tiếc", "Đau buồn vì mất mát", "Thất vọng tình cảm", "Nhìn về quá khứ"],
        keywords_reversed=["Chấp nhận buông bỏ", "Nhìn thấy 2 chiếc ly còn lại", "Hồi phục vết thương"],
        description="Nỗi buồn khi nhìn những chiếc ly đã đổ, nhưng phía sau vẫn còn những điều quý giá chờ bạn quay lại.",
        image_filename="Five of Cups.jpg"
    ),
    "cups_06": TarotCard(
        id="cups_06", name_en="Six of Cups", name_vi="6 Ly", arcana="Cups", number=6, yes_no_affinity="YES",
        keywords_upright=["Kỷ niệm tuổi thơ", "Gặp lại người xưa", "Sự ngây thơ trong sáng", "Hoài niệm đẹp"],
        keywords_reversed=["Mắc kẹt trong quá khứ", "Không chịu trưởng thành", "Rời xa ảo mộng"],
        description="Ký ức ngọt ngào và sự trao gửi tình cảm thuần khiết như thuở ấu thơ.",
        image_filename="Six of Cups.jpg"
    ),
    "cups_07": TarotCard(
        id="cups_07", name_en="Seven of Cups", name_vi="7 Ly", arcana="Cups", number=7, yes_no_affinity="MAYBE",
        keywords_upright=["Nhiều lựa chọn ảo ảnh", "Mơ mộng viển vông", "Thiếu thực tế", "Phân vân"],
        keywords_reversed=["Tỉnh mộng", "Lựa chọn thực tế rõ ràng", "Tập trung mục tiêu"],
        description="Đứng trước vô số cám dỗ và ảo ảnh. Cần giữ cái đầu tỉnh táo để chọn giá trị thực sự.",
        image_filename="Seven of Cups.jpg"
    ),
    "cups_08": TarotCard(
        id="cups_08", name_en="Eight of Cups", name_vi="8 Ly", arcana="Cups", number=8, yes_no_affinity="NO",
        keywords_upright=["Chủ động rời đi", "Tìm kiếm ý nghĩa cao hơn", "Buông bỏ cái cũ", "Hành trình nội tâm"],
        keywords_reversed=["Không dám dứt áo ra đi", "Lẩn tránh vấn đề", "Mắc kẹt trong bế tắc"],
        description="Dũng cảm quay lưng rời bỏ những thứ không còn phù hợp để đi tìm chân trời ý nghĩa hơn.",
        image_filename="Eight of Cups.jpg"
    ),
    "cups_09": TarotCard(
        id="cups_09", name_en="Nine of Cups", name_vi="9 Ly", arcana="Cups", number=9, yes_no_affinity="YES",
        keywords_upright=["Ước nguyện thành sự thật", "Hài lòng trọn vẹn", "Hưởng thụ may mắn", "Thỏa mãn"],
        keywords_reversed=["Thỏa mãn hời hợt", "Tự mãn quá mức", "Lòng tham không đáy"],
        description="Lá bài của 'Điều ước thành hiện thực', sự viên mãn và tự hào về những gì mình đang có.",
        image_filename="Nine of Cups.jpg"
    ),
    "cups_10": TarotCard(
        id="cups_10", name_en="Ten of Cups", name_vi="10 Ly", arcana="Cups", number=10, yes_no_affinity="YES",
        keywords_upright=["Gia đình hạnh phúc", "Tình yêu viên mãn", "Cầu vồng bình yên", "Hòa hợp tuyệt đối"],
        keywords_reversed=["Xung đột gia đình", "Giá trị sống rạn nứt", "Hạnh phúc bề nổi"],
        description="Bức tranh gia đình hạnh phúc ấm êm dưới cầu vồng 10 chiếc ly tràn ngập phúc lành.",
        image_filename="Ten of Cups.jpg"
    ),
    "cups_11": TarotCard(
        id="cups_11", name_en="Page of Cups", name_vi="Tiểu Đồng Ly", arcana="Cups", number=11, yes_no_affinity="YES",
        keywords_upright=["Thông điệp tình cảm", "Trực giác chớm nở", "Tâm hồn mơ mộng", "Bất ngờ dễ thương"],
        keywords_reversed=["Ủy mị thái quá", "Tính khí trẻ con", "Tin đồn thất thiệt"],
        description="Tâm hồn nhạy cảm, giàu trí tưởng tượng và luôn sẵn sàng đón nhận những thông điệp ngọt ngào.",
        image_filename="Page of Cups.jpg"
    ),
    "cups_12": TarotCard(
        id="cups_12", name_en="Knight of Cups", name_vi="Hiệp Sĩ Ly", arcana="Cups", number=12, yes_no_affinity="YES",
        keywords_upright=["Lời mời lãng mạn", "Theo đuổi ước mơ", "Nhã nhặn lịch thiệp", "Sứ giả tình yêu"],
        keywords_reversed=["Thất hứa", "Lãng mạn viển vông", "Lừa dối tình cảm"],
        description="Chàng hiệp sĩ mang chén thánh tình yêu, biểu trưng cho sự lãng mạn và theo đuổi lý tưởng.",
        image_filename="Knight of Cups.jpg"
    ),
    "cups_13": TarotCard(
        id="cups_13", name_en="Queen of Cups", name_vi="Hoàng Hậu Ly", arcana="Cups", number=13, yes_no_affinity="YES",
        keywords_upright=["Thấu cảm sâu sắc", "Trực giác mạnh", "Dịu dàng", "Tâm hồn nuôi dưỡng"],
        keywords_reversed=["Bị cảm xúc thao túng", "Phụ thuộc tình cảm", "Bi lụy"],
        description="Hiện thân của tình yêu thương thấu cảm vô điều kiện và trí tuệ trực giác mẫn tiệp.",
        image_filename="Queen of Cups.jpg"
    ),
    "cups_14": TarotCard(
        id="cups_14", name_en="King of Cups", name_vi="Vua Ly", arcana="Cups", number=14, yes_no_affinity="YES",
        keywords_upright=["Làm chủ cảm xúc", "Điềm tĩnh bao dung", "Cố vấn thông thái", "Chữa lành"],
        keywords_reversed=["Thao túng tâm lý", "Lạnh lùng giả tạo", "Mất bình tĩnh ngấm ngầm"],
        description="Bậc thầy kiểm soát cảm xúc giữa biển khơi sóng gió, luôn giữ sự sáng suốt và ấm áp.",
        image_filename="King of Cups.jpg"
    ),

    # -------------------------------------------------------------------------
    # 3. SUIT OF SWORDS (BỘ KIẾM - KHÍ)
    # -------------------------------------------------------------------------
    "swords_01": TarotCard(
        id="swords_01", name_en="Ace of Swords", name_vi="1 Kiếm", arcana="Swords", number=1, yes_no_affinity="YES",
        keywords_upright=["Đột phá tư duy", "Sự thật sáng tỏ", "Quyết định dứt khoát", "Công lý minh bạch"],
        keywords_reversed=["Nhầm lẫn", "Lời lẽ sát thương", "Bất công", "Thiếu sáng suốt"],
        description="Thanh kiếm trí tuệ sắc bén cắt phăng mọi màn sương mù để chân lý lộ diện.",
        image_filename="Ace of Swords.jpg"
    ),
    "swords_02": TarotCard(
        id="swords_02", name_en="Two of Swords", name_vi="2 Kiếm", arcana="Swords", number=2, yes_no_affinity="MAYBE",
        keywords_upright=["Bế tắc lựa chọn", "Bịt mắt trốn tránh", "Cân bằng mong manh", "Lưỡng lự"],
        keywords_reversed=["Quyết định lộ diện", "Tháo khăn bịt mắt", "Nhìn thẳng sự thật"],
        description="Tâm thế lưỡng lự khi bịt mắt trước hai ngả đường khó khăn. Cần can đảm mở mắt lựa chọn.",
        image_filename="Two of Swords.jpg"
    ),
    "swords_03": TarotCard(
        id="swords_03", name_en="Three of Swords", name_vi="3 Kiếm", arcana="Swords", number=3, yes_no_affinity="NO",
        keywords_upright=["Đau lòng", "Tổn thương sâu sắc", "Phản bội", "Mất mát tình cảm"],
        keywords_reversed=["Chữa lành vết thương", "Vượt qua đau đớn", "Học cách tha thứ"],
        description="Ba thanh kiếm đâm xuyên trái tim dưới cơn mưa bão. Một nỗi đau cần thời gian để chữa lành.",
        image_filename="Three of Swords.jpg"
    ),
    "swords_04": TarotCard(
        id="swords_04", name_en="Four of Swords", name_vi="4 Kiếm", arcana="Swords", number=4, yes_no_affinity="MAYBE",
        keywords_upright=["Nghỉ ngơi tĩnh dưỡng", "Hồi phục năng lượng", "Tạm rút lui", "Suy ngẫm"],
        keywords_reversed=["Kiệt sức vì không nghỉ", "Tái hòa nhập", "Bồn chồn lo âu"],
        description="Khoảng lặng cần thiết để tâm trí và cơ thể hồi phục trước khi bước vào trận chiến mới.",
        image_filename="Four of Swords.jpg"
    ),
    "swords_05": TarotCard(
        id="swords_05", name_en="Five of Swords", name_vi="5 Kiếm", arcana="Swords", number=5, yes_no_affinity="NO",
        keywords_upright=["Chiến thắng cay đắng", "Thủ đoạn", "Tổn thương lòng tự trọng", "Bất hòa"],
        keywords_reversed=["Buông bỏ hiếu thắng", "Hòa giải", "Nhìn nhận sai lầm"],
        description="Thắng trong tranh cãi nhưng đánh mất mối quan hệ quý giá. Một chiến thắng không có niềm vui.",
        image_filename="Five of Swords.jpg"
    ),
    "swords_06": TarotCard(
        id="swords_06", name_en="Six of Swords", name_vi="6 Kiếm", arcana="Swords", number=6, yes_no_affinity="YES",
        keywords_upright=["Vượt qua giông bão", "Chuyển biến êm đềm", "Rời xa vùng khó khăn", "Hồi phục dần"],
        keywords_reversed=["Mắc kẹt trong rắc rối", "Chuyến đi trắc trở", "Khó dứt quá khứ"],
        description="Chiếc thuyền chở bạn rời khỏi vùng biển động để tiến vào vùng nước êm đềm hơn.",
        image_filename="Six of Swords.jpg"
    ),
    "swords_07": TarotCard(
        id="swords_07", name_en="Seven of Swords", name_vi="7 Kiếm", arcana="Swords", number=7, yes_no_affinity="NO",
        keywords_upright=["Lén lút", "Chiến thuật ngầm", "Thiếu trung thực", "Một mình gánh chịu"],
        keywords_reversed=["Bị lật tẩy", "Thừa nhận sự thật", "Hối hận", "Chiến lược thất bại"],
        description="Hành động rón rén mang thanh kiếm đi trong đêm. Cần cẩn trọng trước sự mờ ám.",
        image_filename="Seven of Swords.jpg"
    ),
    "swords_08": TarotCard(
        id="swords_08", name_en="Eight of Swords", name_vi="8 Kiếm", arcana="Swords", number=8, yes_no_affinity="NO",
        keywords_upright=["Tự trói buộc", "Tâm lý nạn nhân", "Cảm giác bế tắc", "Ảo tưởng bất lực"],
        keywords_reversed=["Tự cởi trói", "Tìm thấy lối thoát", "Lấy lại quyền làm chủ"],
        description="Bị vây quanh bởi những thanh kiếm do chính định kiến và nỗi sợ hãi tự trói buộc mình.",
        image_filename="Eight of Swords.jpg"
    ),
    "swords_09": TarotCard(
        id="swords_09", name_en="Nine of Swords", name_vi="9 Kiếm", arcana="Swords", number=9, yes_no_affinity="NO",
        keywords_upright=["Ác mộng", "Lo âu tột độ", "Mất ngủ dằn vặt", "Suy nghĩ bi quan"],
        keywords_reversed=["Hy vọng trở lại", "Nhận ra nỗi sợ chỉ là ảo ảnh", "Được giải tỏa"],
        description="Những đêm mất ngủ ôm mặt lo âu. Phần lớn nỗi sợ đều do tâm trí tự phóng đại.",
        image_filename="Nine of Swords.jpg"
    ),
    "swords_10": TarotCard(
        id="swords_10", name_en="Ten of Swords", name_vi="10 Kiếm", arcana="Swords", number=10, yes_no_affinity="NO",
        keywords_upright=["Chạm đáy nỗi đau", "Kết thúc cay đắng", "Phản bội cùng cực", "Bình minh sau đêm tối"],
        keywords_reversed=["Hồi sinh từ đống tro tàn", "Nỗi đau chấm dứt", "Vượt qua thử thách lớn nhất"],
        description="Khi đã chạm đến đáy cùng của nỗi đau, con đường duy nhất còn lại là đứng lên và tái sinh.",
        image_filename="Ten of Swords.jpg"
    ),
    "swords_11": TarotCard(
        id="swords_11", name_en="Page of Swords", name_vi="Tiểu Đồng Kiếm", arcana="Swords", number=11, yes_no_affinity="MAYBE",
        keywords_upright=["Hiếu kỳ", "Nhanh nhạy", "Quan sát sắc bén", "Thông tin mới"],
        keywords_reversed=["Nhiều chuyện", "Phát ngôn bừa bãi", "Nghi ngờ thái quá"],
        description="Tâm trí tò mò, luôn cảnh giác quan sát và phân tích mọi biến động xung quanh.",
        image_filename="Page of Swords.jpg"
    ),
    "swords_12": TarotCard(
        id="swords_12", name_en="Knight of Swords", name_vi="Hiệp Sĩ Kiếm", arcana="Swords", number=12, yes_no_affinity="MAYBE",
        keywords_upright=["Xông xáo", "Trực diện", "Lý trí quyết liệt", "Hành động thần tốc"],
        keywords_reversed=["Hung hăng", "Vô tâm tàn nhẫn", "Hấp tấp gây họa"],
        description="Lao vào mục tiêu như một cơn lốc lý trí, không ngại va chạm nhưng cần tránh bốc đồng.",
        image_filename="Knight of Swords.jpg"
    ),
    "swords_13": TarotCard(
        id="swords_13", name_en="Queen of Swords", name_vi="Hoàng Hậu Kiếm", arcana="Swords", number=13, yes_no_affinity="MAYBE",
        keywords_upright=["Sắc sảo", "Công tâm", "Độc lập lý trí", "Nói thẳng sự thật"],
        keywords_reversed=["Lạnh lùng cay nghiệt", "Định kiến hẹp hòi", "Cô đơn cay đắng"],
        description="Người phụ nữ từng trải với thanh kiếm công lý, phán đoán rành mạch và bảo vệ sự thật.",
        image_filename="Queen of Swords.jpg"
    ),
    "swords_14": TarotCard(
        id="swords_14", name_en="King of Swords", name_vi="Vua Kiếm", arcana="Swords", number=14, yes_no_affinity="YES",
        keywords_upright=["Trí tuệ đỉnh cao", "Quyền uy luật pháp", "Logic sắc bén", "Lãnh đạo bằng lý trí"],
        keywords_reversed=["Lạm quyền", "Độc đoán lạnh lùng", "Thao túng luật lệ"],
        description="Bậc thầy tư duy chiến lược và luật pháp, đưa ra những quyết định công minh chuẩn xác.",
        image_filename="King of Swords.jpg"
    ),

    # -------------------------------------------------------------------------
    # 4. SUIT OF PENTACLES (BỘ TIỀN / XU - THỔ)
    # -------------------------------------------------------------------------
    "pentacles_01": TarotCard(
        id="pentacles_01", name_en="Ace of Pentacles", name_vi="1 Tiền", arcana="Pentacles", number=1, yes_no_affinity="YES",
        keywords_upright=["Cơ hội tài chính mới", "Nền tảng vững chắc", "Thịnh vượng", "Đầu tư tiềm năng"],
        keywords_reversed=["Bỏ lỡ cơ hội đầu tư", "Thất thoát tiền bạc", "Thiếu tính toán"],
        description="Đồng tiền vàng quý giá trao từ trời mây, mở ra sự thịnh vượng và cơ hội phát triển vật chất.",
        image_filename="Ace of Pentacles.jpg"
    ),
    "pentacles_02": TarotCard(
        id="pentacles_02", name_en="Two of Pentacles", name_vi="2 Tiền", arcana="Pentacles", number=2, yes_no_affinity="MAYBE",
        keywords_upright=["Cân đối thu chi", "Linh hoạt xoay xở", "Đa nhiệm", "Thích nghi hoàn cảnh"],
        keywords_reversed=["Mất cân đối tài chính", "Quá tải việc", "Rối loạn dòng tiền"],
        description="Nghệ thuật tung hứng 2 đồng xu giữa sóng gió, giữ cho cuộc sống luôn ở trạng thái cân bằng linh hoạt.",
        image_filename="Two of Pentacles.jpg"
    ),
    "pentacles_03": TarotCard(
        id="pentacles_03", name_en="Three of Pentacles", name_vi="3 Tiền", arcana="Pentacles", number=3, yes_no_affinity="YES",
        keywords_upright=["Làm việc nhóm hiệu quả", "Kỹ năng chuyên môn", "Học hỏi trau dồi", "Hợp tác xây dựng"],
        keywords_reversed=["Bất đồng nhóm", "Thiếu tay nghề", "Làm việc cẩu thả"],
        description="Sự phối hợp ăn ý giữa người thợ giỏi và chuyên gia để kiến tạo nên công trình kiệt tác.",
        image_filename="Three of Pentacles.jpg"
    ),
    "pentacles_04": TarotCard(
        id="pentacles_04", name_en="Four of Pentacles", name_vi="4 Tiền", arcana="Pentacles", number=4, yes_no_affinity="MAYBE",
        keywords_upright=["Giữ của cẩn thận", "Ổn định tài chính", "Tiết kiệm", "Kiểm soát an toàn"],
        keywords_reversed=["Keo kiệt bủn xỉn", "Sợ mất mát", "Bế tắc dòng tiền"],
        description="Ôm chặt đồng tiền vì sợ mất an toàn. Cần phân biệt giữa tiết kiệm thông minh và giữ khư khư.",
        image_filename="Four of Pentacles.jpg"
    ),
    "pentacles_05": TarotCard(
        id="pentacles_05", name_en="Five of Pentacles", name_vi="5 Tiền", arcana="Pentacles", number=5, yes_no_affinity="NO",
        keywords_upright=["Khó khăn tài chính", "Thiếu thốn", "Cảm giác bị bỏ rơi", "Mất mát vật chất"],
        keywords_reversed=["Vượt qua giai đoạn khó", "Tìm thấy sự trợ giúp", "Hồi phục tài chính"],
        description="Bước đi trong đêm bão tuyết cạnh giáo đường ấm áp. Đừng ngại gõ cửa tìm sự trợ giúp.",
        image_filename="Five of Pentacles.jpg"
    ),
    "pentacles_06": TarotCard(
        id="pentacles_06", name_en="Six of Pentacles", name_vi="6 Tiền", arcana="Pentacles", number=6, yes_no_affinity="YES",
        keywords_upright=["Hào phóng sẻ chia", "Nhận được hỗ trợ", "Cân bằng cho và nhận", "Công bằng tài chính"],
        keywords_reversed=["Cho đi có vụ lợi", "Lợi dụng lòng tốt", "Nợ nần bất công"],
        description="Sự phân phát của cải hào hiệp và đón nhận sự giúp đỡ với lòng biết ơn.",
        image_filename="Six of Pentacles.jpg"
    ),
    "pentacles_07": TarotCard(
        id="pentacles_07", name_en="Seven of Pentacles", name_vi="7 Tiền", arcana="Pentacles", number=7, yes_no_affinity="MAYBE",
        keywords_upright=["Kiên nhẫn chờ vụ mùa", "Đánh giá kết quả", "Đầu tư dài hạn", "Tạm dừng xem xét"],
        keywords_reversed=["Mất kiên nhẫn", "Nỗ lực không kết quả", "Bỏ cuộc giữa chừng"],
        description="Dừng tay chống cuốc nhìn lại mảnh vườn thành quả, kiên nhẫn chờ đến ngày quả chín ngọt ngào.",
        image_filename="Seven of Pentacles.jpg"
    ),
    "pentacles_08": TarotCard(
        id="pentacles_08", name_en="Eight of Pentacles", name_vi="8 Tiền", arcana="Pentacles", number=8, yes_no_affinity="YES",
        keywords_upright=["Chăm chỉ", "Nâng cao tay nghề", "Tập trung tỉ mỉ", "Cống hiến cho công việc"],
        keywords_reversed=["Lười biếng", "Thiếu tập trung", "Làm việc máy móc vô hồn"],
        description="Người thợ cần mẫn đục đẽo từng đồng tiền, biểu trưng cho sự kiên trì mài giũa tài năng.",
        image_filename="Eight of Pentacles.jpg"
    ),
    "pentacles_09": TarotCard(
        id="pentacles_09", name_en="Nine of Pentacles", name_vi="9 Tiền", arcana="Pentacles", number=9, yes_no_affinity="YES",
        keywords_upright=["Tự do tài chính", "Độc lập tự chủ", "Tận hưởng cuộc sống", "Thành quả xứng đáng"],
        keywords_reversed=["Phụ thuộc tài chính", "Tiêu xài hoang phí", "Cô đơn trong xa hoa"],
        description="Tận hưởng sự thư thái trong khu vườn sum suê hoa trái từ chính nỗ lực tự thân tạo dựng.",
        image_filename="Nine of Pentacles.jpg"
    ),
    "pentacles_10": TarotCard(
        id="pentacles_10", name_en="Ten of Pentacles", name_vi="10 Tiền", arcana="Pentacles", number=10, yes_no_affinity="YES",
        keywords_upright=["Gia sản vững bền", "Thịnh vượng lâu dài", "Gia đình sung túc", "Kế thừa tài sản"],
        keywords_reversed=["Tranh chấp gia tài", "Tổn thất tài chính lớn", "Bất ổn gia đình"],
        description="Đỉnh cao của sự giàu sang, thịnh vượng và di sản truyền đời cho nhiều thế hệ.",
        image_filename="Ten of Pentacles.jpg"
    ),
    "pentacles_11": TarotCard(
        id="pentacles_11", name_en="Page of Pentacles", name_vi="Tiểu Đồng Tiền", arcana="Pentacles", number=11, yes_no_affinity="YES",
        keywords_upright=["Học hỏi thực tế", "Cơ hội việc làm", "Chăm chỉ tích lũy", "Khao khát thành công"],
        keywords_reversed=["Thiếu thực tế", "Lười nhác", "Kế hoạch dang dở"],
        description="Chàng trai nâng niu đồng tiền vàng, chăm chú học hỏi để biến ước mơ thành của cải thực tế.",
        image_filename="Page of Pentacles.jpg"
    ),
    "pentacles_12": TarotCard(
        id="pentacles_12", name_en="Knight of Pentacles", name_vi="Hiệp Sĩ Tiền", arcana="Pentacles", number=12, yes_no_affinity="YES",
        keywords_upright=["Kiên định vững chắc", "Đáng tin cậy", "Làm việc có phương pháp", "Trách nhiệm cao"],
        keywords_reversed=["Cứng nhắc bảo thủ", "Chậm chạp lề mề", "Mất động lực"],
        description="Hiệp sĩ cưỡi ngựa đen vững chãi trên đồng ruộng, từng bước chắc chắn tiến đến mục tiêu.",
        image_filename="Knight of Pentacles.jpg"
    ),
    "pentacles_13": TarotCard(
        id="pentacles_13", name_en="Queen of Pentacles", name_vi="Hoàng Hậu Tiền", arcana="Pentacles", number=13, yes_no_affinity="YES",
        keywords_upright=["Thực tế chu đáo", "Chăm sóc gia đình", "Trù phú", "Quản lý tài chính giỏi"],
        keywords_reversed=["Lo âu tiền bạc", "Bỏ bê trách nhiệm", "Giam mình trong vật chất"],
        description="Bà mẹ ấm áp của đất đai, vừa giỏi quán xuyến tài chính vừa tràn ngập lòng hiếu khách.",
        image_filename="Queen of Pentacles.jpg"
    ),
    "pentacles_14": TarotCard(
        id="pentacles_14", name_en="King of Pentacles", name_vi="Vua Tiền", arcana="Pentacles", number=14, yes_no_affinity="YES",
        keywords_upright=["Đế chế tài chính", "Thành công vật chất", "Kinh doanh lão luyện", "Vững như bàn thạch"],
        keywords_reversed=["Tham lam thực dụng", "Bảo thủ", "Phá sản đầu tư"],
        description="Ông trùm kinh doanh uy quyền ngự trên ngai vàng bò tót, làm chủ mọi dòng tiền và của cải.",
        image_filename="King of Pentacles.jpg"
    ),
}

# Cấu hình các kiểu trải bài
SPREAD_DEFINITIONS: Dict[str, dict] = {
    "daily": {
        "key": "daily",
        "name": "Daily Card (Năng Lượng Ngày)",
        "card_count": 1,
        "is_daily": True,
        "requires_question": False,
        "positions": [
            ("LÁ 1: NĂNG LƯỢNG NGÀY", "Thông điệp & năng lượng bao quát dẫn dắt ngày hôm nay của bạn.")
        ]
    },
    "yes_no": {
        "key": "yes_no",
        "name": "Yes / No (Hỏi Nhanh)",
        "card_count": 1,
        "is_daily": False,
        "requires_question": True,
        "positions": [
            ("PHÁN QUYẾT YES / NO", "Phán quyết trực tiếp kèm định hướng cho câu hỏi của bạn.")
        ]
    },
    "single": {
        "key": "single",
        "name": "Single Card (Hỏi Đáp 1 Lá)",
        "card_count": 1,
        "is_daily": False,
        "requires_question": True,
        "positions": [
            ("LỜI KHUYÊN TRỌNG TÂM", "Góc nhìn cốt lõi và bài học quan trọng nhất cho vấn đề của bạn.")
        ]
    },
    "choices": {
        "key": "choices",
        "name": "Two Choices (So Sánh Nhanh - 3 Lá)",
        "card_count": 3,
        "is_daily": False,
        "requires_question": True,
        "positions": [
            ("LÁ 1: BỐI CẢNH", "Tâm thế & thực trạng hiện tại của bạn trước quyết định này."),
            ("LÁ 2: HƯỚNG ĐI A", "Kết quả, tiềm năng & bài học nếu bạn chọn Phương án A."),
            ("LÁ 3: HƯỚNG ĐI B", "Kết quả, tiềm năng & bài học nếu bạn chọn Phương án B.")
        ]
    },
    "two_paths": {
        "key": "two_paths",
        "name": "Two Paths (So Sánh Chuyên Sâu 2 Hướng - 5 Lá)",
        "card_count": 5,
        "is_daily": False,
        "requires_question": True,
        "positions": [
            ("LÁ 1: BỐI CẢNH CHUNG", "Gốc rễ và nguyên nhân dẫn đến sự phân vân hiện tại."),
            ("LÁ 2: THUẬN LỢI CỦA HƯỚNG A", "Điểm mạnh, cơ hội và kết quả tốt nếu chọn Hướng A."),
            ("LÁ 3: RỦI RO CỦA HƯỚNG A", "Thách thức, bất lợi hoặc cái giá phải trả của Hướng A."),
            ("LÁ 4: THUẬN LỢI CỦA HƯỚNG B", "Điểm mạnh, cơ hội và kết quả tốt nếu chọn Hướng B."),
            ("LÁ 5: RỦI RO CỦA HƯỚNG B", "Thách thức, bất lợi hoặc cái giá phải trả của Hướng B.")
        ]
    },
    "horseshoe": {
        "key": "horseshoe",
        "name": "Horseshoe Spread (Trải Bài Móng Ngựa - 5 Lá)",
        "card_count": 5,
        "is_daily": False,
        "requires_question": True,
        "positions": [
            ("LÁ 1: QUÁ KHỨ ẢNH HƯỞNG", "Sự việc trong quá khứ dẫn đến tình trạng hiện tại."),
            ("LÁ 2: HIỆN TRẠNG VẤN ĐỀ", "Tình hình thực tế và những gì đang diễn ra."),
            ("LÁ 3: TRỞ NGẠI / YẾU TỐ ẨN", "Thách thức bất ngờ hoặc điều bạn chưa nhìn thấy."),
            ("LÁ 4: LỜI KHUYÊN HÀNH ĐỘNG", "Giải pháp và hướng xử lý tối ưu nhất lúc này."),
            ("LÁ 5: KẾT QUẢ TIỀM NĂNG", "Kết cục nếu bạn làm theo định hướng và lời khuyên.")
        ]
    },
    "ppf": {
        "key": "ppf",
        "name": "Past - Present - Future (Quá Khứ - Hiện Tại - Tương Lai)",
        "card_count": 3,
        "is_daily": False,
        "requires_question": True,
        "positions": [
            ("LÁ 1: QUÁ KHỨ", "Cội nguồn, sự việc đã qua tạo tiền đề cho hiện tại."),
            ("LÁ 2: HIỆN TẠI", "Thực trạng vấn đề và những gì đang diễn ra."),
            ("LÁ 3: TƯƠNG LAI", "Xu hướng phát triển và kết quả tiềm năng sắp tới.")
        ]
    },
    "mbs": {
        "key": "mbs",
        "name": "Mind - Body - Spirit (Tâm Trí - Thể Chất - Trực Giác)",
        "card_count": 3,
        "is_daily": False,
        "requires_question": True,
        "positions": [
            ("LÁ 1: TÂM TRÍ (MIND)", "Suy nghĩ, nhận thức và lý trí của bạn lúc này."),
            ("LÁ 2: THỂ CHẤT (BODY)", "Hành động thực tế, sức khỏe và thế giới vật chất."),
            ("LÁ 3: TRỰC GIÁC (SPIRIT)", "Tiếng nói nội tâm, tâm linh và bài học tiến hóa sâu xa.")
        ]
    },
    "celtic": {
        "key": "celtic",
        "name": "Celtic Cross (Trải Bài Chữ Thập 10 Lá)",
        "card_count": 10,
        "is_daily": False,
        "requires_question": True,
        "positions": [
            ("LÁ 1: BẢN CHẤT THỰC TẠI", "Bản chất cốt lõi của tình huống hiện tại."),
            ("LÁ 2: TRỞ NGẠI / THÁCH THỨC", "Yếu tố cản trở hoặc hỗ trợ tức thời đè lên hiện tại."),
            ("LÁ 3: TIỀM THỨC / CĂN NGUYÊN", "Nền tảng vô thức và nguyên nhân sâu xa trong quá khứ."),
            ("LÁ 4: QUÁ KHỨ GẦN", "Sự kiện vừa mới diễn ra và đang dần qua đi."),
            ("LÁ 5: MỤC TIÊU / Ý THỨC", "Tiềm năng tốt nhất hoặc điều bạn đang hướng tới."),
            ("LÁ 6: TƯƠNG LAI GẦN", "Sự việc chuẩn bị xảy đến trong tương lai gần."),
            ("LÁ 7: THÁI ĐỘ BẢN THÂN", "Cách bạn tự nhìn nhận bản thân và tâm thế đối diện."),
            ("LÁ 8: MÔI TRƯỜNG BÊN NGOÀI", "Tác động từ người xung quanh, xã hội và hoàn cảnh."),
            ("LÁ 9: HY VỌNG & NỖI SỢ", "Những khao khát sâu kín nhất xen lẫn nỗi âu lo."),
            ("LÁ 10: KẾT QUẢ CUỐI CÙNG", "Tổng hòa bài học và cái kết tiềm năng nhất của vấn đề.")
        ]
    }
}


def draw_spread(spread_key: str) -> List[DrawnCard]:
    """Rút ngẫu nhiên N lá không trùng lặp từ bộ 78 lá bài kèm xác suất 50% đảo chiều."""
    if spread_key not in SPREAD_DEFINITIONS:
        raise ValueError(f"Kiểu trải bài không hợp lệ: {spread_key}")

    spread_def = SPREAD_DEFINITIONS[spread_key]
    count = spread_def["card_count"]
    positions = spread_def["positions"]

    all_cards = list(TAROT_DECK.values())
    chosen_cards = random.sample(all_cards, count)

    drawn: List[DrawnCard] = []
    for i, card in enumerate(chosen_cards):
        is_reversed = random.choice([True, False])
        pos_title, pos_desc = positions[i]
        drawn.append(DrawnCard(
            card=card,
            is_reversed=is_reversed,
            position_index=i + 1,
            position_title=pos_title,
            position_description=pos_desc
        ))

    return drawn


def get_yes_no_verdict(card: TarotCard, is_reversed: bool) -> Tuple[str, str, int]:
    """
    Trả về phán quyết Yes/No chuẩn xác theo biểu tượng Tarot:
    Return (Badge, Tiêu đề tiếng Việt, Màu sắc int Discord)
    """
    affinity = card.yes_no_affinity

    if affinity == "YES":
        if not is_reversed:
            return ("🟢 CÓ (YES)", "Năng lượng rất tích cực và thuận lợi để tiến hành!", 0x2ECC71)
        else:
            return ("🟡 CÓ NHƯNG CẦN CÂN NHẮC (CONDITIONAL YES)", "Có tiềm năng nhưng có trở ngại nhỏ hoặc cần điều chỉnh kế hoạch!", 0xF1C40F)
    elif affinity == "NO":
        if not is_reversed:
            return ("🔴 KHÔNG (NO)", "Năng lượng hiện tại chưa phù hợp hoặc rủi ro cao!", 0xE74C3C)
        else:
            return ("🔴 TẠM THỜI CHƯA NÊN (STRONG NO)", "Rủi ro bất lợi hoặc sự việc còn nhiều biến cố chưa lường trước!", 0xC0392B)
    else:  # MAYBE
        if not is_reversed:
            return ("🟡 TÙY THUỘC VÀO BẠN (DEPENDS)", "Kết quả phụ thuộc lớn vào sự chủ động và quyết định sắp tới của bạn!", 0xF39C12)
        else:
            return ("🔴 NGHIÊNG VỀ KHÔNG NÊN (LEANING NO)", "Khả năng thành công thấp, nhiều yếu tố mập mờ thiếu minh bạch!", 0xE67E22)


def ensure_card_asset(card: TarotCard) -> Optional[pathlib.Path]:
    """Kiểm tra và tải về ảnh lá bài từ CDN nếu chưa có trên máy."""
    dest_path = card.local_image_path
    if dest_path.exists() and dest_path.stat().st_size > 0:
        return dest_path

    try:
        encoded_filename = urllib.parse.quote(card.image_filename)
        url = f"{GITHUB_ASSET_BASE_URL}/{encoded_filename}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; DiscordMikeBot/1.0)"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = resp.read()
            if len(data) > 1000:
                dest_path.write_bytes(data)
                return dest_path
    except Exception as e:
        print(f"[TarotDeck] Không thể tải ảnh {card.image_filename}: {e}", flush=True)

    return None


# =========================================================================
# 🎭 DANH TÍNH NGƯỜI TRẢI BÀI (TAROT READERS)
# =========================================================================
READER_STYLES: Dict[str, Dict] = {
    "neutral": {
        "id": "neutral",
        "name": "⚖️ Orion",
        "title": "Nhà Chiêm Tinh Điềm Tĩnh",
        "desc": "Điềm tĩnh và khách quan (Mặc định)",
        "color": 0x7851A9,
        "embed_title": "📖 THÔNG ĐIỆP TỪ VŨ TRỤ",
        "loading_title": "✨ ĐANG ĐÓN NHẬN THÔNG ĐIỆP...",
        "loading_desc": "🌌 *Orion đang kết nối năng lượng và giải mã tín hiệu từ vũ trụ, xin chờ trong giây lát...*",
        "persona_prompt": """
        🎭 BẠN LÀ ORION - NHÀ CHIÊM TINH ĐIỀM TĨNH & KHÁCH QUAN (MẶC ĐỊNH)
        - Phong cách: Điềm tĩnh, thông tuệ, sắc sảo, khách quan và dựa trên tâm lý học cùng thực tế cuộc sống.
        - Không bi quan hóa, không vùi dập, nhưng TUYỆT ĐỐI KHÔNG nịnh bợ, tô hồng hay khẳng định những điều viển vông. Đưa ra góc nhìn khai sáng, đa chiều và giải pháp thực tiễn.
        """.strip()
    },
    "healer": {
        "id": "healer",
        "name": "🌸 Celeste",
        "title": "Người Chữa Lành Thấu Cảm",
        "desc": "Ấm áp, dịu dàng và đầy hy vọng",
        "color": 0xF06292,
        "embed_title": "💖 THÔNG ĐIỆP TỪ CELESTE",
        "loading_title": "💖 CELESTE ĐANG GỬI TRAO NĂNG LƯỢNG...",
        "loading_desc": "🌸 *Celeste đang gửi gắm những lời vỗ về và năng lượng chữa lành tới bạn, xin chờ trong giây lát...*",
        "persona_prompt": """
        🎭 BẠN LÀ CELESTE - NGƯỜI CHỮA LÀNH DỊU DÀNG & THẤU CẢM
        - Phong cách: Cực kỳ ấm áp, dịu dàng, bao dung và thấu hiểu sâu sắc như một người bạn tâm giao giàu lòng trắc ẩn.
        - Tuyệt đối không hứa hão viển vông, nhưng luôn tìm kiếm điểm sáng (silver lining), sự an ủi và cơ hội phục hồi / tái sinh ngay cả trong những lá bài mang năng lượng nặng nề nhất (như Tower, 10 Swords, Death...).
        - Vỗ về những lo âu, công nhận cảm xúc của người hỏi, giúp họ cảm thấy được chở che, thấu hiểu và có thêm niềm tin, bình yên trong tâm hồn.
        """.strip()
    },
    "chaos": {
        "id": "chaos",
        "name": "🃏 Jester",
        "title": "Kẻ Lập Dị Bí Ẩn",
        "desc": "Trào phúng, quái lạ và khó đoán",
        "color": 0xE67E22,
        "embed_title": "🃏 LỜI THÌ THẦM CỦA JESTER",
        "loading_title": "🃏 JESTER ĐANG KHUẤY ĐẢO KHÔNG GIAN...",
        "loading_desc": "🌀 *Tín hiệu đang bị Jester bẻ cong, chờ tí xem quẻ bài này tấu hài ra sao...*",
        "persona_prompt": """
        🎭 BẠN LÀ JESTER - KẺ LẬP DỊ & HỖN LOẠN
        - Phong cách: Tưng tửng, quái dị, hài hước châm biếm sâu cay (dark humor, witty, meme-ish), nói chuyện như một kẻ tiên tri nửa điên nửa tỉnh đến từ chiều không gian kỳ lạ.
        - Đọc bài theo những góc nhìn "bẻ lái" cực gắt, liên tưởng những hình ảnh kỳ quặc, trào phúng hoặc lật tẩy sự thật trớ trêu nhưng ngẫm lại thấy vô cùng chí lý.
        - Cực kỳ khó đoán, vừa tấu hài vừa khai sáng bằng sự nghịch ngợm, không theo bất kỳ khuôn mẫu nghiêm túc nào!
        """.strip()
    }
}
