#!/usr/bin/env python3
"""
笔记处理管线 (最终优化版 - 仅重命名，不修改内容)
- 先扫描笔记，有待处理文件时才启动 DeepSeek 专家模式，避免空跑窗口
- 只处理文件名末尾带 & 且尚未添加分类前缀的 .md 文件
- 笔记目录从 config.json 的 notes_folder 读取
- 每批次处理前新建对话，保证上下文干净
- 批次大小由 config.json 的 switch_every 控制（不再硬编码）
阶段1：提取笔记元数据
阶段2：判断并自动完善 category_rules.json
阶段3：AI 生成分类编码 → 死循环解析 → 文件名添加前缀
"""
import time, json, shutil, re, sys
from pathlib import Path
from typing import List, Optional

BASE_DIR = Path(__file__).parent
BACKUP_DIR = BASE_DIR / "_backup"
RULES_FILE = BASE_DIR / "category_rules.json"
TEMP_DIR = BASE_DIR / "_temp"

# 以下 BATCH_SIZE 仅为占位符，实际值将在 main() 中根据 config 覆盖
BATCH_SIZE = 50

# ---------- 子模块 ----------
from deepseek_sender import DeepSeekWebSender

# ========== 通用工具 ==========
def load_config():
    with open(BASE_DIR / "config.json", 'r', encoding='utf-8') as f:
        return json.load(f)

def load_file(path: Path) -> str:
    return path.read_text(encoding='utf-8')

def backup_original(note_path: Path):
    BACKUP_DIR.mkdir(exist_ok=True)
    shutil.copy2(note_path, BACKUP_DIR / note_path.name)

def is_unprocessed(filepath: Path) -> bool:
    """
    判断笔记是否需要处理：
    - 必须是以 & 结尾的 .md 文件（例如 不动笔墨不读书&.md）
    - 如果文件名已经带有分类前缀（如 A01-、ZZ00- 等），说明已处理过，跳过
    """
    name = filepath.name
    if not (name.endswith("&.md") or name.endswith("&")):
        return False
    if re.match(r'^[A-Z]{1,2}\d{2}-', name):
        return False
    return True

def scan_unprocessed_notes() -> List[Path]:
    files = sorted(INBOX_DIR.glob("*.md"))
    return [f for f in files if is_unprocessed(f)]

def extract_keywords(content: str) -> str:
    m = re.search(r'\*\*keywords\*\*[：:]\s*(.+)', content)
    if m:
        return m.group(1).strip()
    words = re.findall(r'[\u4e00-\u9fa5]{2,4}', content[:200])
    return " ".join(words[:5])

def extract_json_from_reply(reply: str) -> Optional[dict]:
    m = re.search(r'```json\s*(.*?)\s*```', reply, re.DOTALL)
    if m:
        try: return json.loads(m.group(1))
        except: pass
    try: return json.loads(reply)
    except: return None

def extract_json_array_from_reply(reply: str) -> Optional[List[dict]]:
    m = re.search(r'```json\s*(.*?)\s*```', reply, re.DOTALL)
    if m:
        try:
            data = json.loads(m.group(1))
            if isinstance(data, list): return data
        except: pass
    m = re.search(r'\[.*\]', reply, re.DOTALL)
    if m:
        try:
            data = json.loads(m.group())
            if isinstance(data, list): return data
        except: pass
    return None

# ========== 阶段1：提取笔记信息 ==========
def extract_batch_info(batch: List[Path]) -> Path:
    TEMP_DIR.mkdir(exist_ok=True)
    output_file = TEMP_DIR / f"batch_info_{int(time.time())}.jsonl"
    with open(output_file, 'w', encoding='utf-8') as f:
        for fp in batch:
            try:
                content = fp.read_text(encoding='utf-8')
                title = fp.stem
                if len(title) >= 10 and title[4] == '-' and title[7] == '-':
                    title = title[11:] if len(title) > 11 else title
                if title.endswith("&"):
                    title = title[:-1]   # 仅用于 AI 理解，不保留 &
                keywords = extract_keywords(content)
                info = {
                    "id": fp.stem,
                    "file": fp.name,
                    "title": title,
                    "keywords": keywords
                }
                f.write(json.dumps(info, ensure_ascii=False) + '\n')
            except: pass
    print(f"  📊 阶段1完成：提取 {len(batch)} 篇笔记信息 → {output_file.name}")
    return output_file

# ========== 阶段2：判断规则 + 自动完善 ==========
def stage2_check_and_update_rules(sender, batch_info_file: Path) -> bool:
    judge_template = load_file(BASE_DIR / "判断模板.txt")
    dict_template = load_file(BASE_DIR / "字典模板.txt")
    rules_text = load_file(RULES_FILE)
    batch_text = load_file(batch_info_file)[:6000]

    print("  🤖 发送“判断模板”...")
    judge_prompt = judge_template.replace('{rules}', rules_text).replace('{samples}', batch_text)
    judge_reply = sender.send(judge_prompt)
    if not judge_reply:
        judge_reply = "否"
    if judge_reply.strip().lower().startswith("是"):
        print("  ✅ 规则足够，跳过完善")
        return True

    print("  ⚠️ 规则不足，发送“字典模板”完善...")
    dict_prompt = dict_template.replace('{rules}', rules_text).replace('{samples}', batch_text)
    dict_reply = sender.send(dict_prompt)
    if not dict_reply:
        print("  ❌ AI 未返回新规则，使用旧规则继续")
        return True

    new_rules = extract_json_from_reply(dict_reply)
    if not new_rules or 'main_categories' not in new_rules:
        print("  ❌ 新规则解析失败，使用旧规则继续")
        return True

    backup_path = RULES_FILE.with_suffix(".json.bak")
    shutil.copy2(RULES_FILE, backup_path)
    RULES_FILE.write_text(json.dumps(new_rules, ensure_ascii=False, indent=2), encoding='utf-8')
    print("  ✅ 规则已更新")
    return True

