# TeaWither-01 · 茶萎凋台账

Django 5 + PostgreSQL 服务端渲染应用：Templates + HTMX + 自定义 CSS，无 Vue/React SPA。

## 技术栈

- Django 5、PostgreSQL
- Session 登录
- HTMX（CDN）局部刷新列表
- Docker Compose：`web` + `db`

## 端口与数据库

| 服务 | 端口 |
|------|------|
| Web  | **4100** |
| Postgres | **5440**（容器内 5432） |

数据库账号：`teawither` / `teawither` / 库名 `teawither`

## 快速启动

```bash
cd TeaWither/TeaWither-01
docker compose up --build -d
```

浏览器打开：http://localhost:4100

演示账号：

- `admin` / `123456`（超级用户）
- `witherer` / `123456`（普通用户）

容器启动时会自动：`migrate` → `seed_data` → `collectstatic` → `gunicorn`

## 本地开发（可选）

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
pip install -r requirements.txt
# 确保本机 Postgres 监听 5440，或先 docker compose up -d db
set POSTGRES_HOST=localhost
set POSTGRES_PORT=5440
python manage.py migrate
python manage.py seed_data
python manage.py runserver 0.0.0.0:4100
```

## 业务模型

1. **Garden（茶园）**：`name`、`altitudeBand`、`notes`
2. **Trough（萎凋槽）**：归属茶园、`troughCode`、`cultivar`、`loadKg`、状态 `loading|withering|ready`；同一茶园内槽位编号唯一
3. **WitherBatch（萎凋批次）**：归属槽位、`startedAt`、`targetMoisture`、`actualMoisture`（可空）、`rollGrade`
4. **WitherDutyCard（萎凋值班卡）**：`garden`、`dutyDate`（值班日）、`shiftName`（班次名）、`maxOnDuty`（计划在岗槽数上限）、`supervisor`（值班主管名）；**同园同日同班次唯一**

**业务规则**：

- 将槽位状态设为 `ready`（可下槽）时，若最新批次的 `actualMoisture` 为空或大于 40，抛出中文 `ValidationError`。
- 把槽位**改入 `withering`（萎凋中）**——包括 `loading → withering`、`ready → withering`（可下槽改回）以及新建即萎凋中——受当日值班卡上限约束，规则在 `Trough.clean()` 中执行，表单、Admin、命令行保存均生效。

### 计数口径（萎凋在岗上限）

- **计数**：该茶园当前状态为「萎凋中」的槽数；「装叶中」「可下槽」不计入。
- **上限**：该园**当日**（服务器本地日期，`Asia/Shanghai`）**最近更新**的一张值班卡的 `maxOnDuty`；同日多班次各有一卡时，取 `updatedAt` 最新者（从未编辑过即最新创建的一张）。
- **拒绝条件**：该园当日**无任何值班卡** → 拒绝并提示先建卡；当前萎凋中数 **≥ 上限** → 拒绝。原本已是「萎凋中」的槽再次保存不重复占额。
- **生效时机**：每次改态实时查询最新值班卡，上限修改后立即作用于后续改态，无需重启。
- **共用函数**：改态校验与茶园列表的「当日上限 / 当前萎凋中」列共用 `apps/gardens/services.py` 中的 `wither_capacity` / `withering_count` / `latest_duty_card`，全站同一口径。

## 种子数据

```bash
python manage.py seed_data
```

幂等：已有茶园则只保证账号存在。亦可在环境变量 `TEAWITHER_AUTO_SEED=1` 时于 `post_migrate` 自动播种。

种子包含当日值班卡：**云雾岭一号园上限 1 且已有一槽（A-01）萎凋中**——把 A-02 改入「萎凋中」会被拒绝，可直接演示超限拦截；竹影台二号园上限 2。

## 目录结构

```
TeaWither-01/
  manage.py
  requirements.txt
  Dockerfile
  entrypoint.sh
  docker-compose.yml
  config/           # 项目配置
  apps/gardens/     # 模型、视图、种子命令
  templates/        # Django 模板
  static/css/       # 自定义样式（茶绿色顶栏）
```
