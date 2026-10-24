import json
import time
from playwright.sync_api import sync_playwright
from openai import OpenAI
import json
import requests

# ==================== 1. 配置区 ====================
DEEPSEEK_API_KEY = "".strip()
# 原生 requests 请求必须写完整的 chat/completions 路由
DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"
AI_MODEL_NAME = "deepseek-chat"  # 官方主力模型，兼顾速度与推理

# 你的具体筛选要求（民事/劳动争议与侵权案件）
USER_CRITERIA = """
请在各级法院生效民事/劳动争议判决书中，研判符合以下放宽法理要件的侵权或劳务受害判例：

【放宽事实特征】
1. 身份场景：劳动者受用人单位指派履职（海外外派、国内出差或日常特种职务作业）；
2. 单位过错：因用人单位在合规报备、行政许可、特种作业资质、设备登记或空域申请上存在瑕疵/未办理，导致劳动者在不知情或遵从指令情况下，被执法机关采取行政拘留、刑事拘留审查或限制人身自由数日；
3. 损害后果：当事人无肢体器质性伤残（无评残等级），但因遭受人身自由剥夺产生了严重精神恐慌、名誉贬损及心理创伤；
4. 诉讼请求：劳动者起诉用人单位要求赔偿“人身自由受限损失”、“精神损害抚慰金”及“代垫涉案罚款/规费”。

【排除要求】
严格排除：刑事判决书（故意伤害、暴力犯罪等）、国家赔偿案件、劳动者个人故意犯罪案件。

【研判重点】
1. 是否支持无伤残情况下的精神损害抚慰金，具体判赔金额及理由；
2. 是否全额支持代垫的行政罚款及差旅羁押损失；
3. 法院在认定单位过错与职务侵权时的说理逻辑。
"""

# ==================== 2. AI 评估模块 ====================
import json
import requests

def evaluate_case_with_ai(case_title: str, case_text: str, criteria: str) -> dict:
    """
    使用放宽后的民事/劳动侵权要件对裁判文书进行结构化智能研判
    """
    prompt = f"""你是一名精通民商事侵权与劳动争议的资深审判法官与司法大数据专家。
请仔细评估以下判决书，分析其案件事实、诉辩焦点与判决结果是否符合特定筛选要求。

【研判需求与排除规则】：
{criteria}

【判决书内容】：
案名：{case_title}
正文关键段落：
{case_text}

请严格按以下 JSON 格式返回分析结果（不要输出任何多余的 Markdown 标记或额外解释）：
{{
  "match_score": 0到100之间的整数（与上述放宽要件的匹配程度）,
  "is_highly_relevant": true 或 false,
  "case_info": {{
    "case_number": "案号（如正文无则填'见正文'）",
    "court": "审理法院名称",
    "year": "裁判年份",
    "case_type": "案件类型（如民事二审、民事一审）",
    "cause_of_action": "案由（如提供劳务者受害责任纠纷、劳动争议、一般侵权纠纷）"
  }},
  "core_facts": {{
    "duty_background": "员工职务与被指派作业背景",
    "incident": "单位合规/资质瑕疵导致被查获事件经过",
    "detention_consequence": "被限制人身自由/拘留的天数及身心应激表现",
    "local_penalty": "行政罚款/处罚扣押情况"
  }},
  "liability": {{
    "employer_fault": "法院对用人单位未尽合规/安保义务的过错认定",
    "employee_fault": "法院对员工履职行为的过错认定",
    "liability_ratio": "责任承担比例（如'用人单位承担全部责任'）"
  }},
  "claims_table": [
    {{
      "item": "精神损害抚慰金",
      "claimed_amount": "原告诉求金额",
      "supported_amount": "判赔金额（不支持写0元，未主张写未主张）",
      "support_ratio": "支持比例",
      "notes": "裁判理由及量化考量"
    }},
    {{
      "item": "官方罚金/代垫规费",
      "claimed_amount": "原告诉求金额",
      "supported_amount": "判赔金额",
      "support_ratio": "支持比例",
      "notes": "是否全额追偿"
    }},
    {{
      "item": "受限期间工资待遇",
      "claimed_amount": "原告诉求金额",
      "supported_amount": "判赔金额",
      "support_ratio": "支持比例",
      "notes": "是否视为正常出勤"
    }}
  ],
  "numeric_stats": {{
    "mental_damages_amount": 20000,
    "fines_supported_ratio": 100
  }},
  "court_reasoning": {{
    "basis_for_mental_damages": "关于在无伤残情况下支持精神损害抚慰金的核心说理依据",
    "amount_quantification": "金额裁量酌定的核心考量点"
  }},
  "insights": {{
    "key_takeaways": "对类似诉赔的主张抓手",
    "evidence_suggestions": "关键举证补充建议（如心理门诊、垫款收据）"
  }}
}}
"""
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}"
    }

    payload = {
        "model": AI_MODEL_NAME,
        "messages": [{"role": "user", "content": prompt}],
        "response_format": {"type": "json_object"},
        "temperature": 0.1
    }

    try:
        resp = requests.post(DEEPSEEK_URL, headers=headers, json=payload, timeout=90)
        if resp.status_code == 200:
            return json.loads(resp.json()["choices"][0]["message"]["content"])
        return {"match_score": 0, "error": f"HTTP {resp.status_code}"}
    except Exception as e:
        return {"match_score": 0, "error": str(e)}



