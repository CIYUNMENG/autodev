# Skills 使用说明

AutoDev Agent 以 **ClawHub** 格式为主，同时兼容 Cursor 等备选格式。Skills 从 `skills/` 目录加载，并注入到对话系统提示中。

## 支持的格式

### 1. ClawHub 主格式（推荐）

将 skill 放置在 `skills/<skill-name>/` 目录下：

```
skills/
└── my-skill/
    ├── _meta.json   # 清单文件（必需）
    └── SKILL.md     # AI 指令（必需）
```

**_meta.json 示例：**

```json
{
  "name": "my-skill",
  "slug": "my-skill",
  "description": "技能描述，用于展示",
  "summary": "简短摘要",
  "version": "1.0.0"
}
```

**SKILL.md**：纯 Markdown，定义 AI 在何种场景下激活、如何响应。

### 2. ClawHub 备选格式

若目录中没有 `_meta.json`，则尝试 `claw.json` + 指令文件：

```
skills/
└── my-skill/
    ├── claw.json         # 清单文件
    └── instructions.md   # 或 README.md、SKILL.md
```

**claw.json 示例：**

```json
{
  "name": "my-skill",
  "description": "技能描述",
  "version": "1.0.0"
}
```

### 3. Cursor 备选格式

在 `skills/` 下放置 `SKILL.md` 文件（所在目录无 `_meta.json` / `claw.json` 时）：

```markdown
---
name: my-skill
description: 技能描述
---

# 技能标题

## 何时使用
- 场景 1

## 如何执行
具体指令...
```

## 加载优先级

1. **ClawHub 主格式**：`_meta.json` + `SKILL.md`
2. **ClawHub 备选**：`claw.json` + `instructions.md` / `README.md` / `SKILL.md`
3. **Cursor 备选**：独立的 `SKILL.md`（带 YAML frontmatter）

## 使用方式

1. **下载 skill**：从 ClawHub 或其他来源下载 skill，解压到 `skills/` 目录
2. **启动服务**：`uvicorn app.main:app`，启动时自动加载 `skills/` 下的 skills
3. **对话生效**：加载的 skill 指令会注入到系统提示，AI 会根据指令调整行为

## API

- `GET /api/skills`：列出 `skills/` 下可发现的 skills（不加载，仅元信息）

## 与 ClawHub 的兼容性

- **主格式**：推荐使用 `_meta.json` + `SKILL.md`，与 ClawHub 标准结构一致
- **备选**：仍支持 `claw.json` + `instructions.md` 结构
- **直接使用**：从 ClawHub 下载的 skill 若符合上述任一结构，解压到 `skills/` 即可使用
- **差异**：ClawHub skills 主要为 OpenClaw 设计；AutoDev Agent 将 instructions 注入为系统提示的一部分，不执行 skill 中的 JavaScript/TypeScript 代码
