# 生词卡 — 架构设计文档

> 版本: v0.1
> 日期: 2026-07-13
> 配套文档: PRD.md（v0.2）

## 文档说明

本文档回答：**代码怎么组织、模块怎么协作、数据怎么流、失败了怎么办。**

不回答：做什么、给谁用（→ PRD.md）；每个函数怎么写（→ 开发阶段）。

**本文档主要是给 AI 协作工具看的。**AI 每次对话都是清零重启，没有项目的全局印象。写代码前先读这份文档，才不会每次拍一个不同的结构。

---

## 1. 设计原则

1. **简单优先。**能一个文件解决的不拆三个。不为想象中的需求预留抽象。
2. **词典是外围件，不是地基。**词典的任何字段都可能缺失（实测：`marginal` 缺义项、`scaling` 缺音频）。词典查不到、义项不全、没音频——系统都要能正常出卡。
3. **卡片的正确答案来自 LLM + 原句，不来自词典。**这是上一条的直接推论，也是本设计对词典缺陷免疫的原因。
4. **所有路径和密钥从配置注入，不硬编码。**测试时把数据库路径指向临时目录，代码零改动。
5. **阅读路径不依赖后端。**划词查词直连词典 API。后端挂了，读文章不受影响。
6. **参数在 yaml 里，不在代码里。**改"每天几张卡"不需要改代码、不需要重新部署镜像。

---

## 2. 部署形态

```
浏览器插件（你的电脑）
      ↓ 只有「加入生词本」才请求后端
VPS（一台，一直开着）
      ├── FastAPI（收词接口 + 复习页 + 回流接口）
      ├── 进程内定时器（每天 8:00 推送）
      └── SQLite（一个文件，挂在服务器硬盘上）
      ↓
飞书 → 你的手机
```

**关键决策与理由：**

| 决策 | 理由 |
|------|------|
| VPS（国内或香港），不用 Cloud Run / Fly.io | 手机没有梯子，复习页必须能直接打开。**这是产品的关键路径，页面打不开产品就死了** |
| SQLite，不用 Postgres | 一年不到 2000 条记录。SQLite = 一个文件，本地和线上跑同一套东西，测试零 mock |
| 进程内定时器（APScheduler），不用 GitHub Actions | 后端本来就常驻。GH Actions cron 延迟 10~30 分钟是常态，8 点的推送可能 8:25 才到 |
| FastAPI + Docker，不用 Cloudflare Workers | Cloudflare 在"把工具做出来"上更优（免费、更快），但要写 TypeScript。**FastAPI + Docker + 部署是次要目标的靶心，且不引入新语言** |
| 一个仓库，两个顶层目录 | 插件和后端是一个产品，接口要对齐。分仓会看不到全貌 |

**如果选国内 VPS**：访问不了 Claude / OpenAI，改用国内模型（DeepSeek / 通义 / 豆包 / Kimi）。对"翻译一句话 + 生成中文干扰项"这个任务，国内模型完全够用、更便宜、中文更顺。**这不是降级。**
**如果选香港 VPS**：LLM 随便用，域名免备案。

---

## 3. 目录结构

```
vocab/
├── extension/                # 浏览器插件（JS）
│   ├── manifest.json
│   ├── content.js            # 划词、抓原句、注入弹窗
│   ├── popup.css
│   └── api.js                # 调词典 API + 调后端收词接口
│
├── server/
│   ├── app/
│   │   ├── main.py           # FastAPI 入口，启动时拉起定时器
│   │   ├── config.py         # 配置类（读 config.yaml + .env）
│   │   ├── db.py             # SQLite 连接、建表
│   │   ├── models.py         # 表定义
│   │   │
│   │   ├── api/
│   │   │   ├── collect.py    # POST /words           插件调
│   │   │   └── review.py     # GET /review, POST /review/answer
│   │   │
│   │   ├── services/
│   │   │   ├── dictionary.py # 词典适配器（可换源）
│   │   │   ├── llm.py        # LLM 统一客户端（重试、兜底、可全局关闭）
│   │   │   ├── enrich.py     # 补全：词典 + LLM → 完整卡片数据
│   │   │   ├── deck.py       # 组卡：抽 N 新 + M 复习
│   │   │   └── push.py       # 飞书推送
│   │   │
│   │   ├── scheduler.py      # 定时器：每天 8:00 触发推送
│   │   └── prompts/
│   │       └── enrich.txt    # prompt 单独成文件，便于迭代
│   │
│   ├── templates/            # 复习页 HTML
│   ├── tests/
│   ├── config.yaml           # 参数
│   ├── .env                  # 密钥，不进 git
│   ├── Dockerfile
│   └── requirements.txt
│
├── ARCHITECTURE.md
├── PRD.md
└── README.md
```

