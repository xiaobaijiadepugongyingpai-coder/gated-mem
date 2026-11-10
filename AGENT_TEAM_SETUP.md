# 如何建子智能体（AgentTeams）

## 1. 先确认有哪些模型可用

```
list_subagent_models({})                              # 看有哪些 provider
list_subagent_models({ provider: "workbuddy" })       # 看某 provider 下有哪些 model
```

本机当前可用：

```
workbuddy/deepseek-v4.1-flash
workbuddy/glm-5.3-flash
antigravity/gemini-3.8-flash
```

## 2. 建队：每个成员都要显式传 provider + model

```js
agent_teams_create({
  name: "gated-mem-phase1",
  description: "一句话说明这支队要干什么",
  approval: "required",
  plan: {
    members: [
      { name: "kernel",  role: "主程",      provider: "workbuddy",   model: "deepseek-v4.1-flash" },
      { name: "qa",      role: "数据与评测", provider: "workbuddy",   model: "glm-5.3-flash" },
      { name: "auditor", role: "独立监察",   provider: "antigravity", model: "gemini-3.8-flash" }
    ],
    tasks: [
      { id: "T1", subject: "...", assignee: "qa",      description: "..." },
      { id: "T2", subject: "...", assignee: "kernel",  description: "...", dependencies: ["T1"] },
      { id: "T3", subject: "...", assignee: "auditor", description: "...", dependencies: ["T2"] }
    ]
  }
})
```

要点：

- **不写 provider/model 就继承你自己的路由**，三个成员会全用同一个模型，制衡失效。
- **`approval: "required"`** 会先停在 staged 状态，要再调 `agent_teams_approve` 才开跑。
- `assignee` 必须写，否则任务进共享池没人领。
- `dependencies` 填 plan 里的种子 id。
- **子代理不能再派生子代理**（delegation depth 上限 1），只能一层。

## 3. 审批

```js
agent_teams_approve({ confirmation: "用户已授权立即执行" })
```

## 4. 看状态

```js
agent_teams_status({})
```

返回里有 `members`（status / activity）和 `tasks`（status / attempt / dependencies）。

## 5. 运行中调整

改依赖、改描述（**仅限尚未开始的任务**）：

```js
agent_teams_edit_plan({ operations: [
  { action: "update_task", task_id: "t3", dependencies: [] }
]})
```

重新派活 / 队长接管：

```js
agent_teams_reassign_task({ task_id: "t4", assignee: "kernel",  reason: "..." })
agent_teams_reassign_task({ task_id: "t4", assignee: "captain", reason: "成员零产出，队长接管" })
```

给成员发指令：

```js
agent_teams_send_message({ to: "kernel", content: "..." })
```

## 6. 收尾

```js
agent_teams_delete({})        // 归档并释放整支队
```

## 7. 两个坑

1. **成员可能被外部中断而零产出**。某成员连续两次 attempt 都没落盘文件，立刻 `reassign_task(assignee: "captain")` 自己干。
2. **`antigravity` 走 agy CLI 通道**，不如 workbuddy 稳。若 auditor 启动失败，降级到 `workbuddy/deepseek-v4.1-flash`，并在报告里记录这个偏离。
