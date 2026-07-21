# 生词卡

一个个人用的英文生词留存工具：浏览器划词查词，主动加入生词本，后台补全卡片，每天通过飞书推送复习页。

## 目录

- `extension/`：Chrome/Edge Manifest V3 插件，原生 JS。
- `server/`：FastAPI 后端，SQLite 存储，APScheduler 定时推送。
- `docs/`：项目早期 PRD 和架构文档，仅作为初始设计背景；后续开发以当前代码和实际使用反馈为准。

## 本地运行

```powershell
conda env create -f environment.yml
conda activate p26-vocab-flashcard
cd server
Copy-Item .env.example .env
python -m uvicorn app.main:app --reload --port 8001
```

打开 `http://127.0.0.1:8001/health` 应返回 `{"ok":true}`。

## 配置

- 参数放在 `server/config.yaml`。
- 密钥放在 `server/.env`，不要提交真实密钥。
- DeepSeek 默认模型是 `deepseek-v4-flash`，可通过 `DEEPSEEK_MODEL` 覆盖。
- Merriam-Webster 词典默认使用 Learner's API，把 key 写到 `MERRIAM_WEBSTER_LEARNERS_KEY`。普通 Dictionary API key 可写到 `MERRIAM_WEBSTER_DICTIONARY_KEY` 备用。
- 修改词典 key 后重启服务；要刷新已有词条的释义/音标/音频，运行 `python scripts/refresh_dictionary.py`。

## 浏览器插件

1. 打开 Chrome/Edge 扩展管理页。
2. 启用开发者模式。
3. 加载已解压扩展，选择 `extension/` 目录。
4. 本地默认后端地址是 `http://127.0.0.1:8001`。

## 测试

```powershell
cd server
conda run -n p26-vocab-flashcard python -m pytest

cd ..
node --test extension/tests
```

测试 mock 词典和 LLM，不依赖外部网络。

插件端到端测试页：

```powershell
python -m http.server 8765 --directory extension
```

加载插件后打开 `http://127.0.0.1:8765/test-page.html`，可稳定测试重复词原句、嵌套元素、列表样式和弹窗边界。

## Docker

```powershell
Copy-Item server\\.env.example server\\.env
docker compose up --build -d
```