**目录约定：**

- **`config.yaml` 是数据，`config.py` 是代码。**别混。
- **`services/` 里每个模块都不知道自己被谁调用。**`deck.py` 不该知道飞书的存在。
- **prompt 在单独文件里**，不埋在 Python 字符串里——你要反复调它。
- **`extension/` 和 `server/` 里各有一份词典调用代码，这不是重复。**插件那份只把释义原样显示在弹窗里（几十行 JS，不缓存、不适配）；后端那份要做适配器、缓存、喂给 LLM。目的不同，共用反而别扭。

---

## 4. 数据表

### 4.1 `words` — 词（去重和学习进度的单位）

```
word            TEXT PRIMARY KEY   -- 'marginal'
part_of_speech  TEXT               -- 'adjective'（筛第三层释义要用）
definitions     TEXT               -- 词典英文释义，JSON 数组，可为空
phonetic        TEXT               -- IPA，可为空
audio_url       TEXT               -- 可为空（scaling 实测就没有）
remaining       INTEGER            -- 剩余推荐次数，初始 3
status          TEXT               -- pending / active / graduated
created_at      TIMESTAMP
updated_at      TIMESTAMP
```

`status` 含义：
- `pending` — 在候选池，尚未放行（等着被抽为新词）
- `active` — 在复习队列
- `graduated` — `remaining` 减到 0，不再推送

### 4.2 `sentences` — 原句（一个词可有多句）

```
id           INTEGER PRIMARY KEY
word         TEXT       -- → words.word
sentence     TEXT       -- 划词时抓的那句
source_url   TEXT
answer_zh    TEXT       -- LLM：该词在这句话里的中文含义（= 正确答案）
distractors  TEXT       -- LLM：3 个干扰项，JSON 数组
trans_zh     TEXT       -- LLM：原句中文翻译
enriched     BOOLEAN    -- 是否已补全
created_at   TIMESTAMP
```

### 4.3 `daily_deck` — 今日卡组

```
date         DATE
word         TEXT
sentence_id  INTEGER
is_new       BOOLEAN    -- 新词卡 or 复习卡
answered     BOOLEAN
correct      BOOLEAN
PRIMARY KEY (date, word)
```

### 4.4 `reviews` — 答题历史（可选，但建议留）

```
id           INTEGER PRIMARY KEY
word         TEXT
sentence_id  INTEGER
correct      BOOLEAN
answered_at  TIMESTAMP
```

严格说不需要——`words.remaining` 一个数字就够跑。但留着它，以后能回答"我到底记住了多少词""哪些词我反复错"。一张表，几行代码。

### 4.5 三个关键设计点

**1. 去重的单位是 `word`，不是 `(word, sentence)`。**
同一个词第二次被划到 → `words` 不新增行，`sentences` 追加一句，`words.remaining` 重置为 3，`status` 回到 `active`。**一个词只有一个学习进度。**

**2. LLM 的所有产物挂在 `sentences` 上，不在 `words` 上。**
答案、干扰项、翻译**都依赖具体那句话**。`marginal` 在经济学文章和技术文章里的正确答案不同。这是设计的核心，也是它免疫词典缺陷的原因。

**3. 词典产物（`definitions` / `phonetic` / `audio_url`）挂在 `words` 上。**
它们只跟词有关，与语境无关。一个词查一次，永久缓存。

---

## 5. 数据流

### 5.1 采集（同步，用户在场）

```
划词 → 插件直连 dictionaryapi.dev → 弹窗显示释义
        （不经过后端。后端挂了也能查词、能读文章）

点「加入生词本」 → 插件 POST /words { word, sentence, source_url }
                  → 后端写入 words(status=pending) + sentences(enriched=false)
                  → 立即返回，不做补全
```

**这一步必须快、必须只有 1 次点击。**补全是后台的事，用户不等。

### 5.2 补全（异步，后台批处理）

```
enrich.py（定时或收词后触发）
  取所有 sentences.enriched = false 的记录
  ↓
  1. 词典层（按 word 缓存）：查 dictionary.py
     → definitions / part_of_speech / phonetic / audio_url
     → 失败 = 可接受，字段留空
  ↓
  2. LLM 层（按 sentence 跑一次）：调 llm.py
     输入：word + sentence + 词典释义（作参考，不作约束）
     输出：answer_zh + distractors + trans_zh
     → 失败 = 不可接受，见 §7
  ↓
  写库，enriched = true
```

