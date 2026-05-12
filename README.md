# 软件测试平台

一个基于 Flask 的项目任务登记测试平台。

## 功能特性

- 🔐 用户登录系统
- 📋 项目任务登记与管理
- 👥 送测人、测试人员管理
- ⏰ 时间范围管理（开始时间-结束时间）
- 📊 数据分析（月度/季度/年度分析）
- 📈 完成进度跟踪
- ⚠️ 卡点问题记录
- 🔗 JIRA链接关联
- 📤 数据导入导出（CSV格式）
- 🔍 多条件筛选搜索

## 技术栈

- Python 3.14+
- Flask 2.3.3
- Flask-SQLAlchemy 3.1.1
- SQLite（数据库）

## 快速开始

### 安装依赖

```bash
pip install -r requirements.txt
```

### 启动服务

```bash
python app.py
```

### 访问地址

- 主页：http://localhost:5000
- 局域网访问：http://192.168.x.x:5000

### 默认账号

- 用户名：admin
- 密码：admin123

## 项目结构

```
├── app.py              # Flask应用主文件
├── requirements.txt    # 依赖配置
├── README.md          # 项目说明
├── .gitignore         # Git忽略配置
└── templates/         # HTML模板目录
    ├── home.html      # 主页
    ├── login.html     # 登录页
    ├── index.html     # 任务列表页
    ├── add.html       # 添加任务页
    ├── edit.html      # 编辑任务页
    └── analysis.html  # 数据分析页
```

## 使用说明

1. 登录系统后进入主页
2. 点击「测试项目」进入任务管理页面
3. 支持添加、编辑、删除任务
4. 可通过状态、测试人员、时间范围等条件筛选任务
5. 点击「数据分析」查看月度/季度/年度统计报告