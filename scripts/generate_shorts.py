#!/usr/bin/env python3
"""
مولد يوتيوب شورتس عمودي باللغة العربية
- عناوين من topics/topics.txt
- سكريبت بـ Gemini
- صوت + Captions بـ edge-tts
- ترجمة كلمات مفتاحية لـ Pexels
- صور من Pexels
- فيديو عمودي 1080x1920 + Captions محروقة
- Thumbnail تلقائي
"""

import os
import sys
import json
import re
import subprocess
import requests
from pathlib import Path
from datetime import datetime

# ==================== الإعدادات ====================
OUTPUT_DIR = Path("output")
TOPICS_FILE = Path("topics/topics.txt")
DONE_FILE = Path("topics/done.txt")
MAX_VIDEOS_PER_RUN = int(os.getenv("MAX_VIDEOS", "3"))
VOICE = os.getenv("ARABIC_VOICE", "ar-EG-SalmaNeural")
VIDEO_WIDTH = 1080
VIDEO_HEIGHT = 1920

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY", "")

# ==================== أدوات مساعدة ====================
def log(msg: str):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def run_cmd(cmd: list, check=True):
    log(f"تشغيل: {' '.join(str(c) for c in cmd[:7])}...")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if check and result.returncode != 0:
        log(f"خطأ: {result.stderr[:600]}")
        raise RuntimeError(f"Command failed: {cmd[0]}")
    return result


def ensure_dirs():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    Path("temp").mkdir(exist_ok=True)
    Path("topics").mkdir(exist_ok=True)