**关键：LLM 的输出不受词典义项约束。**词典给的释义只是参考材料。实测 `marginal` 的词典返回里根本没有"微不足道"这个义项——如果让 LLM 从词典义项里挑，这张卡就废了。

### 5.3 复习（今日卡组）

```
GET /review
  今天的 daily_deck 已存在？
    是 → 直接读（刷新页面不会重新洗牌）
    否 → deck.py 现算：
           复习卡：从 status=active 中取 M 张（优先取最久没复习的）
           新词卡：从 status=pending 且 enriched=true 中放行 N 个 → status=active
           不足则有多少给多少，不补齐
         写入 daily_deck
  ↓
  渲染三层卡片

POST /review/answer { word, correct }
  correct=true  → words.remaining -= 1
  correct=false → 不变（不归零、不惩罚）
  remaining == 0 → status = graduated
  写 daily_deck.answered + reviews
```

**为什么"打开时现算"而不是"推送时现算"**：
推送失败（飞书挂了、网络抖）不该导致今天没有卡片。**推送只是发一个链接的提醒，卡片在你打开页面时才生成。**这样推送模块从"核心"降级为"辅助"，少一个能杀死产品的单点。

### 5.4 推送

```
scheduler.py（每天 8:00）
  → push.py 发飞书消息，内含复习页链接
  → 失败：重试 3 次 → 记 ERROR 日志 → 结束（不影响任何东西）
```

---

## 6. 外部服务调用

### 6.1 词典适配器（`services/dictionary.py`）

**统一接口，实现可替换：**

```python
def lookup(word: str) -> DictEntry | None:
    """返回 {definitions, part_of_speech, phonetic, audio_url}，任何字段可为 None"""
```

当前实现：`dictionaryapi.dev`（无需 key，直接打）。

**为什么做适配器（这是唯一一处允许的"提前抽象"）：**
不是为了想象中的扩展，是因为**已经确定要换**——Merriam-Webster Learner's（学习者词典，释义可读性高一个档次）是目标，只是注册暂时受阻。接口留着，注册通了换一个实现类，其他代码零改动。

**实现要点（全部来自实测）：**
- 返回是**数组**，不是对象
- 查不到 → HTTP 404，不是空数组。**必须处理，不然崩**
- `meanings[].definitions[]` 可能有 18 条（`scaling` 实测）→ **按 `partOfSpeech` 筛出匹配的一组，最多取前 3 条**
- `phonetics` 数组里，**音标和音频常常分散在不同元素中**（`marginal` 实测）→ 要写个归并函数凑出 `{phonetic, audio_url}`
- 音频**可能完全没有**（`scaling` 实测）→ `audio_url = None`，前端不播、不报错、不留空按钮
- 有多个音频时**优先 `-us`**，别放澳洲口音
- 无词形还原：`-ed` / `-s` / 不规则变化可能 404（见 §9）
- 数据是 CC BY-SA → 复习页页脚挂一行 Wiktionary 署名和回链

### 6.2 LLM 客户端（`services/llm.py`）

- **所有 LLM 调用走这一个入口**
- 内置重试：3 次指数退避
- 内置**全局关闭开关**（测试和降级用）
- **无状态**（单次问答，不是多轮对话）→ 共享一个客户端实例
- prompt 从 `prompts/enrich.txt` 读，不写在代码里

**一次调用产出三样东西**（一条记录只跑一次，永久缓存）：
```
输入：word, sentence, 词典释义（参考，非约束）
输出：{ answer_zh, distractors: [3个], trans_zh }
```

**干扰项的质量是本产品的核心质量。**要求：同词性、语义相邻、放进这句话也说得通。考 `marginal` 时，干扰项里该有"可以忽略不计的"，而不是"一种红色水果"。**这一条要写进 prompt，也要进评估。**

**关键性质：日常复习流程零 LLM 调用、零词典调用，全部读缓存。**

---

## 7. 错误处理分级

