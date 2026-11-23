# 043 - 输入守卫：模型只服务统计任务

> 状态：done
> 创建：2026-11-17 ｜ 敲定：2026-11-17 ｜ 完成：2026-11-17
> 上游：用户需求「完善模型只能用于做统计任务分析，避免闲聊无关问题或者别用于做其他任务烧token」

## 范围

- 做：两层守卫——
  - 第一层（零 token）：宿主预筛 `_looks_like_chitchat`——纯问候/致谢/告别/单字符等
    明显闲聊在 `_on_chat` 最前直接拒绝，先于模型/数据检查
  - 第二层（零额外调用）：模型**同请求自检**——`AnalysisPlan`/`_OUTPUT_FIELDS` 增
    `off_topic`/`off_topic_reason` 字段，模型判定无关时宿主拦截，不进入方案流程；
    答疑路径 `AnswerReply.off_topic` 同理（替换为范围提示）
  - 拒绝事件 `chat_rejected` → 前端 notice 气泡（引导描述统计需求），phase 重置 idle
- 不做：关键词黑名单式语义判断（守门是成本控制非语义决策，语义判断仍归模型）

## 行为列表（全部完成）

- [x] B1: 纯问候预筛拒绝，模型未调用（零 token）
- [x] B2: 模型自检 off_topic=true → chat_rejected，不产方案、状态不破坏
- [x] B3: 正常统计请求不受守卫影响（off_topic=false 回归）
- [x] B4: 答疑 off_topic → 回答替换为统计范围提示
- [x] B5: 前端 chat_rejected 渲染 notice 气泡

## 验证

后端 481 passed（+9：预筛及变体/模型自检/回归/答疑）；前端 86 passed（+1）；
ruff/mypy/build 清零。