# ========== 阶段3：死循环匹配 + 重命名 ==========
def stage3_generate_and_apply(sender, batch_info_file: Path, batch: List[Path]) -> dict:
    stats = {"success": 0, "skipped": 0, "failed": 0}
    match_template = load_file(BASE_DIR / "生成匹配.txt")
    rules_text = load_file(RULES_FILE)
    batch_text = load_file(batch_info_file)[:6000]

    base_prompt = match_template.replace('{rules}', rules_text).replace('{samples}', batch_text)
    print("  🤖 发送“生成匹配”请求...")

    attempt = 0
    mapping = None
    current_prompt = base_prompt
    while True:
        attempt += 1
        reply = sender.send(current_prompt)
        if not reply:
            print(f"    ⚠️ 第{attempt}次未收到回复，重试...")
            time.sleep(5)
            continue
        mapping = extract_json_array_from_reply(reply)
        if mapping and len(mapping) > 0:
            print(f"    ✅ 第{attempt}次成功，获取 {len(mapping)} 条匹配数据")
            break
        print(f"    ❌ 第{attempt}次解析失败，强化指令后重试...")
        current_prompt = base_prompt + "\n\n【强制】只输出JSON数组，不要任何解释。格式：[{\"id\":\"...\",\"main_code\":\"...\",\"sub_code\":\"...\",\"title\":\"...\"}]"
        time.sleep(3)

    rules = json.loads(rules_text)
    valid_codes = {item["code"] for item in rules["main_categories"]}
    for item in mapping:
        main_code = item.get("main_code", "ZZ")
        sub_code = item.get("sub_code", "00")
        if main_code not in valid_codes:
            item["main_code"] = "ZZ"
        if not (sub_code.isdigit() and len(sub_code) == 2):
            item["sub_code"] = "00"

    file_map = {fp.stem: fp for fp in batch}
    for item in mapping:
        note_id = item.get("id", "")
        main_code = item.get("main_code", "ZZ")
        sub_code = item.get("sub_code", "00")

        target = file_map.get(note_id)
        if not target:
            stats["failed"] += 1
            continue

        # 使用原始文件 stem（保留了 & 符号）
        safe_stem = re.sub(r'[\\/*?:"<>|]', '', target.stem)[:40]
        new_name = f"{main_code}{sub_code}-{safe_stem}.md"

        new_path = target.with_name(new_name)
        if new_path.exists():
            stats["skipped"] += 1
            continue
        try:
            target.rename(new_path)
            stats["success"] += 1
        except:
            stats["failed"] += 1
    print(f"  📊 阶段3完成：成功 {stats['success']}，跳过 {stats['skipped']}，失败 {stats['failed']}")
    return stats

# ========== 主流程（先扫描，有任务才启动专家模式） ==========
def main():
    global INBOX_DIR, BATCH_SIZE          # <-- 新增 global 声明，使 BATCH_SIZE 可被修改
    cfg = load_config()
    INBOX_DIR = Path(cfg["notes_folder"])
    # 用配置中的 switch_every 覆盖硬编码的 BATCH_SIZE（若缺失则保持默认 50）
    BATCH_SIZE = cfg.get("switch_every", BATCH_SIZE)

    sender = DeepSeekWebSender(
        empty_input_box=tuple(cfg["coordinates"]["empty_input_box"]),
        normal_input_box=tuple(cfg["coordinates"]["normal_input_box"]),
        copy_btn=tuple(cfg["coordinates"]["copy_btn"]),
        regen_btn=tuple(cfg["coordinates"]["regen_btn"]),
        new_chat_btn=tuple(cfg["coordinates"]["new_chat_btn"]),
        expert_btn=tuple(cfg["coordinates"]["expert_btn"]),
        max_retries_per_note=cfg.get("max_retries_per_note", 2),
        poll_interval=cfg.get("poll_interval", 5),
        initial_silent_wait=cfg.get("initial_silent_wait", 20),
        total_timeout=cfg.get("total_timeout", 600),
    )

    print(f"⚙️  批次大小: {BATCH_SIZE} 篇/批")    # 可选：显示当前批次设置
    print("🚀 启动笔记处理管线（仅重命名，不修改内容）")

    while True:
        unprocessed = scan_unprocessed_notes()
        if not unprocessed:
            print("✅ 所有笔记已处理完毕")
            break

        # 只有发现待处理笔记时才首次创建专家对话（或每轮开始前创建）
        sender.new_chat_with_expert()

        print(f"📄 发现 {len(unprocessed)} 篇未处理笔记")
        for start in range(0, len(unprocessed), BATCH_SIZE):
            batch = unprocessed[start:start + BATCH_SIZE]
            print(f"\n🔹 批次 {start//BATCH_SIZE + 1} ({len(batch)} 篇)")

            info_file = extract_batch_info(batch)
            if not stage2_check_and_update_rules(sender, info_file):
                print("  ❌ 阶段2失败，跳过本批")
                continue
            stage3_generate_and_apply(sender, info_file, batch)

            if start + BATCH_SIZE < len(unprocessed):
                time.sleep(5)
        print("😴 本轮结束，休息10秒...")
        time.sleep(10)

if __name__ == "__main__":
    main()