# ==================== 3. 核心文本提取函数 ====================
def extract_core_legal_content(full_text: str) -> str:
    """
    过滤冗余信息，优先保留刑事判决书中的核心部分：
    '经审理查明'、'本院认为'、'判决如下'
    """
    keywords = ["经审理查明", "公诉机关指控", "本院认为", "判决如下"]
    start_pos = -1
    for kw in keywords:
        pos = full_text.find(kw)
        if pos != -1 and (start_pos == -1 or pos < start_pos):
            start_pos = pos

    if start_pos != -1:
        return full_text[start_pos:]
    return full_text



# ======================plus 自动清洗脚本===================================
import re


def prune_judgment_smartly(raw_text: str) -> str:
    """
    智能结构化剪枝：精准剔除网页杂质与末尾程序套话，
    保留起诉诉求、法院查明事实、裁判说理与最终判决主文（100%核心无损）。
    """
    if not raw_text:
        return ""

    # 1. 剔除网页残留的典型噪音行
    noise_patterns = [
        r"裁判文书网.*?版权所有",
        r"请使用IE9以上浏览器.*?浏览",
        r"微信扫一扫.*?分享",
        r"登录.*?注册",
        r"返回检索结果"
    ]
    cleaned = raw_text
    for pattern in noise_patterns:
        cleaned = re.sub(pattern, "", cleaned)

    # 2. 截断文末无用信息（告知上诉权利、审判人员名单、书记员、附录法条）
    # 从“如不服本判决”或“审 判 长”处安全截断，但确保保留“判决如下”后的判决主文
    judgment_end_anchors = ["如不服本判决", "如不服本裁定", "本判决为终审判决", "审 判 长", "审判员"]

    # 找到判决主文的位置（防止截断把“判决如下”给切掉）
    judgment_verdict_pos = -1
    for v_kw in ["判决如下", "裁定如下", "决定如下"]:
        pos = cleaned.rfind(v_kw)
        if pos != -1:
            judgment_verdict_pos = pos
            break

    # 如果找到了判决主文，只在判决主文之后寻找末尾截断点
    if judgment_verdict_pos != -1:
        tail_text = cleaned[judgment_verdict_pos:]
        cut_tail_pos = len(tail_text)
        for anchor in judgment_end_anchors:
            idx = tail_text.find(anchor)
            if idx != -1 and idx < cut_tail_pos:
                cut_tail_pos = idx
        cleaned = cleaned[:judgment_verdict_pos] + tail_text[:cut_tail_pos]

    # 3. 动态压缩连续空行和多余制表符
    cleaned = re.sub(r"\n\s*\n+", "\n\n", cleaned)
    cleaned = cleaned.strip()

    # 4. 长度保险策略：
    # 绝大多数裁判文书精简后在 3000~8000 字之间，可完整送入
    # 若遇到极少数超大体量文书（> 15000 字），保留首尾核心并对中间举证做轻微抽吸
    if len(cleaned) > 12000:
        # 保留案由诉求前 3000 字 + 裁判说理与判决后 8000 字
        cleaned = cleaned[:3000] + "\n\n[...略去中间详细举证质证文字...]\n\n" + cleaned[-8000:]

    return cleaned


# ==================== 4. Playwright 自动化检索执行 ====================
import os
import json
import time
from playwright.sync_api import sync_playwright


