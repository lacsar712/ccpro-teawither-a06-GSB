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
4. **WitherDutyCard（萎凋值班卡）**：归属茶园、`dutyDate`（值班日）、`shiftName`（班次名）、`maxOnDuty`（计划在岗槽数上限）、`supervisor`（值班主管名）；同一茶园同日同班次唯一

**业务规则**：

- 将槽位状态设为 `ready`（可下槽）时，若最新批次的 `actualMoisture` 为空或大于 40，抛出中文 `ValidationError`。
- 将槽位改入 `withering`（萎凋中）时，受当日值班卡上限约束（见下）。

### 萎凋在岗上限 · 计数口径

- **计数**：该园当前状态为「萎凋中」的槽数（实时状态，不分班次、不按批次）。
- **上限**：该园「值班日 = 今天」的最新值班卡的 `maxOnDuty`；同日多张班次卡时取**最近更新**的一张。
- **校验时机**：槽位由「装叶中」改「萎凋中」、由「可下槽」改回「萎凋中」、或新建槽位直接置「萎凋中」；已处「萎凋中」的槽重复保存不重复占名额。
- **拒绝条件**：当日无值班卡（提示先建卡），或当前萎凋中槽数已达上限。
- **生效时机**：上限修改保存后立即作用于后续改态；改态校验与茶园/值班卡列表共用同一计数函数（`count_withering` / `latest_duty_card`）。

## 种子数据

```bash
python manage.py seed_data
```

幂等：已有茶园则只保证账号存在。亦可在环境变量 `TEAWITHER_AUTO_SEED=1` 时于 `post_migrate` 自动播种。

种子含当日值班卡：一号园「早班」上限 1（已有一槽萎凋中，可演示超限拒绝）；二号园「早班」上限 3。

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
