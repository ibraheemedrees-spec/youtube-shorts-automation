#!/usr/bin/env python3
"""
مولد يوتيوب شورتس عمودي باللغة العربية + Captions
- يقرأ العناوين من topics/topics.txt
- يكتب سكريبت قصير بـ Gemini
- يحول النص لصوت بـ edge-tts (عربي) + يولد ترجمات
- يجيب صور من Pexels
- يركب فيديو عمودي 1080x1920 بـ FFmpeg مع Captions محروقة
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
VOICE = os.getenv("ARABIC_VOICE", "ar-EG-SalmaNeural")  # أو ar-SA-HamedNeural
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


# ==================== توليد السكريبت ====================
def generate_script(title: str) -> str:
    """يولد سكريبت قصير جذاب بالعربية باستخدام Gemini"""
    if not GEMINI_API_KEY:
        log("مفيش GEMINI_API_KEY → استخدام سكريبت بسيط")
        return (
            f"مرحباً! النهاردة هنتكلم عن {title}. "
            f"دي معلومة مهمة جداً لازم تعرفها. "
            f"النقطة الأولى: ركز على الأساسيات. "
            f"النقطة التانية: طبق اللي تتعلمه فوراً. "
            f"النقطة التالتة: استمر كل يوم شوية. "
            f"لو الفيديو عجبك اعمل لايك واشترك في القناة. شكراً لمشاهدتك!"
        )

    try:
        import google.generativeai as genai
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel("gemini-2.0-flash")

        prompt = f"""
اكتب سكريبت يوتيوب شورتس باللغة العربية الفصحى السهلة (لهجة بيضاء مفهومة).

العنوان: {title}

الشروط:
- المدة المستهدفة: 40 إلى 50 ثانية عند القراءة بصوت طبيعي
- ابدأ بـ Hook قوي في أول جملة يجذب الانتباه
- استخدم جمل قصيرة وواضحة
- انتهى بدعوة للتفاعل (لايك + اشتراك)
- لا تستخدم إيموجي
- لا تكتب عناوين فرعية أو أرقام فقط، اكتب نص متسلسل جاهز للقراءة
- اكتب النص فقط بدون أي مقدمات أو شرح