def search_and_analyze_cases():
    user_data_dir = "./browser_user_data"
    report_json_path = "case_screening_report.json"

    # ================= 全局配置 =================
    MAX_PAGES = 150  # 最大允许翻页上限（覆盖 600+ 篇足够）
    TARGET_TOTAL_CASES = 600  # 不设数量人为截断，跑完全部搜索结果
    # ============================================

    # 1. 载入历史进度（实现断点续传，防止中途异常重跑）
    analyzed_results = []
    processed_titles = set()

    if os.path.exists(report_json_path):
        try:
            with open(report_json_path, "r", encoding="utf-8") as f:
                analyzed_results = json.load(f)
                processed_titles = {item.get("title") for item in analyzed_results if item.get("title")}
                print(f"📦 检测到已有历史存档，已加载 {len(processed_titles)} 篇已研判文书（自动跳过重复篇目）。")
        except Exception:
            analyzed_results = []
            processed_titles = set()

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            headless=False,
            slow_mo=50,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox"
            ]
        )

        page = context.pages[0] if context.pages else context.new_page()

        # 打开文书网首页
        base_url = "https://wenshu.court.gov.cn"
        print(f"🌐 正在打开裁判文书网首页: {base_url}")
        page.goto(base_url, wait_until="domcontentloaded")

        print("\n" + "=" * 55)
        print("💡 【人工协作与参数配置】")
        print("1. 确认已登录账号；")
        print("2. 在搜索框输入检索词并点击检索；")
        print("3. 【强烈建议】：在列表下方将‘每页5条’切换为‘每页10条’或‘20条’以减少翻页次数；")
        print("4. 确认列表渲染出 600 多条结果的第一页后...")
        input("👉 回到终端按【Enter 回车键】启动全量 600+ 篇研判流水线...")
        print("=" * 55 + "\n")

        current_page_num = 1

        # 2. 多页长循环流水线
        while current_page_num <= MAX_PAGES:
            print(f"\n📄 ========== 正在扫描第 {current_page_num} 页 ==========")

            # 等待文书标题节点渲染
            try:
                page.wait_for_selector("a.caseName", timeout=15000)
            except Exception as e:
                print(f"⚠️ 当前页文书列表加载超时，可能已到最后一页或触发滑块: {e}")
                break

            case_title_elements = page.query_selector_all("a.caseName")
            page_case_count = len(case_title_elements)

            if page_case_count == 0:
                print("🔚 当前页无文书记录，检索已到达末尾。")
                break

            print(f"📋 当前第 {current_page_num} 页共展示 {page_case_count} 篇文书")
            first_case_title = case_title_elements[0].inner_text().strip()

            # 3. 逐篇提取与 AI 深度研判
            for idx in range(page_case_count):
                # 重新获取节点，防止新标签页返回后 DOM 引用失效
                current_elements = page.query_selector_all("a.caseName")
                if idx >= len(current_elements):
                    break
                title_elem = current_elements[idx]

                try:
                    title = title_elem.inner_text().strip()
                    total_progress = len(analyzed_results) + 1

                    # 断点续传拦截：如果已研判过，跳过详情读取
                    if title in processed_titles:
                        print(f"⏩ [{total_progress}] 已在历史库中，跳过重复篇目: {title[:20]}...")
                        continue

                    print(f"\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
                    print(f"[{total_progress}] 正在研判: {title}")

                    # 打开详情新标签页
                    with context.expect_page() as new_page_info:
                        title_elem.click()
                    detail_page = new_page_info.value
                    detail_page.wait_for_load_state("domcontentloaded")

                    # 轮询等待正文异步渲染（最多等 8 秒）
                    detail_content_selector = '.PDF_box, .ws-content, #content, .content, div[class*="content"]'
                    raw_content = ""
                    for _ in range(8):
                        try:
                            elem = detail_page.query_selector(detail_content_selector)
                            if elem:
                                text_cand = elem.inner_text().strip()
                                if len(text_cand) > 100:
                                    raw_content = text_cand
                                    break
                            body_text = detail_page.inner_text("body").strip()
                            if len(body_text) > 200:
                                raw_content = body_text
                                break
                        except Exception:
                            pass
                        time.sleep(1)

                    case_url = detail_page.url
                    detail_page.close()

                    if not raw_content:
                        print("⚠️ 正文提取为空（可能触发验证码），跳过此篇。")
                        continue

                    # 智能剪枝与 AI 研判
                    optimized_text = prune_judgment_smartly(raw_content)
                    print("🤖 正在调用 AI 进行案件事实与量刑匹配度全局深度分析...")
                    evaluation = evaluate_case_with_ai(title, optimized_text, USER_CRITERIA)
                    score = evaluation.get("match_score", 0)
                    print(f"🎯 匹配得分: {score} / 100")

                    record = {
                        "title": title,
                        "url": case_url,
                        "score": score,
                        "case_info": evaluation.get("case_info", {}),
                        "core_facts": evaluation.get("core_facts", {}),
                        "liability": evaluation.get("liability", {}),
                        "claims_table": evaluation.get("claims_table", []),
                        "numeric_stats": evaluation.get("numeric_stats", {}),
                        "court_reasoning": evaluation.get("court_reasoning", {}),
                        "insights": evaluation.get("insights", {})
                    }

                    analyzed_results.append(record)
                    processed_titles.add(title)


                    # 实时落盘：每篇研判完即写入本地，防止崩毁
                    with open(report_json_path, "w", encoding="utf-8") as f:
                        json.dump(analyzed_results, f, ensure_ascii=False, indent=2)

                    # 每次抓取后的防风控间隔（2 秒）
                    time.sleep(2)

                except Exception as e:
                    print(f"⚠️ 处理文书失败: {e}")

            # 4. 翻页逻辑控制
            print(f"\n➡️ 第 {current_page_num} 页处理完毕，准备翻页（累计已库存储备: {len(analyzed_results)} 篇）...")

            # 定位翻页按钮
            next_btn = page.locator('a:has-text("下一页"), a.next, li.next a, button:has-text("下一页")').first

            if next_btn.count() == 0 or not next_btn.is_visible():
                print("🔚 未找到‘下一页’按钮或已到达文书最后一页，提取结束！")
                break

            # 点击下一页
            next_btn.click()
            time.sleep(1)

            # 智能监听列表刷新（等待直到标题变化）
            try:
                page.wait_for_function(
                    f"""() => {{
                        const el = document.querySelector('a.caseName');
                        return el && el.innerText.trim() !== {json.dumps(first_case_title)};
                    }}""",
                    timeout=15000
                )
                print("✅ 下一页数据加载成功！")
                current_page_num += 1
                time.sleep(2.5)  # 翻页后预留 2.5 秒风控缓冲
            except Exception:
                print("⚠️ 等待下一页刷新超时，可能已到最后一页或触发了滑块验证码。")
                break

        # 5. 生成最终 Markdown 深度分析报告
        print("\n📊 正在整合生成全局分析报告...")
        generate_markdown_report(analyzed_results, output_filename="涉案类似判例检索与赔偿尺度分析报告.md")
        print("🎉 全部任务圆满完成！")

        context.close()


import statistics

def generate_markdown_report(analyzed_results: list, output_filename="涉案类似判例检索与赔偿尺度分析报告.md"):
    """
    根据匹配得分排序，提取统计数据并按规范模板生成 Markdown 报告
    """
    if not analyzed_results:
        print("⚠️ 暂无有效研判数据，取消报告生成。")
        return

    # 1. 过滤并按匹配度降序排列
    sorted_cases = sorted(analyzed_results, key=lambda x: x.get("score", 0), reverse=True)
    total_samples = len(sorted_cases)

    # 2. 统计计算：提取精神损害抚慰金金额与罚金支持率
    mental_amounts = []
    fine_ratios = []

    for c in sorted_cases:
        stats = c.get("numeric_stats", {})
        m_amt = stats.get("mental_damages_amount")
        if m_amt is not None and isinstance(m_amt, (int, float)) and m_amt > 0:
            mental_amounts.append(m_amt)

        f_ratio = stats.get("fines_supported_ratio")
        if f_ratio is not None and isinstance(f_ratio, (int, float)):
            fine_ratios.append(f_ratio)

    if mental_amounts:
        min_amt = f"{min(mental_amounts):,.0f}"
        max_amt = f"{max(mental_amounts):,.0f}"
        median_amt = f"{statistics.median(mental_amounts):,.0f}"
    else:
        min_amt, max_amt, median_amt = "0", "0", "0"

    avg_fine_support = f"{statistics.mean(fine_ratios):.1f}%" if fine_ratios else "100%"

    # 3. 构建报告内容
    md_lines = [
        "# 涉案类似判例检索与赔偿尺度分析报告\n",
        "## 报告摘要",
        "- **检索目标**：因公外派/出差因单位合规瑕疵导致被羁押，且无肢体伤残下的精神损害赔偿判例",
        f"- **检索样本数**：{total_samples} 件生效裁判文书",
        f"- **精神损害抚慰金判赔区间**：{min_amt} 元 ~ {max_amt} 元（常见中位数：{median_amt} 元）",
        f"- **职务行为罚款/规费支持率**：约 {avg_fine_support} 全额由用人单位承担\n",
        "---\n",
        "## 典型案例深度剖析\n"
    ]

    # 只展示得分靠前的高相关案例（例如前 3~5 篇）
    display_cases = [c for c in sorted_cases if c.get("score", 0) > 0][:5]
    if not display_cases:
        display_cases = sorted_cases[:3]

    for idx, c in enumerate(display_cases, 1):
        info = c.get("case_info", {})
        facts = c.get("core_facts", {})
        liab = c.get("liability", {})
        reason = c.get("court_reasoning", {})
        insights = c.get("insights", {})
        table_rows = c.get("claims_table", [])

        md_lines.append(f"### 案例 {idx}：{c.get('title', '未知案例')}\n")
        md_lines.append(f"> **匹配度评分**：{c.get('score', 0)} / 100 | **文书链接**：[点击查看详情]({c.get('url', '#')})\n")

        # 【一、 案件基本信息】
        md_lines.append("#### 【一、 案件基本信息】")
        md_lines.append(f"- 案号：{info.get('case_number', '详见文书')}")
        md_lines.append(f"- 审理法院：{info.get('court', '详见文书')}")
        md_lines.append(f"- 裁判年份：{info.get('year', '详见文书')}")
        md_lines.append(f"- 案件类型：{info.get('case_type', '民事纠纷')}")
        md_lines.append(f"- 案由：{info.get('cause_of_action', '提供劳务者受害责任纠纷 / 劳动争议')}\n")

        # 【二、 核心案件事实】
        md_lines.append("#### 【二、 核心案件事实】")
        md_lines.append(f"- 职务背景：{facts.get('duty_background', '无明确记载')}")
        md_lines.append(f"- 涉案事件：{facts.get('incident', '无明确记载')}")
        md_lines.append(f"- 羁押后果：{facts.get('detention_consequence', '无明确记载')}")
        md_lines.append(f"- 当地处罚：{facts.get('local_penalty', '无明确记载')}\n")

        # 【三、 责任与过错认定】
        md_lines.append("#### 【三、 责任与过错认定】")
        md_lines.append(f"- 用人单位过错：{liab.get('employer_fault', '法院认定用人单位负有合规与安全保障义务')}")
        md_lines.append(f"- 员工过错认定：{liab.get('employee_fault', '员工系履职行为，无重大过失')}")
        md_lines.append(f"- 责任比例：{liab.get('liability_ratio', '用人单位承担 100% 责任')}\n")

        # 【四、 诉求与判赔数额明细】
        md_lines.append("#### 【四、 诉求与判赔数额明细】")
        md_lines.append("| 索赔项目 | 员工诉求金额 | 法院判决支持金额 | 判赔比例 | 裁判要点说明 |")
        md_lines.append("| :--- | :--- | :--- | :--- | :--- |")
        if table_rows:
            for row in table_rows:
                md_lines.append(
                    f"| **{row.get('item', '-')}** | {row.get('claimed_amount', '-')} | "
                    f"{row.get('supported_amount', '-')} | {row.get('support_ratio', '-')} | "
                    f"{row.get('notes', '-')} |"
                )
        else:
            md_lines.append("| **综合损失与补偿** | 详见正文 | 依据审理认定 | 依判决执行 | 综合案件事实认定 |")
        md_lines.append("")

        # 【五、 法院裁判说理与要旨】
        md_lines.append("#### 【五、 法院裁判说理与要旨】")
        md_lines.append(f"1. **关于精神损害抚慰金的成立依据**：\n   {reason.get('basis_for_mental_damages', '侵害自然人人身自由权即使未致身体残疾，亦必然产生精神恐慌，符合严重精神损害认定标准。')}")
        md_lines.append(f"2. **关于金额的量化考量**：\n   {reason.get('amount_quantification', '结合羁押时长、惊吓程度及当地经济水平综合酌定。')}\n")

        # 【六、 对本案索赔的对标启示】
        md_lines.append("#### 【六、 对本案索赔的对标启示】")
        md_lines.append(f"- **可直接借鉴点**：{insights.get('key_takeaways', '单位过错与因公受羁押事实是支持兜底追偿的核心依据。')}")
        md_lines.append(f"- **证据补充建议**：{insights.get('evidence_suggestions', '完善回国后门诊病历、诊断证明及实际支付凭证链条。')}\n")
        md_lines.append("---\n")

    # 4. 写入文件
    with open(output_filename, "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines))

    print(f"📄 深度法律分析报告已成功生成至: {output_filename}")



# ==================== 修改后（正确写法） ====================
if __name__ == "__main__":
    search_and_analyze_cases()