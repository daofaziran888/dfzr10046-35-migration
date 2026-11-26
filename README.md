# 维链工坊 · 维度建模与缓慢变化维加工平台

面向维度注册、缓慢变化维拉链、一致性维度核对、事实表装配、代理键生成、维度退化、迟到事实回补、汇总层派生、指标口径绑定与维度快照发布的数仓维度建模加工平台。

这是一个前后端分离的管理平台：前端 Vue 3 + Vite + TypeScript，后端 FastAPI（Python）。
两边各自独立启动，前端 dev server 已关掉自动打开页面，启动后按终端打印的地址手工打开。

## 目录结构

```text
.
├── frontend/                 Vue 3 + Vite + TypeScript 前端
│   ├── src/views/WorkbenchView.vue|tsx  全部模块共享工作台
│   ├── src/views/BindingDetailView.vue  指标绑定直连工作台
│   ├── src/domain/metricBind.ts         绑定编辑会话与冲突分型
│   ├── src/data/modules.ts              18个业务模块配置
│   ├── src/api/              统一请求封装
│   └── vite.config.ts        dev server 配置（open: false）
├── backend/                  FastAPI（Python） 后端
│   ├── app/routers/resource.py  通用查询/导出/登记/动作接口
│   ├── app/services/<key>.py    每个模块独立领域逻辑
│   ├── app/services/base.py     共享服务骨架
│   └── app/store.py          内存数据仓库与示例数据
├── .gitignore
└── docker-compose.yml
```

## 启动

### 后端

```bash
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
./run.sh
```

健康检查：`curl http://127.0.0.1:8003/api/health`

### 前端

```bash
cd frontend
npm ci
npm run dev
```

前端默认监听 `http://127.0.0.1:5176/`，dev server 不会自动打开浏览器，
需要自己访问。`/api` 由 vite 代理到后端 `http://127.0.0.1:8003`。

## 业务模块

| 模块 | 目录 | 业务对象 | 主要字段 |
| --- | --- | --- | --- |
| 维度建档 | `dim_entry` | 维度条目 | 维度编号、维度名称、业务主键 |
| 拉链加工 | `scd_chain` | 拉链记录 | 拉链编号、所属维度、代理键 |
| 代理键生成 | `surrogate_key` | 代理键段 | 键段编号、所属维度、键段起点 |
| 一致性核对 | `conform_check` | 核对条目 | 核对编号、基准维度、对照维度 |
| 事实装配 | `fact_assemble` | 事实批次 | 批次编号、所属事实表、度量列集合 |
| 退化维度 | `degenerate_dim` | 退化维条目 | 条目编号、所属事实表、退化字段 |
| 迟到事实 | `late_fact` | 迟到记录 | 记录编号、所属事实表、业务发生日 |
| 汇总层派生 | `summary_layer` | 汇总条目 | 汇总编号、来源事实表、汇总粒度 |
| 粒度声明 | `grain_declare` | 粒度声明 | 声明编号、所属事实表、一行代表 |
| 度量目录 | `measure_catalog` | 度量条目 | 度量编号、度量名称、计算表达式 |
| 指标绑定 | `metric_bind` | 绑定关系 | 绑定编号、指标名称、引用度量 |
| 维度快照 | `dim_snapshot` | 快照版本 | 快照编号、所属维度、快照日期 |
| 层级路径 | `hier_path` | 层级路径 | 路径编号、所属维度、层级名称 |
| 多值桥接 | `bridge_link` | 桥接条目 | 桥接编号、所属事实表、关联维度 |
| 属性失效 | `attr_decay` | 失效条目 | 失效编号、所属维度、属性名称 |
| 装载窗口 | `load_window` | 装载窗口 | 窗口编号、所属事实表、窗口起点 |
| 重跑任务 | `reprocess_task` | 重跑任务 | 重跑编号、触发原因、影响事实表 |
| 装配质量闸 | `quality_gate` | 质量闸条目 | 闸口编号、所属事实表、校验项 |
| 血缘关系 | `lineage_edge` | 血缘边 | 血缘编号、上游对象、下游对象 |
| 维度发布 | `dim_publish` | 发布版本 | 发布编号、所属维度、发布版本 |
| 建模审计 | `model_audit` | 审计条目 | 条目编号、操作类型、操作对象 |
| 源端抽取 | `src_extract` | 抽取批次 | 抽取编号、来源系统、抽取范围 |

## 约定

- 全部模块共享`frontend/src/views/WorkbenchView.vue|tsx`和一套资源路由。
- 每个模块仍保留独立`backend/app/services/<模块>.py`；纯前端保留
  `frontend/src/domain/<模块>.ts`，用于承载真实业务差异并维持36题位容量。
- 列表接口统一返回 `{ items, total, page, size }`，动作接口统一返回 `{ ok, message }`。
- 状态流转只允许在 `app/services` 里改，路由层不做业务判断。

## 指标绑定：直连路由与并发编辑

指标绑定的存量入口 `/metric_bind` 仍然打开列表工作台，团队的旧书签、收藏链接
（包括 `/metric_bind?bind=BND-002`、`/metric_bind?keyword=BND-002` 和
`/metric_bind/BND-002`）都会解析回同一份绑定。新链接 `/metric_bind/<绑定 id>`
可直接打开指定绑定的工作台，两个入口共存，分批部署与回退期间都能进入原工作台。

- `GET /api/metric_bind/{id}/context`：绑定归属、引用度量快照、可编辑性与后续动作。
  绑定已失效（已替换/已解除）时仍返回归属，并给出复制为新绑定、重新启用、
  查看引用度量、回到列表等可执行动作。
- `GET /api/metric_bind/by-code/{绑定编号}`：老书签只带编号时兜底解析。
- `POST /api/metric_bind/{id}/edit`：绑定页从度量目录选完度量后提交，同时核对
  绑定与度量两份 `revision`。
- `PATCH /api/metric_bind/{id}`、`PATCH /api/measure_catalog/{id}`：带版本号的
  字段更新，用于并发演示与正常编辑。

提交冲突按两个维度分型，回包里的 `canKeepMeasure` 与 `mustReconfirm` 就是
“能否沿用当前所选度量”“是否须重新取得编辑确认”：

| 冲突类型 | 触发条件 | 能否沿用所选度量 | 是否须重新确认 |
| --- | --- | --- | --- |
| `binding_changed` | 仅绑定被他人修改 | 可以 | 必须 |
| `measure_changed` | 仅所选度量被他人修改 | 不能 | 不必 |
| `binding_and_measure_changed` | 两者都被修改 | 不能 | 必须 |
| `binding_invalid` / `measure_missing` | 绑定失效、度量不存在 | 不能 | 不必 |

前端编辑草稿按“编辑会话”存放（`frontend/src/domain/metricBind.ts`），会话标识写在
地址栏 `session` 参数里，同一编号的两个页面各持一份草稿、互不覆盖；从度量目录
选完度量后用 `replace` 返回发起编辑的那份绑定，后退、刷新与旧入口回退都能找回
同一对象与草稿。绑定被改的冲突可“沿用所选度量并重新确认”，度量被改的冲突则须
重新选择度量，只有版本对齐后才允许提交。


领域：数据工程
子方向：数仓与数据湖
