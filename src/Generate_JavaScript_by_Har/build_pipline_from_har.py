import json
import re
import os
from urllib.parse import urlparse, parse_qs

HAR_FILE = "network_dump.har"
OUTPUT_JS = "airgap_batch_runner.js"

if not os.path.exists(HAR_FILE):
    print(f"❌ 未找到 {HAR_FILE}，请确认文件名一致。")
    exit(1)

print("📂 正在解析 HAR 文件...")
with open(HAR_FILE, 'r', encoding='utf-8') as f:
    har = json.load(f)

entries = har.get('log', {}).get('entries', [])

# 提取目标容器
captured = {
    "all_table": None,
    "table_fields": None,
    "batch_create": None,
    "data_storage": None,
    "create_table": None
}

def clean_headers(header_list):
    """过滤浏览器专属头，保留网关鉴权和内容协商标头"""
    keep_headers = {}
    for h in header_list:
        name = h['name']
        val = h['value']
        nl = name.lower()
        if nl in ['authorization', 'accept', 'content-type', 'tenant-id', 'project-id', 'workspace-id']:
            keep_headers[name] = val
        elif nl.startswith('x-') or 'token' in nl:
            keep_headers[name] = val
    return keep_headers

print("🔍 正在逆向提取 5 大关键接口的原生请求报文...")

for e in entries:
    req = e.get('request', {})
    url = req.get('url', '')
    method = req.get('method', '').upper()
    post_text = req.get('postData', {}).get('text', '')

    # 1. all-table
    if any(k in url.lower() for k in ['all-table', 'all_table', 'tables']) and method == 'GET':
        if not captured["all_table"]:
            captured["all_table"] = {
                "url": url,
                "headers": clean_headers(req.get('headers', []))
            }

    # 2. table-fields
    if 'table-fields' in url and method == 'GET':
        if not captured["table_fields"]:
            captured["table_fields"] = {
                "url": url,
                "headers": clean_headers(req.get('headers', []))
            }

    # 3. batch-create (抓取体积最大的那次完整建表请求)
    if 'batch-create' in url and method == 'POST':
        if len(post_text) > 1000:
            if not captured["batch_create"] or len(post_text) > len(captured["batch_create"]["raw_text"]):
                captured["batch_create"] = {
                    "url": url,
                    "headers": clean_headers(req.get('headers', [])),
                    "raw_text": post_text,
                    "json_data": json.loads(post_text)
                }

    # 4. data-storage / saveModel
    if any(k in url.lower() for k in ['data-storage', 'savemodel', 'storage']) and method in ['POST', 'PUT']:
        if len(post_text) > 10:
            if not captured["data_storage"]:
                captured["data_storage"] = {
                    "url": url,
                    "method": method,
                    "headers": clean_headers(req.get('headers', [])),
                    "json_data": json.loads(post_text)
                }

    # 5. create-table / syncPhysicalTable
    if any(k in url.lower() for k in ['create-table', 'syncphysicaltable', 'physical']) and method in ['POST', 'PUT']:
        if not captured["create_table"]:
            captured["create_table"] = {
                "url": url,
                "method": method,
                "headers": clean_headers(req.get('headers', [])),
                "json_data": json.loads(post_text) if post_text else {}
            }

for k, v in captured.items():
    if v is None:
        print(f"⚠️ 警告: 未在 HAR 中自动识别到 [{k}]，请检查录制完整性。")
    else:
        print(f"✅ 成功提取 [{k}]: {v['url']}")

# -------------------------------------------------------------
# 深度解析 batch-create 内部结构
# -------------------------------------------------------------
bc_raw = captured["batch_create"]["json_data"]
m0 = bc_raw.get("modelInfoList", [{}])[0]

sample_source_table = m0.get("sourceName") or m0.get("sourceEnglishName")
if not sample_source_table and captured["table_fields"]:
    parsed = urlparse(captured["table_fields"]["url"])
    sample_source_table = parse_qs(parsed.query).get("tableName", [""])[0]

print(f"\n🎯 识别出 HAR 中手工录制所用的源表名基准: [{sample_source_table}]")