def read_pending_topics(limit: int = 3) -> list[str]:
    if not TOPICS_FILE.exists():
        log("ملف topics.txt مش موجود!")
        return []
    topics = []
    with open(TOPICS_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                topics.append(line)
    return topics[:limit]


def mark_as_done(title: str):
    with open(DONE_FILE, "a", encoding="utf-8") as f:
        f.write(f"{title}\n")
    if TOPICS_FILE.exists():
        lines = TOPICS_FILE.read_text(encoding="utf-8").splitlines()
        new_lines = [l for l in lines if l.strip() != title]
        TOPICS_FILE.write_text("\n".join(new_lines) + "\n", encoding="utf-8")


# ==================== Gemini helpers ====================
def call_gemini(prompt: str) -> str:
    if not GEMINI_API_KEY:
        return ""
    try:
        import google.generativeai as genai
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel("gemini-2.0-flash")
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        log(f"Gemini error: {e}")
        return ""


# ==================== توليد السكريبت ====================
def generate_script(title: str) -> str:
    if not GEMINI_API_KEY:
        log("مفيش GEMINI_API_KEY → سكريبت بسيط بالعامية")
        return (
            f"يا جماعة النهاردة هنتكلم عن {title}. "
            f"الموضوع ده مهم أوي ولازم تعرفه. "
            f"أول حاجة: ركز على الأساسيات كويس. "
            f"تاني حاجة: طبق اللي بتتعلمه على طول. "
            f"تالت حاجة: استمر كل يوم شوية شوية. "
            f"لو الفيديو عجبك اعمل لايك واشترك في القناة. شكراً ليك!"
        )

    prompt = f"""
اكتب سكريبت يوتيوب شورتس بالعامية المصرية 100% (لهجة مصرية صريحة زي كلام الشارع والمحتوى المصري على يوتيوب).

العنوان: {title}

شروط مهمة جداً:
- العامية المصرية فقط، ممنوع الفصحى أو اللهجة البيضاء
- استخدم كلمات زي: النهاردة، أوي، كده، عايز، هتعمل، مش، يعني، بص، يا جماعة، خليني أقولك...
- جمل قصيرة وواضحة وسهلة النطق
- المدة: حوالي 40-50 ثانية لما تتقرأ بصوت طبيعي
- ابدأ بـ Hook قوي من أول جملة
- خلص بدعوة للتفاعل (لايك + اشتراك) بالعامية
- ممنوع الإيموجي
- ممنوع أي شرح أو عناوين فرعية
- اكتب النص جاهز للقراءة مباشرة بدون مقدمات

أمثلة أسلوب مطلوب:
"يا جماعة بصوا، الموضوع ده مهم أوي..."
"خليني أقولك حاجة هتغير نظرتك تماماً..."
"لو عملت الخطوة دي هتشوف فرق كبير..."

اكتب السكريبت بالعامية المصرية فقط:
"""
    script = call_gemini(prompt)
    if not script:
        return (
            f"يا جماعة النهاردة هنتكلم عن {title}. "
            f"الموضوع ده مهم أوي وهيفرق معاك. "
            f"أول حاجة ركز كويس على الأساسيات. "
            f"تاني حاجة طبق اللي بتتعلمه فوراً. "
            f"وآخر حاجة استمر كل يوم شوية. "
            f"لو الفيديو عجبك اعمل لايك واشترك. شكراً ليك!"
        )
    for bad in ["السكريبت:", "النص:", "```", "العامية:", "السكريبت بالعامية:"]:
        script = script.replace(bad, "")
    log(f"تم توليد السكريبت بالعامية ({len(script)} حرف)")
    return script.strip()


# ==================== ترجمة كلمات مفتاحية لـ Pexels ====================
def translate_keywords_for_pexels(title: str) -> str:
    """يترجم العنوان العربي لكلمات إنجليزية مناسبة لبحث Pexels"""
    if not GEMINI_API_KEY:
        # fallback بسيط
        return "motivation success lifestyle abstract nature"

    prompt = f"""
Translate this Arabic YouTube Shorts title into 3-5 English keywords optimized for searching stock photos on Pexels.
Return ONLY the keywords separated by spaces, nothing else. No quotes, no explanation.

Title: {title}
"""
    result = call_gemini(prompt)
    if not result:
        return "motivation success lifestyle abstract"
    # تنظيف
    result = re.sub(r'[^\w\s\-]', '', result)
    keywords = " ".join(result.split()[:6])
    log(f"كلمات Pexels: {keywords}")
    return keywords or "motivation success lifestyle"


# ==================== صوت + ترجمات ====================
def generate_audio_and_subs(script: str, audio_path: Path, srt_path: Path) -> tuple[Path, Path]:
    import edge_tts
    import asyncio

    async def _tts():
        # rate أبطأ شوية عشان النطق يكون أوضح بالعامية المصرية
        communicate = edge_tts.Communicate(script, VOICE, rate="-5%", pitch="+0Hz")
        await communicate.save(str(audio_path), str(srt_path))

    log(f"توليد الصوت والترجمات ({VOICE})...")
    asyncio.run(_tts())

    if not audio_path.exists() or audio_path.stat().st_size < 1000:
        raise RuntimeError("فشل توليد الصوت")

    if not srt_path.exists() or srt_path.stat().st_size < 50:
        log("إنشاء ترجمات بسيطة...")
        create_simple_srt(script, audio_path, srt_path)

    return audio_path, srt_path


def create_simple_srt(script: str, audio_path: Path, srt_path: Path):
    duration = get_audio_duration(audio_path)
    sentences = re.split(r'[.؟!]\s*', script)
    sentences = [s.strip() for s in sentences if s.strip()]
    if not sentences:
        sentences = [script]

    seg_dur = duration / len(sentences)
    lines = []
    for i, sent in enumerate(sentences):
        start = i * seg_dur
        end = (i + 1) * seg_dur
        lines.append(f"{i+1}")
        lines.append(f"{format_ts(start)} --> {format_ts(end)}")
        lines.append(sent)
        lines.append("")
    srt_path.write_text("\n".join(lines), encoding="utf-8")


def format_ts(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def get_audio_duration(audio_path: Path) -> float:
    result = run_cmd([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(audio_path)
    ])
    return float(result.stdout.strip())


# ==================== SRT → ASS ====================
def srt_to_styled_ass(srt_path: Path, ass_path: Path):
    content = srt_path.read_text(encoding="utf-8")

    header = """[Script Info]
Title: Arabic Shorts Captions
ScriptType: v4.00+
WrapStyle: 0
ScaledBorderAndShadow: yes
YCbCr Matrix: TV.709
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Noto Sans Arabic,72,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,4,2,2,60,60,180,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    events = []
    blocks = re.split(r'\n\s*\n', content.strip())
    for block in blocks:
        lines = block.strip().splitlines()
        if len(lines) < 3:
            continue
        time_line = lines[1]
        if "-->" not in time_line:
            continue
        start_str, end_str = [t.strip() for t in time_line.split("-->")]
        text = " ".join(lines[2:]).strip()
        start_ass = srt_time_to_ass(start_str)
        end_ass = srt_time_to_ass(end_str)
        text = text.replace("\n", "\\N")
        events.append(f"Dialogue: 0,{start_ass},{end_ass},Default,,0,0,0,,{text}")

    ass_path.write_text(header + "\n".join(events), encoding="utf-8")
    log(f"تم إنشاء ASS: {ass_path.name}")


def srt_time_to_ass(srt_time: str) -> str:
    srt_time = srt_time.replace(",", ".")
    parts = srt_time.split(":")
    if len(parts) == 3:
        h, m, s = parts
        return f"{int(h)}:{m}:{s[:5]}"
    return srt_time


# ==================== صور Pexels ====================
def fetch_pexels_images(query: str, count: int = 5) -> list[Path]:
    images_dir = Path("temp/images")
    images_dir.mkdir(parents=True, exist_ok=True)
    saved = []

    if not PEXELS_API_KEY:
        log("مفيش PEXELS_API_KEY → خلفيات لونية")
        return create_color_backgrounds(count)

    # ترجمة الكلمات المفتاحية
    search_query = translate_keywords_for_pexels(query)
    headers = {"Authorization": PEXELS_API_KEY}

    try:
        url = "https://api.pexels.com/v1/search"
        params = {
            "query": search_query,
            "orientation": "portrait",
            "per_page": count + 2,
            "size": "large"
        }
        r = requests.get(url, headers=headers, params=params, timeout=20)
        r.raise_for_status()
        data = r.json()

        for i, photo in enumerate(data.get("photos", [])[:count]):
            img_url = photo["src"].get("large2x") or photo["src"].get("large")
            if not img_url:
                continue
            img_path = images_dir / f"img_{i}.jpg"
            img_data = requests.get(img_url, timeout=30).content
            img_path.write_bytes(img_data)
            saved.append(img_path)
            log(f"تم تحميل صورة {i+1}")

        if not saved:
            return create_color_backgrounds(count)
        return saved
    except Exception as e:
        log(f"خطأ Pexels: {e} → خلفيات لونية")
        return create_color_backgrounds(count)


def create_color_backgrounds(count: int = 5) -> list[Path]:
    from PIL import Image
    images_dir = Path("temp/images")
    images_dir.mkdir(parents=True, exist_ok=True)
    colors = [
        (20, 30, 60), (40, 20, 50), (10, 40, 40),
        (50, 20, 30), (25, 35, 55), (30, 25, 45)
    ]
    saved = []
    for i in range(count):
        img = Image.new("RGB", (VIDEO_WIDTH, VIDEO_HEIGHT), colors[i % len(colors)])
        path = images_dir / f"bg_{i}.jpg"
        img.save(path, quality=90)
        saved.append(path)
    return saved


# ==================== Thumbnail ====================
def generate_thumbnail(title: str, background_img: Path | None, output_path: Path):
    """يولّد thumbnail جذاب 1080x1920 مع العنوان"""
    from PIL import Image, ImageDraw, ImageFont

    # خلفية
    if background_img and background_img.exists():
        img = Image.open(background_img).convert("RGB")
        img = img.resize((VIDEO_WIDTH, VIDEO_HEIGHT), Image.Resampling.LANCZOS)
    else:
        img = Image.new("RGB", (VIDEO_WIDTH, VIDEO_HEIGHT), (25, 35, 55))

    # طبقة شبه شفافة عشان النص يبان
    overlay = Image.new("RGBA", (VIDEO_WIDTH, VIDEO_HEIGHT), (0, 0, 0, 140))
    img = img.convert("RGBA")
    img = Image.alpha_composite(img, overlay)
    img = img.convert("RGB")

    draw = ImageDraw.Draw(img)

    # محاولة تحميل خط عربي
    font_paths = [
        "/usr/share/fonts/truetype/noto/NotoSansArabic-Bold.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansArabic-Regular.ttf",
        "/usr/share/fonts/opentype/noto/NotoSansArabic-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ]
    font = None
    for fp in font_paths:
        if Path(fp).exists():
            try:
                font = ImageFont.truetype(fp, 70)
                break
            except Exception:
                pass
    if font is None:
        font = ImageFont.load_default()

    # تقسيم العنوان لأسطر
    words = title.split()
    lines = []
    current = ""
    for w in words:
        test = (current + " " + w).strip()
        bbox = draw.textbbox((0, 0), test, font=font)
        if bbox[2] - bbox[0] < VIDEO_WIDTH - 120:
            current = test
        else:
            if current:
                lines.append(current)
            current = w
    if current:
        lines.append(current)

    # رسم النص في المنتصف
    total_h = len(lines) * 90
    y = (VIDEO_HEIGHT - total_h) // 2

    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        tw = bbox[2] - bbox[0]
        x = (VIDEO_WIDTH - tw) // 2
        # ظل
        draw.text((x + 3, y + 3), line, font=font, fill=(0, 0, 0))
        draw.text((x, y), line, font=font, fill=(255, 255, 255))
        y += 90

    img.save(output_path, quality=92)
    log(f"✅ Thumbnail: {output_path.name}")
    return output_path


# ==================== تركيب الفيديو + Captions ====================
def create_video(audio_path: Path, images: list[Path], ass_path: Path, output_path: Path):
    duration = get_audio_duration(audio_path)
    log(f"مدة الصوت: {duration:.1f} ثانية")

    if not images:
        images = create_color_backgrounds(3)
    num_images = len(images)
    seg_duration = duration / num_images

    # كليبات مع Zoom
    temp_clips = []
    for i, img in enumerate(images):
        clip_path = Path(f"temp/clip_{i}.mp4")
        zoom_filter = (
            f"scale=1200:2133,zoompan=z='min(zoom+0.0015,1.3)':"
            f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
            f"d={int(seg_duration*30)}:s={VIDEO_WIDTH}x{VIDEO_HEIGHT}:fps=30"
        )
        run_cmd([
            "ffmpeg", "-y", "-loop", "1", "-i", str(img),
            "-vf", zoom_filter,
            "-t", f"{seg_duration:.2f}",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "ultrafast",
            str(clip_path)
        ])
        temp_clips.append(clip_path)

    # دمج
    list_file = Path("temp/clips.txt")
    with open(list_file, "w") as f:
        for c in temp_clips:
            f.write(f"file '{c.absolute()}'\n")

    video_no_audio = Path("temp/video_no_audio.mp4")
    run_cmd([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(list_file),
        "-c", "copy", str(video_no_audio)
    ])

    # صوت + Captions
    vf = f"ass={ass_path}:fontsdir=/usr/share/fonts"
    run_cmd([
        "ffmpeg", "-y",
        "-i", str(video_no_audio),
        "-i", str(audio_path),
        "-vf", vf,
        "-c:v", "libx264", "-preset", "fast", "-crf", "22",
        "-c:a", "aac", "-b:a", "128k",
        "-shortest",
        "-pix_fmt", "yuv420p",
        str(output_path)
    ])

    log(f"✅ فيديو مع Captions: {output_path.name}")
    return output_path


# ==================== العملية الرئيسية ====================
def process_one_topic(title: str, index: int):
    log(f"\n{'='*50}")
    log(f"بدء: {title}")
    log(f"{'='*50}")

    safe_name = f"{index:02d}_{''.join(c if c.isalnum() or c in '-_' else '_' for c in title[:40])}"
    work_dir = Path("temp") / safe_name
    work_dir.mkdir(parents=True, exist_ok=True)

    # 1. سكريبت
    script = generate_script(title)
    (work_dir / "script.txt").write_text(script, encoding="utf-8")
    log(f"السكريبت:\n{script[:180]}...")

    # 2. صوت + SRT
    audio_path = work_dir / "audio.mp3"
    srt_path = work_dir / "subs.srt"
    generate_audio_and_subs(script, audio_path, srt_path)

    # 3. ASS
    ass_path = work_dir / "subs.ass"
    srt_to_styled_ass(srt_path, ass_path)

    # 4. صور (مع ترجمة كلمات مفتاحية)
    images = fetch_pexels_images(title, count=4)

    # 5. فيديو + Captions
    video_path = OUTPUT_DIR / f"{safe_name}.mp4"
    create_video(audio_path, images, ass_path, video_path)

    # 6. Thumbnail
    thumb_bg = images[0] if images else None
    thumb_path = OUTPUT_DIR / f"{safe_name}_thumb.jpg"
    generate_thumbnail(title, thumb_bg, thumb_path)

    # 7. Meta
    meta = {
        "title": title,
        "script": script,
        "voice": VOICE,
        "created_at": datetime.now().isoformat(),
        "video": video_path.name,
        "thumbnail": thumb_path.name,
        "has_captions": True
    }
    (OUTPUT_DIR / f"{safe_name}.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    mark_as_done(title)
    log(f"✅ خلص: {title}")
    return video_path


def main():
    ensure_dirs()
    log("🚀 مولد الشورتس العربي + Captions + Thumbnail")

    topics = read_pending_topics(MAX_VIDEOS_PER_RUN)
    if not topics:
        log("مفيش عناوين في topics/topics.txt")
        sys.exit(0)

    log(f"هيتولد {len(topics)} فيديو")
    success = 0
    for i, title in enumerate(topics, 1):
        try:
            process_one_topic(title, i)
            success += 1
        except Exception as e:
            log(f"❌ فشل '{title}': {e}")
            import traceback
            traceback.print_exc()

    log(f"\n🎉 تم: {success}/{len(topics)} فيديو")
    log(f"المجلد: {OUTPUT_DIR.absolute()}")


if __name__ == "__main__":
    main()