السكريبت:
"""
        response = model.generate_content(prompt)
        script = response.text.strip()
        for bad in ["السكريبت:", "النص:", "```"]:
            script = script.replace(bad, "")
        log(f"تم توليد السكريبت ({len(script)} حرف)")
        return script.strip()
    except Exception as e:
        log(f"خطأ في Gemini: {e} → استخدام سكريبت احتياطي")
        return (
            f"مرحباً بكم! موضوعنا النهاردة: {title}. "
            f"هشارك معاكم أهم النقاط اللي محتاج تعرفها. "
            f"النصيحة الأهم هي الاستمرارية والتطبيق العملي. "
            f"جرب الفكرة دي النهاردة وشوف الفرق بنفسك. "
            f"لو استفدت اعمل لايك واشترك عشان توصلك الحلقات الجاية."
        )


# ==================== تحويل النص لصوت + ترجمات ====================
def generate_audio_and_subs(script: str, audio_path: Path, srt_path: Path) -> tuple[Path, Path]:
    """يولّد الصوت + ملف SRT باستخدام edge-tts"""
    import edge_tts
    import asyncio

    async def _tts():
        communicate = edge_tts.Communicate(script, VOICE, rate="+5%")
        await communicate.save(str(audio_path), str(srt_path))

    log(f"توليد الصوت والترجمات بصوت {VOICE}...")
    asyncio.run(_tts())

    if not audio_path.exists() or audio_path.stat().st_size < 1000:
        raise RuntimeError("فشل توليد الصوت")

    # لو الـ SRT مش اتعمل، نعمل واحد بسيط
    if not srt_path.exists() or srt_path.stat().st_size < 50:
        log("إنشاء ترجمات بسيطة يدوياً...")
        create_simple_srt(script, audio_path, srt_path)

    log(f"تم حفظ الصوت والترجمات")
    return audio_path, srt_path


def create_simple_srt(script: str, audio_path: Path, srt_path: Path):
    """إنشاء SRT بسيط لو edge-tts ما ولدش ترجمات"""
    duration = get_audio_duration(audio_path)
    # تقسيم السكريبت لجمل
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


# ==================== تحويل SRT إلى ASS (أفضل للعربية) ====================
def srt_to_styled_ass(srt_path: Path, ass_path: Path):
    """يحول SRT إلى ASS مع تنسيق جميل مناسب للشورتس + دعم عربي"""
    content = srt_path.read_text(encoding="utf-8")

    # تنسيق ASS احترافي للشورتس (نص كبير في النص السفلي)
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
        # السطر الثاني فيه التوقيت
        time_line = lines[1]
        if "-->" not in time_line:
            continue
        start_str, end_str = [t.strip() for t in time_line.split("-->")]
        text = " ".join(lines[2:]).strip()

        # تحويل توقيت SRT إلى ASS
        start_ass = srt_time_to_ass(start_str)
        end_ass = srt_time_to_ass(end_str)

        # تنظيف النص
        text = text.replace("\n", "\\N")
        events.append(f"Dialogue: 0,{start_ass},{end_ass},Default,,0,0,0,,{text}")

    ass_path.write_text(header + "\n".join(events), encoding="utf-8")
    log(f"تم إنشاء ملف ASS منسق: {ass_path}")


def srt_time_to_ass(srt_time: str) -> str:
    """00:00:01,500 → 0:00:01.50"""
    srt_time = srt_time.replace(",", ".")
    parts = srt_time.split(":")
    if len(parts) == 3:
        h, m, s = parts
        return f"{int(h)}:{m}:{s[:5]}"  # دقتتين للثواني العشرية
    return srt_time


# ==================== صور من Pexels ====================
def fetch_pexels_images(query: str, count: int = 5) -> list[Path]:
    images_dir = Path("temp/images")
    images_dir.mkdir(parents=True, exist_ok=True)
    saved = []

    if not PEXELS_API_KEY:
        log("مفيش PEXELS_API_KEY → استخدام خلفيات لونية")
        return create_color_backgrounds(count)

    headers = {"Authorization": PEXELS_API_KEY}
    search_query = query if any(ord(c) < 128 for c in query) else "motivation success lifestyle abstract"

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


# ==================== تركيب الفيديو + Captions ====================
def create_video(title: str, audio_path: Path, images: list[Path], ass_path: Path, output_path: Path):
    """يركب فيديو عمودي + يحرق الـ Captions"""
    duration = get_audio_duration(audio_path)
    log(f"مدة الصوت: {duration:.1f} ثانية")

    num_images = max(len(images), 1)
    if not images:
        images = create_color_backgrounds(3)
        num_images = 3

    seg_duration = duration / num_images

    # 1. عمل كليبات من الصور مع تأثير Zoom
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

    # 2. دمج الكليبات
    list_file = Path("temp/clips.txt")
    with open(list_file, "w") as f:
        for c in temp_clips:
            f.write(f"file '{c.absolute()}'\n")

    video_no_audio = Path("temp/video_no_audio.mp4")
    run_cmd([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(list_file),
        "-c", "copy", str(video_no_audio)
    ])

    # 3. إضافة الصوت + حرق الـ Captions (ASS)
    # نستخدم force_style للتأكد من الخط العربي
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

    log(f"✅ تم إنشاء الفيديو مع Captions: {output_path}")
    return output_path


# ==================== العملية الرئيسية ====================
def process_one_topic(title: str, index: int):
    log(f"\n{'='*50}")
    log(f"بدء معالجة: {title}")
    log(f"{'='*50}")

    safe_name = f"{index:02d}_{''.join(c if c.isalnum() or c in '-_' else '_' for c in title[:40])}"
    work_dir = Path("temp") / safe_name
    work_dir.mkdir(parents=True, exist_ok=True)

    # 1. السكريبت
    script = generate_script(title)
    script_file = work_dir / "script.txt"
    script_file.write_text(script, encoding="utf-8")
    log(f"السكريبت:\n{script[:200]}...")

    # 2. الصوت + ترجمات
    audio_path = work_dir / "audio.mp3"
    srt_path = work_dir / "subs.srt"
    generate_audio_and_subs(script, audio_path, srt_path)

    # 3. تحويل لـ ASS منسق
    ass_path = work_dir / "subs.ass"
    srt_to_styled_ass(srt_path, ass_path)

    # 4. الصور
    images = fetch_pexels_images(title, count=4)

    # 5. الفيديو + Captions
    output_path = OUTPUT_DIR / f"{safe_name}.mp4"
    create_video(title, audio_path, images, ass_path, output_path)

    # 6. حفظ معلومات
    meta = {
        "title": title,
        "script": script,
        "voice": VOICE,
        "created_at": datetime.now().isoformat(),
        "file": str(output_path.name),
        "has_captions": True
    }
    (OUTPUT_DIR / f"{safe_name}.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    mark_as_done(title)
    log(f"✅ انتهى: {title}")
    return output_path


def main():
    ensure_dirs()
    log("🚀 بدء مولد الشورتس العربي + Captions")

    topics = read_pending_topics(MAX_VIDEOS_PER_RUN)
    if not topics:
        log("مفيش عناوين جديدة في topics/topics.txt")
        log("أضف عناوين (سطر واحد لكل عنوان) وشغّل تاني")
        sys.exit(0)

    log(f"هيتولد {len(topics)} فيديو")
    success = 0
    for i, title in enumerate(topics, 1):
        try:
            process_one_topic(title, i)
            success += 1
        except Exception as e:
            log(f"❌ فشل في '{title}': {e}")
            import traceback
            traceback.print_exc()

    log(f"\n🎉 تم بنجاح: {success}/{len(topics)} فيديو")
    log(f"الملفات موجودة في مجلد: {OUTPUT_DIR.absolute()}")


if __name__ == "__main__":
    main()
