"""
笔记元数据提取器 (最终完善版)
- 从 category_rules.json 加载分类规则，支持热修改
- 默认仅处理未打标签的笔记，跳过已有标签的笔记
- 使用 --all 参数可处理全部笔记
- 预设优先，动态覆盖未预定义分类
- 输出 notes_meta.jsonl 和 notes_meta.csv
- 笔记目录从 config.json 的 notes_folder 读取，兼容原硬编码兜底
"""
import os
import re
import json
import csv
import sys
import argparse
from pathlib import Path

BASE_DIR = Path(__file__).parent

# ── 读取配置，获取笔记目录 ──────────────────────────────
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

INBOX_DIR = NOTES_FOLDER
RULES_FILE = BASE_DIR / "category_rules.json"       # 分类规则文件
OUTPUT_JSONL = BASE_DIR / "notes_meta.jsonl"
OUTPUT_CSV = BASE_DIR / "notes_meta.csv"

# ========== 加载外部规则 ==========
def load_rules():
    """从 JSON 文件加载分类规则，返回 main_list 和 sub_preset"""
    if not RULES_FILE.exists():
        print(f"❌ 规则文件不存在: {RULES_FILE}")
        sys.exit(1)
    with open(RULES_FILE, 'r', encoding='utf-8') as f:
        rules = json.load(f)
    main_list = [item["name"] for item in rules["main_categories"]]
    sub_preset = {item["name"]: item["code"] for item in rules["sub_categories"]}
    return main_list, sub_preset, rules

# 初始化规则
MAIN_PRESET_LIST, SUB_PRESET, RULE_CONFIG = load_rules()

# ========== 辅助函数 ==========
def _num_to_alpha(n: int) -> str:
    """0→A, 25→Z, 26→AA..."""
    n += 1
    result = ""
    while n > 0:
        n, r = divmod(n - 1, 26)
        result = chr(65 + r) + result
    return result

def is_valid_title(title: str) -> bool:
    """过滤无效标题"""
    if not title or len(title) < 2:
        return False
    if "未命名" in title:
        return False
    if re.match(r'^\d{4}-\d{2}-\d{2}-', title):
        return False
    return True

def parse_note_meta(filepath: Path, content: str) -> dict:
    """解析笔记元数据（不含编码）"""
    meta = {}
    for line in content.splitlines():
        line = line.strip()
        if not line:
            continue
        match = re.match(r'\*\*(.+?)\*\*[：:]\s*(.*)', line)
        if match:
            key = match.group(1).strip()
            value = match.group(2).strip()
            meta[key] = value

    note_id = meta.get('笔记ID') or filepath.stem
    raw_title = meta.get('原主题') or meta.get('title') or ''
    title = raw_title if is_valid_title(raw_title) else filepath.stem
    if title == filepath.stem:
        title = re.sub(r'^\d{4}-\d{2}-\d{2}-', '', title)

    tags_str = meta.get('tags', '')
    tags = []
    if tags_str:
        tags = [t.strip('` ').strip() for t in tags_str.split('`') if t.strip('` ').strip()]

    keywords_str = meta.get('keywords', '')
    keywords = []
    if keywords_str:
        keywords = [kw.strip() for kw in keywords_str.split() if kw.strip()]

    return {
        "id": note_id,
        "file": filepath.name,
        "title": title,
        "tags": tags,
        "keywords": keywords,
    }

# ========== 分类编码构建 ==========
def collect_all_categories(files: list) -> tuple[set, set]:
    """扫描所有文件，收集一级和二级分类"""
    main_set = set()
    sub_set = set()
    for f in files:
        try:
            with open(f, 'r', encoding='utf-8') as fh:
                content = fh.read()
        except:
            continue
        meta = parse_note_meta(f, content)
        for tag in meta['tags']:
            parts = tag.split('/')
            if parts[0]:
                main_set.add(parts[0])
            if len(parts) > 1 and parts[1]:
                sub_set.add(parts[1])
    return main_set, sub_set

