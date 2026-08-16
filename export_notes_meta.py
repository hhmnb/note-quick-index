"""
未打标笔记元数据提取器 (完善版)
- 默认仅处理没有 tags 或 tags 为空的笔记
- 使用 --all 参数可处理全部笔记
- 输出文件保存到桌面上的「笔记快速索引产出」文件夹
- 纯 UTF-8 处理，异常自动跳过
- 笔记目录从 config.json 的 notes_folder 读取，兼容原硬编码兜底
"""
import os
import re
import json
import csv
import argparse
from pathlib import Path

# ── 读取配置，获取笔记目录 ──────────────────────────────
BASE_DIR = Path(__file__).parent
CONFIG_PATH = BASE_DIR / "config.json"
try:
    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
        config = json.load(f)
    NOTES_FOLDER = Path(config.get('notes_folder', '_inbox'))
    # 若 notes_folder 是相对路径，则相对于项目根目录解析
    if not NOTES_FOLDER.is_absolute():
        NOTES_FOLDER = BASE_DIR / NOTES_FOLDER
except Exception:
    # 配置读取失败时，回退到原来的硬编码 _inbox（保证兼容性）
    NOTES_FOLDER = BASE_DIR / "_inbox"

# 输出目录：桌面/笔记快速索引产出
OUTPUT_DIR = Path.home() / "Desktop" / "笔记快速索引产出"
OUTPUT_JSONL = OUTPUT_DIR / "untagged_notes_export.jsonl"
OUTPUT_CSV = OUTPUT_DIR / "untagged_notes_export.csv"

# ── 笔记目录即 notes_folder 指定的路径 ──────────────
INBOX_DIR = NOTES_FOLDER


def extract_meta(content: str, filename: str) -> dict:
    """从笔记内容中提取元数据"""
    meta = {}
    for line in content.splitlines():
        line = line.strip()
        if not line:
            continue
        # 匹配 **key**：value 或 **key**: value
        m = re.match(r'\*\*(.+?)\*\*[：:]\s*(.*)', line)
        if m:
            key = m.group(1).strip()
            value = m.group(2).strip()
            meta[key] = value

    note_id = meta.get('笔记ID', Path(filename).stem)
    title = meta.get('原主题') or meta.get('title') or Path(filename).stem

    # 解析 tags
    tags_str = meta.get('tags', '')
    tags = []
    if tags_str:
        tags = [t.strip('` ').strip() for t in tags_str.split('`') if t.strip('` ').strip()]

    # 解析 keywords
    keywords_str = meta.get('keywords', '')
    keywords = []
    if keywords_str:
        keywords = [kw.strip() for kw in keywords_str.split() if kw.strip()]

    return {
        "id": note_id,
        "file": filename,
        "title": title,
        "tags": tags,
        "keywords": keywords
    }


def has_tags(content: str) -> bool:
    """快速判断笔记是否已有有效标签"""
    m = re.search(r'\*\*tags\*\*[：:]\s*(.+)', content)
    if not m:
        return False
    value = m.group(1).strip()
    return bool(value)


def main():
    parser = argparse.ArgumentParser(description="提取未打标笔记的元数据")
    parser.add_argument("--all", action="store_true", help="处理全部笔记（默认只处理未打标的）")
    args = parser.parse_args()

    if not INBOX_DIR.exists():
        print(f"❌ 笔记目录不存在: {INBOX_DIR}")
        print("   请检查 config.json 中的 notes_folder 设置")
        return

    # 创建输出目录
    try:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        print(f"❌ 无法创建输出目录 {OUTPUT_DIR}: {e}")
        return

    files = sorted(INBOX_DIR.glob("*.md"))
    print(f"📂 找到 {len(files)} 个笔记文件")
    if not args.all:
        print("📌 默认模式：仅提取【未打标签】的笔记")
    else:
        print("📌 全局模式：提取所有笔记")
    print(f"📁 输出目录: {OUTPUT_DIR}\n")

    success, skipped_tagged, fail = 0, 0, 0

    with open(OUTPUT_JSONL, 'w', encoding='utf-8') as jf, \
         open(OUTPUT_CSV, 'w', encoding='utf-8-sig', newline='') as cf:

        csv_writer = csv.DictWriter(cf, fieldnames=["id", "file", "title", "tags", "keywords"])
        csv_writer.writeheader()

        for i, fp in enumerate(files, 1):
            try:
                # 仅处理 UTF-8 文件，异常则跳过
                with open(fp, 'r', encoding='utf-8') as f:
                    content = f.read()

                # 如果不是 --all 模式，且笔记已有标签，则跳过
                if not args.all and has_tags(content):
                    skipped_tagged += 1
                    continue

                meta = extract_meta(content, fp.name)

                # 写入 JSON Lines
                jf.write(json.dumps(meta, ensure_ascii=False) + '\n')

                # 写入 CSV
                csv_writer.writerow({
                    "id": meta["id"],
                    "file": meta["file"],
                    "title": meta["title"],
                    "tags": " | ".join(meta["tags"]),
                    "keywords": " ".join(meta["keywords"])
                })
                success += 1

                if i % 20 == 0:
                    print(f"  进度: {i}/{len(files)}")

            except UnicodeDecodeError:
                print(f"  ⚠️ 跳过 {fp.name}：非 UTF-8 编码")
                fail += 1
            except Exception as e:
                print(f"  ⚠️ 跳过 {fp.name}: {e}")
                fail += 1

    print(f"\n✅ 完成！")
    print(f"   成功提取: {success}")
    if not args.all:
        print(f"   跳过已打标: {skipped_tagged}")
    print(f"   失败/跳过: {fail}")
    print(f"📁 JSON Lines: {OUTPUT_JSONL}")
    print(f"📁 CSV: {OUTPUT_CSV}")


if __name__ == "__main__":
    main()