field_list_key = None
for k, v in m0.items():
    if isinstance(v, list) and len(v) > 0 and isinstance(v[0], dict):
        field_list_key = k
        break

print(f"🎯 识别出字段数组的实际属性名: [{field_list_key}]")

common_headers = captured["batch_create"]["headers"]
if 'Content-Type' not in common_headers:
    common_headers['Content-Type'] = 'application/json;charset=UTF-8'

# -------------------------------------------------------------
# 生成保密机直接运行的 JavaScript 批量执行脚本
# -------------------------------------------------------------
js_template = f"""/**
 * 自动化批量建表执行脚本（100% 提取自 HAR 原生请求）
 * 生成环境: 保密机专用
 */
(async function runAirgapPipeline() {{
  // 1. 全局配置与 HAR 原生底模
  const COMMON_HEADERS = {json.dumps(common_headers, ensure_ascii=False, indent=2)};

  // 动态自动提取当前浏览器激活的最新 Token，杜绝 401 AUTH_UNAUTHORIZED
  const activeToken = 
    sessionStorage.getItem('token') || 
    sessionStorage.getItem('access_token') || 
    sessionStorage.getItem('Blade-Auth') ||
    localStorage.getItem('token') || 
    localStorage.getItem('access_token') ||
    localStorage.getItem('Blade-Auth');
  if (activeToken) {{
    COMMON_HEADERS['Authorization'] = activeToken.startsWith('Bearer ') ? activeToken : `Bearer ${{activeToken}}`;
  }}

  // 原生 URL
  const URL_ALL_TABLE = "{captured['all_table']['url'].split('?')[0] if captured['all_table'] else ''}";
  const URL_TABLE_FIELDS = "{captured['table_fields']['url'].split('?')[0] if captured['table_fields'] else ''}";
  const URL_BATCH_CREATE = "{captured['batch_create']['url'] if captured['batch_create'] else ''}";
  const URL_DATA_STORAGE = "{captured['data_storage']['url'] if captured['data_storage'] else ''}";
  const DATA_STORAGE_METHOD = "{captured['data_storage']['method'] if captured['data_storage'] else 'POST'}";
  const URL_CREATE_TABLE = "{captured['create_table']['url'] if captured['create_table'] else ''}";
  const CREATE_TABLE_METHOD = "{captured['create_table']['method'] if captured['create_table'] else 'POST'}";

  // 原生载荷底模
  const RAW_BATCH_CREATE_TEMPLATE = {json.dumps(bc_raw, ensure_ascii=False)};
  const RAW_STORAGE_TEMPLATE = {json.dumps(captured['data_storage']['json_data'] if captured['data_storage'] else {}, ensure_ascii=False)};
  const RAW_CREATE_TABLE_TEMPLATE = {json.dumps(captured['create_table']['json_data'] if captured['create_table'] else {}, ensure_ascii=False)};

  const SAMPLE_ORIGIN_TABLE = "{sample_source_table}";
  const FIELD_LIST_KEY = "{field_list_key}";

  const sleep = (ms) => new Promise(r => setTimeout(r, ms));
  function generateUUID() {{
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function (c) {{
      const r = (Math.random() * 16) | 0;
      const v = c === 'x' ? r : (r & 0x3) | 0x8;
      return v.toString(16);
    }});
  }}

  // =========================================================================
  // 步骤 0：通过网络请求拉取全量表清单并自愈解析
  // =========================================================================
  console.log("🚀 [第 1 步] 正在请求源库全部表清单...");
  const allTableRes = await fetch(`${{URL_ALL_TABLE}}?dataSourceConnectionId=${{RAW_BATCH_CREATE_TEMPLATE.dataSourceConnectionId}}&_t=${{Date.now()}}`, {{
    method: 'GET',
    headers: COMMON_HEADERS,
    credentials: 'include'
  }});

  if (!allTableRes.ok) {{
    console.error(`❌ 拉取表清单失败，HTTP 状态码: ${{allTableRes.status}}。若为 401 请在当前页面重新刷新登录。`);
    return;
  }}

  const allTableJson = await allTableRes.json();

  // 针对形态 A 的智能穿透提取算法
  function extractTableArray(res) {{
    if (Array.isArray(res)) return res;
    const d = res.data !== undefined ? res.data : res;
    if (Array.isArray(d)) return d;
    if (typeof d === 'object' && d !== null) {{
      for (const k of ['tableList', 'list', 'records', 'tables', 'rows']) {{
        if (Array.isArray(d[k])) return d[k];
      }}
      for (const key of Object.keys(d)) {{
        if (Array.isArray(d[key]) && d[key].length > 0) return d[key];
      }}
      const vals = Object.values(d);
      if (vals.length > 0 && typeof vals[0] === 'object') return vals;
    }}
    return [];
  }}

  const rawTableList = extractTableArray(allTableJson);

  if (!Array.isArray(rawTableList) || rawTableList.length === 0) {{
    console.error("❌ 未能在返回数据中定位到有效表数组，返回结构为:", allTableJson);
    return;
  }}

  // 使用指定正则排除系统内部表
  const filterRegex = /^(?!i\\d+$).*$/i;
  const targetTables = rawTableList
    .map(t => typeof t === 'string' ? t : (t.tableName || t.table_name || t.name || t.sourceName || t.TABLE_NAME || ''))
    .filter(name => Boolean(name) && filterRegex.test(name));

  console.log(`📋 库内总表数: ${{rawTableList.length}}，正则筛选后待处理: ${{targetTables.length}} 张表`);

  let successCount = 0;
  let failCount = 0;

  // =========================================================================
  // 遍历每张表执行完整治理流水线
  // =========================================================================
  for (let i = 0; i < targetTables.length; i++) {{
    const currentTable = targetTables[i];
    const currentModelName = 'ods_makani_' + currentTable;
    console.log(`\\n==================== [${{i + 1}}/${{targetTables.length}}] 正在处理: ${{currentTable}} ====================`);

    try {{
      // A. 拉取字段
      const fieldRes = await fetch(`${{URL_TABLE_FIELDS}}?tableName=${{currentTable}}&_t=${{Date.now()}}`, {{
        method: 'GET',
        headers: COMMON_HEADERS,
        credentials: 'include'
      }});
      const fieldData = await fieldRes.json();
      const rawFields = fieldData.data?.modelFields || fieldData.modelFields || [];

      // 剔除 ObjectID
      const fields = rawFields.filter(f => {{
        const cname = (f.columnName || f.fieldName || f.name || '').toUpperCase();
        return cname !== 'OBJECTID';
      }});

      if (fields.length === 0) {{
        console.warn(`⚠️ [${{currentTable}}] 获取到的字段为空，跳过此表。`);
        continue;
      }}

      // 动态生成 bindMapping
      const dynamicBindMapping = {{}};
      fields.forEach(f => {{
        const srcId = f.id || f.fieldId || generateUUID();
        const tgtId = f.targetFieldId || generateUUID();
        dynamicBindMapping[srcId] = [tgtId];
      }});

      // B. 深拷贝原生 batch-create 模板进行精准替换
      const batchPayload = JSON.parse(JSON.stringify(RAW_BATCH_CREATE_TEMPLATE));
      const modelItem = batchPayload.modelInfoList[0];

      for (const key of Object.keys(modelItem)) {{
        const val = modelItem[key];
        if (typeof val === 'string') {{
          if (val === SAMPLE_ORIGIN_TABLE) {{
            modelItem[key] = currentTable;
          }} else if (val.toLowerCase() === SAMPLE_ORIGIN_TABLE.toLowerCase()) {{
            modelItem[key] = currentTable.toLowerCase();
          }} else if (val.includes(SAMPLE_ORIGIN_TABLE)) {{
            modelItem[key] = val.replace(new RegExp(SAMPLE_ORIGIN_TABLE, 'gi'), currentTable);
          }}
        }}
      }}

      modelItem.modelEnName = currentModelName;
      modelItem.targetTableName = currentModelName.toLowerCase();
      modelItem.bindMapping = dynamicBindMapping;

      if (FIELD_LIST_KEY) {{
        modelItem[FIELD_LIST_KEY] = fields;
      }}

      const bcRes = await fetch(URL_BATCH_CREATE, {{
        method: 'POST',
        headers: COMMON_HEADERS,
        credentials: 'include',
        body: JSON.stringify(batchPayload)
      }});

      const bcJson = await bcRes.json();
      if (!bcRes.ok || (bcJson.code && bcJson.code !== 200 && bcJson.code !== 0 && bcJson.code !== '0')) {{
        throw new Error(`batch-create 失败: ${{JSON.stringify(bcJson)}}`);
      }}

      const newModelId = bcJson.data?.id || (Array.isArray(bcJson.data) ? bcJson.data[0]?.id : null) || bcJson.data || bcJson.id;
      console.log(`✅ [${{currentTable}}] 元数据登记成功，分配 Model ID: ${{newModelId}}`);

      // C. 提交 data-storage：精准注入 saveModel: DROP_DATA
      if (URL_DATA_STORAGE) {{
        const storagePayload = JSON.parse(JSON.stringify(RAW_STORAGE_TEMPLATE));
        if ('modelId' in storagePayload) storagePayload.modelId = newModelId;
        if ('id' in storagePayload) storagePayload.id = newModelId;

        storagePayload.saveModel = "DROP_DATA";

        await fetch(URL_DATA_STORAGE, {{
          method: DATA_STORAGE_METHOD,
          headers: COMMON_HEADERS,
          credentials: 'include',
          body: JSON.stringify(storagePayload)
        }});
        console.log(`✅ [${{currentTable}}] 存储策略已更新为 saveModel: DROP_DATA`);
      }}

      // D. 识别 General Geometry 且列名包含 shape 的空间字段
      const geomFields = fields.filter(f => {{
        const typeStr = (f.dataType || f.fieldType || f.type || '').toLowerCase();
        return typeStr.includes('geometry');
      }});

      let targetGeomField = null;
      if (geomFields.length > 0) {{
        targetGeomField = geomFields.find(f => {{
          const colName = (f.columnName || f.fieldName || f.name || '').toLowerCase();
          return colName.includes('shape');
        }}) || geomFields[0];
      }}

      const selectedGeomColumn = targetGeomField 
        ? (targetGeomField.columnName || targetGeomField.fieldName || targetGeomField.name)
        : null;

      // E. 执行 create-table (物理 DDL)
      if (URL_CREATE_TABLE) {{
        const ddlPayload = JSON.parse(JSON.stringify(RAW_CREATE_TABLE_TEMPLATE));
        if ('modelId' in ddlPayload) ddlPayload.modelId = newModelId;
        ddlPayload.connectionType = "AZURE_POSTGRESQL";

        if (selectedGeomColumn) {{
          const uniqueIndexName = `tbl_idx_${{Date.now()}}`;
          ddlPayload.indexes = [
            {{
              columns: [selectedGeomColumn],
              name: uniqueIndexName,
              type: "NORMAL"
            }}
          ];
        }} else {{
          ddlPayload.indexes = [];
        }}

        const ddlRes = await fetch(URL_CREATE_TABLE, {{
          method: CREATE_TABLE_METHOD,
          headers: COMMON_HEADERS,
          credentials: 'include',
          body: JSON.stringify(ddlPayload)
        }});

        if (ddlRes.ok) {{
          console.log(`🎉 [${{currentTable}}] 物理建表成功！` + (selectedGeomColumn ? `索引: tbl_idx_${{Date.now()}}` : '（无索引属性表）'));
          successCount++;
        }} else {{
          const errText = await ddlRes.text();
          console.error(`❌ [${{currentTable}}] 物理建表失败: HTTP ${{ddlRes.status}} - ${{errText}}`);
          failCount++;
        }}
      }}

      await sleep(600);

    }} catch (err) {{
      console.error(`💥 [${{currentTable}}] 流程中断:`, err);
      failCount++;
    }}
  }}

  console.log(`\\n🏁 全部处理完成！成功: ${{successCount}}，失败: ${{failCount}}`);
}})();
"""

with open(OUTPUT_JS, 'w', encoding='utf-8') as f:
    f.write(js_template)

print(f"\n🎉 生成完成！保密机执行文件已写入: {OUTPUT_JS}")