def build_code_maps(main_set: set, sub_set: set) -> tuple[dict, dict]:
    """生成字母板块码和数字细分码映射"""
    main_map = {}
    used_alpha = set()
    # 预设优先
    for i, cat in enumerate(MAIN_PRESET_LIST):
        code = _num_to_alpha(i)
        main_map[cat] = code
        used_alpha.add(code)

    # 动态分配（按规则控制）
    if RULE_CONFIG.get("auto_assign_dynamic", True):
        next_idx = len(MAIN_PRESET_LIST)
        for cat in sorted(main_set - set(MAIN_PRESET_LIST)):
            while True:
                code = _num_to_alpha(next_idx)
                next_idx += 1
                if code not in used_alpha:
                    break
            main_map[cat] = code
            used_alpha.add(code)
    else:
        default_main = RULE_CONFIG.get("default_main_code", "ZZ")
        for cat in main_set - set(MAIN_PRESET_LIST):
            main_map[cat] = default_main

    # 细分码
    sub_map = {}
    used_digits = set(SUB_PRESET.values())
    for k, v in SUB_PRESET.items():
        sub_map[k] = v

    if RULE_CONFIG.get("auto_assign_dynamic", True):
        next_num = max([int(v) for v in SUB_PRESET.values()]) + 1 if SUB_PRESET else 1
        for sub in sorted(sub_set - set(SUB_PRESET.keys())):
            while True:
                code = f"{next_num:02d}"
                next_num += 1
                if code not in used_digits and int(code) <= 99:
                    break
            sub_map[sub] = code
            used_digits.add(code)
    else:
        default_sub = RULE_CONFIG.get("default_sub_code", "00")
        for sub in sub_set - set(SUB_PRESET.keys()):
            sub_map[sub] = default_sub

    return main_map, sub_map

# ========== 主流程 ==========
def main():
    parser = argparse.ArgumentParser(description="提取笔记元数据")
    parser.add_argument("--all", action="store_true", help="处理全部笔记（默认跳过已打标签）")
    args = parser.parse_args()

    if not INBOX_DIR.exists():
        print(f"❌ 笔记目录不存在: {INBOX_DIR}")
        print("   请检查 config.json 中的 notes_folder 设置")
        sys.exit(1)

    files = sorted(INBOX_DIR.glob("*.md"))
    print(f"📂 扫描目录: {INBOX_DIR}")
    print(f"📄 发现 {len(files)} 个文件")

    # 收集全部分类
    main_set, sub_set = collect_all_categories(files)
    main_map, sub_map = build_code_maps(main_set, sub_set)
    print(f"🔖 一级分类: {len(main_set)} 个，二级分类: {len(sub_set)} 个\n")

    success = 0
    skipped_tagged = 0
    fail = 0

    with open(OUTPUT_JSONL, 'w', encoding='utf-8') as jf:
        csv_f = open(OUTPUT_CSV, 'w', encoding='utf-8-sig', newline='')
        writer = csv.DictWriter(csv_f, fieldnames=[
            "id", "file", "title", "tags", "keywords",
            "main_category", "sub_category", "main_code", "sub_code"
        ])
        writer.writeheader()

        for f in files:
            try:
                with open(f, 'r', encoding='utf-8') as fh:
                    content = fh.read()
                meta = parse_note_meta(f, content)

                # 跳过已打标笔记
                if not args.all and meta['tags']:
                    skipped_tagged += 1
                    continue

                # 编码
                main_cat = ''
                sub_cat = ''
                m_code = RULE_CONFIG.get("default_main_code", "ZZ")
                s_code = RULE_CONFIG.get("default_sub_code", "00")
                if meta['tags']:
                    first_tag = meta['tags'][0]
                    parts = first_tag.split('/')
                    main_cat = parts[0]
                    m_code = main_map.get(main_cat, m_code)
                    if len(parts) > 1:
                        sub_cat = parts[1]
                        s_code = sub_map.get(sub_cat, s_code)

                row = {
                    "id": meta["id"],
                    "file": meta["file"],
                    "title": meta["title"],
                    "tags": " | ".join(meta["tags"]),
                    "keywords": " ".join(meta["keywords"]),
                    "main_category": main_cat,
                    "sub_category": sub_cat,
                    "main_code": m_code,
                    "sub_code": s_code,
                }
                jf.write(json.dumps(row, ensure_ascii=False) + '\n')
                writer.writerow(row)
                success += 1

            except Exception as e:
                print(f"❌ {f.name}: {e}")
                fail += 1

        csv_f.close()

    print(f"\n✅ 完成！成功提取: {success}, 跳过已打标: {skipped_tagged}, 失败: {fail}")
    print(f"📁 {OUTPUT_JSONL}")
    print(f"📁 {OUTPUT_CSV}")

    # 编码表摘要
    print("\n📋 当前板块编码表 (部分):")
    for cat in sorted(main_map, key=lambda x: main_map[x]):
        print(f"  {main_map[cat]}: {cat}")

if __name__ == "__main__":
    main()