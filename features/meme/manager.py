import struct
import json
import time
import math
from typing import List, Dict, Optional, Tuple, Any
from datetime import datetime, timezone
import aiosqlite
import config

INITIAL_SEEDS = [
    {
        "title": "Độ Mixi Đúng Đúng Hợp Lý",
        "url": "https://khoanhdep.com/wp-content/uploads/2026/02/meme-do-mixi-7.jpg",
        "media_type": "image",
        "caption": "Đúng đúng... rất là hợp lý luôn!",
        "tags": ["độ mixi", "mixigaming", "đúng", "hợp lý", "tán thành", "agree", "chuẩn", "đồng tình"],
        "vibe": "Tán thành tuyệt đối, gật gù tâm đắc, công nhận sự thật hiển nhiên",
        "source": "seed"
    },
    {
        "title": "Độ Mixi Cay Cú Bất Lực",
        "url": "https://khoanhdep.com/wp-content/uploads/2026/02/meme-do-mixi-8.jpg",
        "media_type": "image",
        "caption": "Cay thật sự, không còn gì để nói nữa!",
        "tags": ["độ mixi", "cay", "tức", "bất lực", "rage", "mad", "troll", "ức chế"],
        "vibe": "Tức giận, cay cú tột cùng nhưng không làm gì được, ức chế tột độ",
        "source": "seed"
    },
    {
        "title": "Mèo Khóc Giơ Ngón Tay Like (Crying Cat Thumbs Up)",
        "url": "https://i.imgflip.com/49z9rw.jpg",
        "media_type": "image",
        "caption": "Tuyệt vời lắm... vừa khóc vừa mỉm cười!",
        "tags": ["mèo khóc", "crying cat", "thumbs up", "đau khổ", "bất lực", "gượng cười", "sad", "pain"],
        "vibe": "Đau khổ, tổn thương bên trong nhưng ngoài mặt vẫn phải gượng cười tỏ ra ổn",
        "source": "seed"
    },
    {
        "title": "Drake Hotline Bling (Từ Chối vs Đồng Ý)",
        "url": "https://i.imgflip.com/30b1gx.jpg",
        "media_type": "image",
        "caption": "Cái kia thì chê, cái này mới là chân ái!",
        "tags": ["drake", "hotline bling", "chê", "thích", "so sánh", "reject", "prefer", "chọn lọc"],
        "vibe": "So sánh 2 lựa chọn, chê cái dở và say mê ủng hộ cái đúng gu",
        "source": "seed"
    },
    {
        "title": "Người Đàn Ông Phân Vân 2 Nút Bấm (Two Buttons)",
        "url": "https://i.imgflip.com/1g8my4.jpg",
        "media_type": "image",
        "caption": "Khó nghĩ quá, bấm nút nào cũng toang!",
        "tags": ["two buttons", "phân vân", "khó chọn", "toát mồ hôi", "lưỡng lự", "dilemma", "sweat"],
        "vibe": "Phân vân cực độ giữa 2 lựa chọn tiến thoái lưỡng nan",
        "source": "seed"
    },
    {
        "title": "Bạn Gái Ghen Khi Bạn Trai Nhìn Cô Gái Khác (Distracted Boyfriend)",
        "url": "https://i.imgflip.com/1ur9b0.jpg",
        "media_type": "image",
        "caption": "Có mới nới cũ, nhìn sang thứ hấp dẫn hơn!",
        "tags": ["distracted boyfriend", "nhìn gái", "ghen", "có mới nới cũ", "cám dỗ", "distraction"],
        "vibe": "Bỏ bê thứ hiện tại vì bị cám dỗ bởi thứ mới mẻ, hấp dẫn hơn",
        "source": "seed"
    },
    {
        "title": "Pikachu Bất Ngờ Há Hốc Mồm (Surprised Pikachu)",
        "url": "https://i.imgflip.com/2kbn1e.jpg",
        "media_type": "image",
        "caption": "Ủa kì lạ vậy... thật bất ngờ chưa kìa!",
        "tags": ["pikachu", "surprised", "há hốc mồm", "ngạc nhiên", "sốc", "bất ngờ", "ironic"],
        "vibe": "Giả vờ bất ngờ trước một kết quả hiển nhiên do chính mình gây ra",
        "source": "seed"
    },
    {
        "title": "Cô Gái Quát Con Mèo Bàn Ăn (Woman Yelling at Cat)",
        "url": "https://i.imgflip.com/345v97.jpg",
        "media_type": "image",
        "caption": "Một bên gào thét hung hăng, một bên ngơ ngác vô tội!",
        "tags": ["woman yelling at cat", "mèo bàn ăn", "smudge cat", "cãi nhau", "ngơ ngác", "oan ức"],
        "vibe": "Một bên trách móc giận dữ trong khi đối phương mặt tỉnh bơ ngơ ngác vô can",
        "source": "seed"
    },
    {
        "title": "Khỉ Con Liếc Mắt Ngại Ngùng (Monkey Puppet Look Away)",
        "url": "https://i.imgflip.com/2gnnjh.jpg",
        "media_type": "image",
        "caption": "Ủa đâu có biết gì đâu, liếc sang chỗ khác liền!",
        "tags": ["monkey puppet", "liếc mắt", "lẩn tránh", "giả vờ không biết", "awkward", "guilty"],
        "vibe": "Chột dạ, lén lút lảng tránh ánh nhìn khi bị nhắc trúng tim đen",
        "source": "seed"
    },
    {
        "title": "Batman Tát Robin (Batman Slapping Robin)",
        "url": "https://i.imgflip.com/9ehk.jpg",
        "media_type": "image",
        "caption": "Nín ngay, nói xàm vừa thôi!",
        "tags": ["batman", "robin", "tát", "ngừng nói", "tỉnh táo lại", "slap", "shut up"],
        "vibe": "Cắt ngang lời nói ngớ ngẩn, kéo đối phương về thực tế bằng hành động dứt khoát",
        "source": "seed"
    },
    {
        "title": "Chó Cheems vs Chó Cơ Bắp Doge (Buff Doge vs Cheems)",
        "url": "https://i.imgflip.com/43a45p.jpg",
        "media_type": "image",
        "caption": "Xưa hùng dũng bản lĩnh bao nhiêu, nay hèn nhát bấy nhiêu!",
        "tags": ["doge", "cheems", "chó cơ bắp", "xưa và nay", "yếu đuối", "hoài niệm", "so sánh"],
        "vibe": "Tự ti hoặc châm biếm sự suy giảm bản lĩnh giữa quá khứ huy hoàng và hiện tại",
        "source": "seed"
    },
    {
        "title": "Pepe Hề Đeo Tóc Giả (Pepe Clown Makeup)",
        "url": "https://i.imgflip.com/38el31.jpg",
        "media_type": "image",
        "caption": "Từng bước tự biến mình thành trò hề!",
        "tags": ["pepe", "clown", "trò hề", "ngốc nghếch", "mù quáng", "tự lừa dối", "fool"],
        "vibe": "Tự nhận ra bản thân đã dại khờ, tin người mù quáng và làm trò cười cho thiên hạ",
        "source": "seed"
    },
    {
        "title": "Disaster Girl (Bé Gái Cười Nham Hiểm Trước Ngôi Nhà Cháy)",
        "url": "https://i.imgflip.com/23ls.jpg",
        "media_type": "image",
        "caption": "Mọi thứ đang cháy rụi và tôi chính là thủ phạm!",
        "tags": ["disaster girl", "cười nham hiểm", "cháy nhà", "hả hê", "hắc ám", "villain", "chaos"],
        "vibe": "Thích thú khi thấy hỗn loạn hoặc chính mình vừa ngấm ngầm gây ra rắc rối lớn",
        "source": "seed"
    },
    {
        "title": "Meme Chê (Tuyệt Bích Ảnh Chế)",
        "url": "https://bom.edu.vn/public/upload/2024/12/meme-che-viet-nam-3.webp",
        "media_type": "image",
        "caption": "Chê cực mạnh! Không thể chấp nhận nổi!",
        "tags": ["chê", "meme chê", "việt nam", "từ chối", "không duyệt", "dislike", "disapprove"],
        "vibe": "Phán xét gay gắt, chê bai thẳng thừng, bác bỏ không thương tiếc",
        "source": "seed"
    },
    {
        "title": "Omedetou Shinji Clapping (Evangelion Vỗ Tay Chúc Mừng)",
        "url": "https://media.tenor.com/PZ7b4-6lI00AAAAC/evangelion-congratulations.gif",
        "media_type": "gif",
        "caption": "Omedetou! Xin chúc mừng bạn đã đạt tới cảnh giới này!",
        "tags": ["omedetou", "shinji", "evangelion", "vỗ tay", "chúc mừng", "congratulations", "anime", "mỉa mai"],
        "vibe": "Vỗ tay chúc mừng một cách trịnh trọng hoặc mỉa mai một màn thể hiện khó đỡ",
        "source": "seed"
    },
    {
        "title": "KEKW / Pepe Laugh (Cười Bể Bụng El Risitas)",
        "url": "https://media.tenor.com/T0b4_qG3i_wAAAAC/kekw-kek.gif",
        "media_type": "gif",
        "caption": "KEKW! Cười không nhặt được mồm luôn á!",
        "tags": ["kek", "kekw", "pepelaugh", "cười", "el risitas", "twitch", "emote", "lmao", "lol", "cười lăn lộn"],
        "vibe": "Cười lăn lộn, cười nghiêng ngả, cười vỡ bụng trước một tình huống quá buồn cười",
        "source": "seed"
    },
    {
        "title": "GigaChad (Người Đàn Ông Hoàn Hảo Alpha Male)",
        "url": "https://media.tenor.com/F3bOQfU0a-wAAAAC/gigachad-chad.gif",
        "media_type": "gif",
        "caption": "Vâng, tôi làm vậy đấy, thì sao nào?",
        "tags": ["gigachad", "chad", "alpha", "nam tính", "tự tin", "đẳng cấp", "bản lĩnh", "bá đạo"],
        "vibe": "Tự tin ngút trời, điềm tĩnh chấp nhận mọi ý kiến với phong thái đỉnh cao",
        "source": "seed"
    },
    {
        "title": "Wojak Crying Behind Mask (Khóc Thầm Sau Mặt Nạ Cười)",
        "url": "https://i.imgflip.com/4acc2v.jpg",
        "media_type": "image",
        "caption": "Bên ngoài cười ha ha, bên trong khóc ròng rã!",
        "tags": ["wojak", "khóc sau mặt nạ", "crying mask", "đau lòng", "bất lực", "giả vờ ổn", "doomer", "sad"],
        "vibe": "Giả vờ vui vẻ đắc ý trước mặt mọi người nhưng thực ra bên trong đang cay cú tổn thương",
        "source": "seed"
    }
]