| 环节 | 核心/辅助 | 失败了怎么办 |
|------|-----------|-------------|
| 插件 → 词典 API | 辅助 | 弹窗显示"查不到"。**不影响阅读** |
| 插件 → 后端收词 | 辅助 | 弹窗提示"入库失败"。v1 不做本地重试队列（见 §9） |
| 补全 → 词典 | **辅助** | 字段留空。**卡片照常能出**——答案来自 LLM，不依赖词典 |
| 补全 → LLM | **核心** | 重试 3 次 → 仍失败 → 该记录留 `enriched=false`，下次批处理再试。**不阻塞其他词的补全** |
| 组卡 → 新词不够 | 辅助 | 有多少给多少，不补齐（PRD 已定） |
| 组卡 → 复习词不够 | 辅助 | 同上 |
| 推送 | **辅助** | 重试 3 次 → 记 ERROR 日志 → 结束。**卡片是打开页面时才算的，推送失败不影响你手动打开链接** |
| 复习页 / 回流接口 | **核心** | 这两个挂了产品就死了。要有日志、要能快速发现 |

**判断标准：不做的话，最终交付物（今天那 10 张卡）是缺一块，还是整个废。**

**唯一的核心外部依赖是 LLM。**词典可以全挂，卡片照样出（只是第三层没有英文释义和发音）。这是设计原则 2 和 3 的直接结果。

---

## 8. 配置系统

**三层：**

| 层 | 文件 | 内容 | 进 git |
|---|---|---|---|
| 参数 | `config.yaml` | 每日卡片数、新词数、毕业次数、推送时间、词典源 | ✓ |
| 密钥 | `.env` | LLM key、飞书 webhook | **✗** |
| 代码 | `config.py` | 读上面两个，做校验，暴露一个配置类 | ✓ |

`config.yaml` 初始值（全部来自 PRD）：
```yaml
daily_cards: 10
daily_new_words: 5
graduate_after: 3
options_count: 4
push_time: "08:00"
db_path: "./data/vocab.db"
dictionary_source: "dictionaryapi_dev"
```

**用类封装配置（`config.py`），不用裸字典。**有类型提示、有 IDE 补全、能集中校验。

**`db_path` 必须从配置读，不能硬编码。**测试时指向临时目录，代码零改动——这就是"依赖注入"。

---

## 9. 测试策略

**这个项目的次要目标是练完整的工程流程，测试是重点，不是补丁。**

**注意：确定性流程一样要测，而且更好测。**不要因为"想用上评估方法论"就把确定性逻辑改造成 LLM 逻辑。

### 9.1 单元测试（不碰网络）

| 模块 | 测什么 |
|---|---|
| `dictionary.py` | **用 `marginal` / `tractable` / `scaling` / `ablation` 的真实返回存成 fixture**，断言：18 条释义能筛到 3 条、音标音频能正确归并、无音频时返回 None、404 不崩 |
| `deck.py` | 组卡逻辑：配比对不对、不足时怎么处理、同一天重复调用返回同一组 |
| 计数逻辑 | 选对 -1、选错不变、减到 0 毕业 |
| 去重逻辑 | 同词再入库 → 追加例句 + 重置为 3 |

### 9.2 集成测试

- 端到端：收词 → 补全 → 组卡 → 回流，全链路
- **词典和 LLM 全部 mock，测试不依赖外部网络**

### 9.3 LLM 输出质量评估（抽样，人工）

- 正确答案（`answer_zh`）准确率 ≥ 95%（抽 50 条）
- 干扰项抽样检查：**不能出现一眼排除的低质量选项**

---

## 10. 开放问题（留到开发阶段）

1. **词形还原。**dictionaryapi.dev 没有 `stems`。划到 `scaled` / `gains` 可能 404。先跑起来，实际撞到了再解决。**不要现在造轮子。**
2. **原句抓取的 DOM 策略。**网页结构千奇百怪，先做主流场景，不追求 100%。
3. **插件收词失败的本地重试队列。**v1 不做，直接提示失败。如果实际用起来发现经常丢词，再加。
4. **干扰项从哪来。**当前方案：LLM 生成（可缓存、冷启动时词库为空也能用）。备选：从自己词库里抽同词性的词。先用 LLM。
5. **复习页要不要加密。**它挂在公网上，任何人拿到链接都能看。你的生词不是机密，v1 先不做。
6. **M-W Learner's 注册。**通了就换实现类。释义可读性比 Wiktionary 高一个档次，值得再试一次。

---

## 附录：给 AI 协作的约定

- **写任何代码前，先读这份文档和 PRD.md。**
- **不要引入 PRD 和本文档里没有的功能。**想加的记到 someday-ideas，不在当前代码里做。
- **不要为想象中的扩展提前抽象。**唯一允许的抽象是词典适配器（因为已确定要换）。
- **不要硬编码路径、密钥、参数。**全部从 `config.py` 取。
- **prompt 改动只改 `prompts/*.txt`，不改 Python 代码。**
