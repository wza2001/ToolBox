import json
import requests

DEEPSEEK_API_KEY = "".strip()
DEEPSEEK_URL = "https://api.deepseek.com"


def evaluate_case_with_ai(case_title: str, case_text: str, criteria: str) -> dict:
    """
    使用标准 HTTP POST 调用 DeepSeek 进行结构化文书研判
    """
    prompt = f"""你是一名资深的刑事辩护律师与司法大数据分析专家。
请仔细评估以下判决书，分析其是否符合用户的特定筛选要求。

【用户检索需求】：
{criteria}

【判决书内容摘要】：
案名：{case_title}
正文/核心段落：
{case_text[:3500]}

请严格按以下 JSON 格式返回分析结果（不要输出任何多余的 Markdown 标记或解释）：
{{
  "match_score": 0到100之间的整数（匹配度评分）,
  "is_highly_relevant": true 或 false（是否高度契合）,
  "summary": "案件核心事实与判决结果的一句话总结",
  "key_findings": "与需求吻合的关键情节",
  "discrepancies": "与需求不一致的地方（如有）"
}}
"""
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}"
    }

    payload = {
        "model": "deepseek-chat",  # 对应 DeepSeek V3 / Flash
        "messages": [{"role": "user", "content": prompt}],
        "response_format": {"type": "json_object"},
        "temperature": 0.1
    }

    try:
        resp = requests.post(DEEPSEEK_URL, headers=headers, json=payload, timeout=60)

        if resp.status_code == 200:
            res_data = resp.json()
            raw_content = res_data["choices"][0]["message"]["content"]
            return json.loads(raw_content)
        else:
            print(f"❌ API 返回异常状态码 {resp.status_code}: {resp.text}")
            return {"match_score": 0, "is_highly_relevant": False, "summary": f"HTTP {resp.status_code} 异常"}

    except Exception as e:
        print(f"❌ AI 研判出错: {e}")
        return {"match_score": 0, "is_highly_relevant": False, "summary": f"调用异常: {e}"}