def serialize_vector(vector: List[float]) -> bytes:
    """Nén danh sách float thành chuỗi nhị phân (Binary BLOB) siêu gọn."""
    return struct.pack(f"{len(vector)}f", *vector)


def deserialize_vector(blob: bytes) -> List[float]:
    """Giải nén chuỗi nhị phân thành danh sách float."""
    count = len(blob) // 4
    return list(struct.unpack(f"{count}f", blob))


def cosine_similarity(v1: List[float], v2: List[float]) -> float:
    """Tính độ tương đồng Cosine giữa 2 vector."""
    if not v1 or not v2 or len(v1) != len(v2):
        return 0.0
    dot = 0.0
    norm1 = 0.0
    norm2 = 0.0
    for a, b in zip(v1, v2):
        dot += a * b
        norm1 += a * a
        norm2 += b * b
    if norm1 == 0.0 or norm2 == 0.0:
        return 0.0
    return dot / (math.sqrt(norm1) * math.sqrt(norm2))


class MemeManager:
    """Quản lý Kho Lưu Trữ Meme, Vector Database và Đếm Lượt Sử Dụng."""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = str(db_path or config.MEME_DB_PATH)
        self._db: Optional[aiosqlite.Connection] = None

    async def get_db(self) -> aiosqlite.Connection:
        if self._db is None:
            self._db = await aiosqlite.connect(self.db_path)
            self._db.row_factory = aiosqlite.Row
        return self._db

    async def init_db(self) -> None:
        """Khởi tạo cấu trúc bảng SQLite và Seed kho meme ban đầu."""
        db = await self.get_db()
        await db.execute("""
            CREATE TABLE IF NOT EXISTS memes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                url TEXT UNIQUE NOT NULL,
                media_type TEXT DEFAULT 'image',
                caption TEXT,
                tags TEXT,
                vibe TEXT,
                vector BLOB,
                source TEXT DEFAULT 'seed',
                likes INTEGER DEFAULT 0,
                uses_count INTEGER DEFAULT 0,
                created_at TEXT NOT NULL,
                added_by TEXT DEFAULT 'System'
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS meme_likes (
                user_id INTEGER NOT NULL,
                meme_id INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (user_id, meme_id)
            )
        """)
        await db.commit()
        print("[MemeManager] Đã khởi tạo cơ sở dữ liệu Meme Vault thành công.", flush=True)

    async def seed_vault_if_empty(self, embed_fn) -> int:
        """Nạp các meme kinh điển ban đầu và vector hóa chúng nếu chưa có trong DB."""
        db = await self.get_db()
        added = 0
        now_str = datetime.now(timezone.utc).isoformat()

        for item in INITIAL_SEEDS:
            try:
                # Kiểm tra xem meme đã có trong DB chưa
                cursor = await db.execute("SELECT 1 FROM memes WHERE url = ?", (item["url"],))
                exists = await cursor.fetchone()
                if exists:
                    continue

                # Ghép chuỗi ngữ nghĩa để tạo vector chất lượng cao
                text_to_embed = f"Title: {item['title']}. Vibe: {item['vibe']}. Tags: {', '.join(item['tags'])}. Caption: {item['caption']}"
                vector = await embed_fn(text_to_embed)
                if not vector:
                    continue

                blob = serialize_vector(vector)
                tags_json = json.dumps(item["tags"], ensure_ascii=False)

                await db.execute("""
                    INSERT OR IGNORE INTO memes (
                        title, url, media_type, caption, tags, vibe, vector, source, created_at, added_by
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    item["title"],
                    item["url"],
                    item["media_type"],
                    item["caption"],
                    tags_json,
                    item["vibe"],
                    blob,
                    item["source"],
                    now_str,
                    "System"
                ))
                added += 1
            except Exception as e:
                print(f"[MemeManager] Lỗi seed meme '{item['title']}': {e}", flush=True)

        if added > 0:
            await db.commit()
            print(f"[MemeManager] Đã nạp thành công {added} meme kinh điển mới vào Vector Vault.", flush=True)

        cursor = await db.execute("SELECT COUNT(*) as cnt FROM memes")
        row = await cursor.fetchone()
        return row["cnt"] if row else 0

    async def add_meme(
        self,
        title: str,
        url: str,
        media_type: str = "image",
        caption: str = "",
        tags: Optional[List[str]] = None,
        vibe: str = "",
        vector: Optional[List[float]] = None,
        source: str = "web",
        added_by: str = "User"
    ) -> Optional[int]:
        """Thêm một meme mới kèm vector vào kho dữ liệu."""
        db = await self.get_db()
        tags_json = json.dumps(tags or [], ensure_ascii=False)
        blob = serialize_vector(vector) if vector else None
        now_str = datetime.now(timezone.utc).isoformat()

        try:
            cursor = await db.execute("""
                INSERT INTO memes (
                    title, url, media_type, caption, tags, vibe, vector, source, created_at, added_by
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                title, url, media_type, caption, tags_json, vibe, blob, source, now_str, added_by
            ))
            await db.commit()
            return cursor.lastrowid
        except aiosqlite.IntegrityError:
            # URL đã tồn tại trong DB -> Cập nhật lại lượt dùng
            cursor = await db.execute("SELECT id FROM memes WHERE url = ?", (url,))
            row = await cursor.fetchone()
            if row:
                return row["id"]
            return None
        except Exception as e:
            print(f"[MemeManager] Lỗi khi thêm meme: {e}", flush=True)
            return None

    async def search_vector(
        self,
        query_vector: List[float],
        top_k: int = 5,
        threshold: float = 0.70
    ) -> List[Dict[str, Any]]:
        """
        Tìm kiếm ngữ nghĩa Vector Search (Cosine Similarity) trong kho nội bộ.
        Trả về danh sách meme đạt độ tương đồng >= threshold, xếp từ cao xuống thấp.
        """
        db = await self.get_db()
        cursor = await db.execute("SELECT id, title, url, media_type, caption, tags, vibe, vector, source, likes, uses_count FROM memes WHERE vector IS NOT NULL")
        rows = await cursor.fetchall()

        results = []
        for row in rows:
            blob = row["vector"]
            if not blob:
                continue
            stored_vec = deserialize_vector(blob)
            score = cosine_similarity(query_vector, stored_vec)
            if score >= threshold:
                tags = []
                try:
                    tags = json.loads(row["tags"]) if row["tags"] else []
                except Exception:
                    pass

                results.append({
                    "id": row["id"],
                    "title": row["title"],
                    "url": row["url"],
                    "media_type": row["media_type"],
                    "caption": row["caption"],
                    "tags": tags,
                    "vibe": row["vibe"],
                    "source": row["source"],
                    "likes": row["likes"],
                    "uses_count": row["uses_count"],
                    "similarity": round(score, 4)
                })

        results.sort(key=lambda x: x["similarity"], reverse=True)
        return results[:top_k]

    async def search_keywords(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Tìm kiếm theo từ khóa text (LIKE) bổ trợ khi chưa có vector."""
        db = await self.get_db()
        pattern = f"%{query.strip().lower()}%"
        cursor = await db.execute("""
            SELECT id, title, url, media_type, caption, tags, vibe, source, likes, uses_count
            FROM memes
            WHERE LOWER(title) LIKE ? OR LOWER(tags) LIKE ? OR LOWER(vibe) LIKE ? OR LOWER(caption) LIKE ?
            ORDER BY uses_count DESC, likes DESC
            LIMIT ?
        """, (pattern, pattern, pattern, pattern, limit))
        rows = await cursor.fetchall()

        results = []
        for row in rows:
            tags = []
            try:
                tags = json.loads(row["tags"]) if row["tags"] else []
            except Exception:
                pass
            results.append({
                "id": row["id"],
                "title": row["title"],
                "url": row["url"],
                "media_type": row["media_type"],
                "caption": row["caption"],
                "tags": tags,
                "vibe": row["vibe"],
                "source": row["source"],
                "likes": row["likes"],
                "uses_count": row["uses_count"],
                "similarity": 0.85
            })
        return results

    async def like_meme(self, user_id: int, meme_id: int) -> Tuple[bool, int]:
        """Thả tim / bỏ tim meme. Trả về (is_liked, new_total_likes)."""
        db = await self.get_db()
        cursor = await db.execute("SELECT 1 FROM meme_likes WHERE user_id = ? AND meme_id = ?", (user_id, meme_id))
        exists = await cursor.fetchone()

        if exists:
            await db.execute("DELETE FROM meme_likes WHERE user_id = ? AND meme_id = ?", (user_id, meme_id))
            await db.execute("UPDATE memes SET likes = MAX(0, likes - 1) WHERE id = ?", (meme_id,))
            is_liked = False
        else:
            now_str = datetime.now(timezone.utc).isoformat()
            await db.execute("INSERT INTO meme_likes (user_id, meme_id, created_at) VALUES (?, ?, ?)", (user_id, meme_id, now_str))
            await db.execute("UPDATE memes SET likes = likes + 1 WHERE id = ?", (meme_id,))
            is_liked = True

        await db.commit()
        cursor = await db.execute("SELECT likes FROM memes WHERE id = ?", (meme_id,))
        row = await cursor.fetchone()
        total_likes = row["likes"] if row else 0
        return is_liked, total_likes

    async def use_meme(self, meme_id: int) -> None:
        """Ghi nhận thêm 1 lượt sử dụng meme."""
        db = await self.get_db()
        await db.execute("UPDATE memes SET uses_count = uses_count + 1 WHERE id = ?", (meme_id,))
        await db.commit()

    async def get_random_meme(self) -> Optional[Dict[str, Any]]:
        """Lấy ngẫu nhiên 1 meme trong kho."""
        db = await self.get_db()
        cursor = await db.execute("""
            SELECT id, title, url, media_type, caption, tags, vibe, source, likes, uses_count
            FROM memes
            ORDER BY RANDOM()
            LIMIT 1
        """)
        row = await cursor.fetchone()
        if not row:
            return None
        tags = []
        try:
            tags = json.loads(row["tags"]) if row["tags"] else []
        except Exception:
            pass
        return {
            "id": row["id"],
            "title": row["title"],
            "url": row["url"],
            "media_type": row["media_type"],
            "caption": row["caption"],
            "tags": tags,
            "vibe": row["vibe"],
            "source": row["source"],
            "likes": row["likes"],
            "uses_count": row["uses_count"],
            "similarity": 1.0
        }

    async def get_stats(self) -> Dict[str, Any]:
        """Thống kê tổng quan kho Meme."""
        db = await self.get_db()
        cursor = await db.execute("SELECT COUNT(*) as total, SUM(likes) as total_likes, SUM(uses_count) as total_uses FROM memes")
        stat_row = await cursor.fetchone()

        cursor = await db.execute("""
            SELECT id, title, url, likes, uses_count
            FROM memes
            ORDER BY uses_count DESC, likes DESC
            LIMIT 5
        """)
        top_rows = await cursor.fetchall()
        top_memes = [
            {"id": r["id"], "title": r["title"], "likes": r["likes"], "uses": r["uses_count"]}
            for r in top_rows
        ]

        return {
            "total_memes": stat_row["total"] if stat_row and stat_row["total"] else 0,
            "total_likes": stat_row["total_likes"] if stat_row and stat_row["total_likes"] else 0,
            "total_uses": stat_row["total_uses"] if stat_row and stat_row["total_uses"] else 0,
            "top_memes": top_memes
        }
