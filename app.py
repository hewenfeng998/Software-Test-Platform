from flask import Flask, render_template, request, redirect, url_for, flash, session, make_response, jsonify, send_file
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from collections import defaultdict
from functools import wraps
import csv
from io import StringIO
from urllib.parse import quote, urlencode
import requests
import json
import os
import time
import threading

FEISHU_WEBHOOK_URL = 'https://open.feishu.cn/open-apis/bot/v2/hook/deea26d5-c11e-4c21-88d1-2f25d29b1d88'

HEARTBEAT_TIMEOUT = 30

def check_offline_machines():
    while True:
        try:
            with app.app_context():
                current_time = time.time()
                
                machines = Machine.query.all()
                for machine in machines:
                    if machine.status == 'online':
                        if machine.id in last_heartbeat:
                            elapsed = current_time - last_heartbeat[machine.id]
                            if elapsed >= HEARTBEAT_TIMEOUT:
                                try:
                                    del last_heartbeat[machine.id]
                                    machine.status = 'offline'
                                    db.session.commit()
                                    print(f"机器 {machine.id} ({machine.name}) 已离线")
                                except Exception as e:
                                    print(f"更新机器状态失败: {e}")
                        else:
                            machine.status = 'offline'
                            db.session.commit()
                            print(f"机器 {machine.id} ({machine.name}) 无心跳记录，标记为离线")
        except Exception as e:
            print(f"离线检测错误: {e}")
        
        time.sleep(5)

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///tasks_v4.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'secret_key_here_2026'

db = SQLAlchemy(app)

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(100), nullable=False)
    name = db.Column(db.String(50), nullable=True)
    is_active = db.Column(db.Boolean, default=False)
    role = db.Column(db.String(20), default='viewer')
    can_access_performance = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<User {self.username}>'
    
    def is_admin(self):
        return self.role == 'admin'
    
    def can_edit(self):
        return self.role in ['admin', 'editor']
    
    def can_delete(self):
        return self.role == 'admin'
    
    def can_access_performance(self):
        return self.can_access_performance or self.role == 'admin'
    
    def can_view(self):
        return self.role in ['admin', 'editor', 'viewer']

class Task(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), default='待处理')
    priority = db.Column(db.String(20), default='中等')
    submitter = db.Column(db.String(50), nullable=True)
    tester = db.Column(db.String(50), nullable=True)
    industry = db.Column(db.String(50), nullable=True)
    jira_link = db.Column(db.String(255), nullable=True)
    test_result = db.Column(db.String(10), nullable=True)
    test_round = db.Column(db.String(10), nullable=True)
    di_value = db.Column(db.Float, nullable=True)
    start_date = db.Column(db.Date, nullable=True)
    end_date = db.Column(db.Date, nullable=True)
    progress = db.Column(db.Integer, default=0)
    blockers = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f'<Task {self.title}>'

INDUSTRY_OPTIONS = ['金融', '电商', '医疗', '教育', '科技', '制造', '零售', '其他']
TEST_RESULT_OPTIONS = ['PASS', 'FAIL', 'N/A']
TEST_ROUND_OPTIONS = ['A1', 'A2', 'A3', 'A4', 'A5', 'A6', 'A7', 'A8', 'A9', 'A10']

class LoginLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    username = db.Column(db.String(50), nullable=False)
    login_time = db.Column(db.DateTime, default=datetime.utcnow)
    ip_address = db.Column(db.String(50))

    def __repr__(self):
        return f'<LoginLog {self.username} {self.login_time}>'

class Tool(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)
    file_path = db.Column(db.String(255), nullable=False)
    file_name = db.Column(db.String(255), nullable=False)
    file_size = db.Column(db.Integer, nullable=False)
    uploader_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    uploader_name = db.Column(db.String(50), nullable=False)
    upload_time = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<Tool {self.name}>'

class Machine(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    os_type = db.Column(db.String(20), nullable=False)
    ip_address = db.Column(db.String(50), nullable=False)
    port = db.Column(db.Integer, nullable=False)
    cpu = db.Column(db.String(20), nullable=True)
    memory = db.Column(db.String(20), nullable=True)
    username = db.Column(db.String(50), nullable=True)
    password = db.Column(db.String(100), nullable=True)
    status = db.Column(db.String(20), default='offline')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f'<Machine {self.name} {self.ip_address}>'

ROLES = [
    ('admin', '管理员'),
    ('editor', '编辑'),
    ('viewer', '浏览')
]

def send_feishu_notification(task):
    """发送飞书群机器人通知"""
    try:
        title = task.title[:50] + '...' if len(task.title) > 50 else task.title
        content = f"""
**📋 测试任务提醒**

**任务标题**: {title}
**送测人**: {task.submitter or '-'}
**测试人员**: {task.tester or '-'}
**所属行业**: {task.industry or '-'}
**测试结果**: {task.test_result or '-'}
**送测轮次**: {task.test_round or '-'}
**DI数值**: {task.di_value or '-'}
**测试时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        """.strip()
        
        payload = {
            "msg_type": "text",
            "content": {
                "text": content
            }
        }
        
        response = requests.post(FEISHU_WEBHOOK_URL, data=json.dumps(payload), headers={'Content-Type': 'application/json'})
        return response.status_code == 200
    except Exception as e:
        print(f"发送飞书消息失败: {str(e)}")
        return False

def send_feishu_report(period_name, total_tasks, status_counts, avg_progress, blocker_count, pass_count, test_round_pass_rate):
    """发送项目分析报告到飞书群"""
    try:
        pass_rates = []
        for round_name in ['A1', 'A2', 'A3', 'A4', 'A5', 'A6', 'A7', 'A8', 'A9', 'A10']:
            round_data = test_round_pass_rate.get(round_name, {'total': 0, 'pass': 0, 'rate': 0})
            if round_data['total'] > 0:
                pass_rates.append(f"{round_name}: {round_data['pass']}/{round_data['total']} ({round_data['rate']}%)")
        
        pass_rate_text = '\n'.join(pass_rates) if pass_rates else '暂无数据'
        
        content = f"""
**📊 {period_name}项目分析报告**

**📈 概览统计**
- 总任务数: {total_tasks}
- 待处理: {status_counts.get('待处理', 0)}
- 进行中: {status_counts.get('进行中', 0)}
- 已完成: {status_counts.get('已完成', 0)}
- 异常中断: {status_counts.get('异常中断', 0)}
- 送测打回: {status_counts.get('送测打回', 0)}
- 平均进度: {avg_progress}%
- 测试NG: {blocker_count}
- 定版项目: {pass_count}

**✅ 测试轮次通过率**
{pass_rate_text}

**📅 生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        """.strip()
        
        payload = {
            "msg_type": "text",
            "content": {
                "text": content
            }
        }
        
        response = requests.post(FEISHU_WEBHOOK_URL, data=json.dumps(payload), headers={'Content-Type': 'application/json'})
        return response.status_code == 200
    except Exception as e:
        print(f"发送飞书报告失败: {str(e)}")
        return False

def send_feishu_report_with_html(period_name, total_tasks, status_counts, avg_progress, blocker_count, pass_count, test_round_pass_rate, html_content):
    """发送项目分析报告到飞书群（包含HTML附件链接）"""
    import sys
    print(f"=== 开始发送报告 ===", flush=True)
    print(f"period_name: {period_name}", flush=True)
    print(f"total_tasks: {total_tasks}", flush=True)
    try:
        import io
        
        pass_rates = []
        for round_name in ['A1', 'A2', 'A3', 'A4', 'A5', 'A6', 'A7', 'A8', 'A9', 'A10']:
            round_data = test_round_pass_rate.get(round_name, {'total': 0, 'pass': 0, 'rate': 0})
            if round_data['total'] > 0:
                pass_rates.append(f"{round_name}: {round_data['pass']}/{round_data['total']} ({round_data['rate']}%)")
        
        pass_rate_text = '\n'.join(pass_rates) if pass_rates else '暂无数据'
        
        filename = f"{period_name}项目分析报告.html"
        file_data = io.BytesIO(html_content.encode('utf-8'))
        
        upload_url = 'https://gch.test.seewo.com/performance/v1/auto/upload/report'
        
        upload_data = {
            'test_id': 'cc6099abc9bd4380b0f938241bd8fc99',
            'mac': '38:7A:0E:2C:B4:51',
            'app_name': '希沃白板展台',
            'report_name': filename,
            'app_version': '2.0.5.1764',
            'report_detail': '{}',
            'sys_info': '{"arch": "x86_64", "system": {"Distributor ID": "Uos", "Description": "Microsoft Windows 11", "Release": "20", "Codename": "eagle"}}',
            'script_type': 'python'
        }
        
        files = {
            'file': (filename, file_data, 'text/html')
        }
        
        headers = {
            'User-Agent': 'Apifox/1.0.0 (https://apifox.com)'
        }
        
        report_url = None
        try:
            print(f"开始上传文件到 {upload_url}", flush=True)
            print(f"文件名: {filename}, 文件大小: {len(html_content)} bytes", flush=True)
            response = requests.post(upload_url, data=upload_data, files=files, headers=headers, timeout=60)
            print(f"上传响应状态码: {response.status_code}", flush=True)
            print(f"上传响应内容长度: {len(response.text)}", flush=True)
            print(f"上传响应内容: {response.text[:1000]}", flush=True)
            
            try:
                result = response.json()
                print(f"上传响应JSON: {result}", flush=True)
                
                if result.get('code') == 0 or result.get('success'):
                    data_field = result.get('data')
                    if isinstance(data_field, dict):
                        report_url = data_field.get('url')
                    elif isinstance(data_field, str):
                        report_url = data_field
                    else:
                        report_url = result.get('url')
                    print(f"报告上传成功，URL: {report_url}", flush=True)
                else:
                    print(f"上传失败: {result.get('msg', result.get('message', '未知错误'))}", flush=True)
            except Exception as json_error:
                print(f"解析JSON失败: {str(json_error)}", flush=True)
                print(f"响应内容: {response.text}", flush=True)
        except Exception as upload_error:
            print(f"上传异常: {str(upload_error)}", flush=True)
            print(f"异常类型: {type(upload_error).__name__}", flush=True)
        
        content = f"""
**📊 {period_name}项目分析报告**

**📈 概览统计**
- 总任务数: {total_tasks}
- 待处理: {status_counts.get('待处理', 0)}
- 进行中: {status_counts.get('进行中', 0)}
- 已完成: {status_counts.get('已完成', 0)}
- 异常中断: {status_counts.get('异常中断', 0)}
- 送测打回: {status_counts.get('送测打回', 0)}
- 平均进度: {avg_progress}%
- 测试NG: {blocker_count}
- 定版项目: {pass_count}

**✅ 测试轮次通过率**
{pass_rate_text}

**📅 生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        """.strip()
        
        if report_url:
            content += "\n\n【查看完整报告】: " + report_url
        
        payload = {
            "msg_type": "text",
            "content": {
                "text": content
            }
        }
        
        response = requests.post(FEISHU_WEBHOOK_URL, data=json.dumps(payload), headers={'Content-Type': 'application/json'}, timeout=30)
        return response.status_code == 200
    except Exception as e:
        print(f"发送飞书报告失败: {str(e)}")
        return False

with app.app_context():
    db.create_all()
    
    from sqlalchemy import inspect
    inspector = inspect(db.engine)
    columns = inspector.get_columns('task')
    column_names = [col['name'] for col in columns]
    
    if 'industry' not in column_names:
        with db.engine.connect() as conn:
            conn.execute(db.text('ALTER TABLE task ADD COLUMN industry VARCHAR(50)'))
            conn.commit()
    
    if 'jira_link' not in column_names:
        with db.engine.connect() as conn:
            conn.execute(db.text('ALTER TABLE task ADD COLUMN jira_link VARCHAR(255)'))
            conn.commit()
    
    if 'test_result' not in column_names:
        with db.engine.connect() as conn:
            conn.execute(db.text('ALTER TABLE task ADD COLUMN test_result VARCHAR(10)'))
            conn.commit()
    
    if 'test_round' not in column_names:
        with db.engine.connect() as conn:
            conn.execute(db.text('ALTER TABLE task ADD COLUMN test_round VARCHAR(10)'))
            conn.commit()
    
    if 'di_value' not in column_names:
        with db.engine.connect() as conn:
            conn.execute(db.text('ALTER TABLE task ADD COLUMN di_value FLOAT'))
            conn.commit()
    
    if not User.query.filter_by(username='admin').first():
        admin_user = User(username='admin', password='admin123', name='管理员', is_active=True, role='admin')
        db.session.add(admin_user)
        db.session.commit()

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        name = request.form['name']
        password = request.form['password']
        confirm_password = request.form['confirm_password']

        if password != confirm_password:
            flash('两次输入的密码不一致！')
            return redirect(url_for('register'))

        if User.query.filter_by(username=username).first():
            flash('用户名已存在！')
            return redirect(url_for('register'))

        new_user = User(username=username, password=password, name=name, is_active=False, is_admin=False)
        db.session.add(new_user)
        db.session.commit()
        flash('注册成功！请等待管理员审核')
        return redirect(url_for('login'))

    return render_template('register.html')

STATUS_OPTIONS = ['待处理', '进行中', '已完成', '异常中断', '送测打回']

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('请先登录！')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('请先登录！')
            return redirect(url_for('login'))
        user = User.query.get(session['user_id'])
        if not user or not user.is_admin():
            flash('无权限访问！')
            return redirect(url_for('home'))
        return f(*args, **kwargs)
    return decorated_function

def editor_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('请先登录！')
            return redirect(url_for('login'))
        user = User.query.get(session['user_id'])
        if not user or not user.can_edit():
            flash('无权限访问！')
            return redirect(url_for('home'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/login', methods=['GET', 'POST'])
def login():
    hostname = socket.gethostname()
    local_ip = get_local_ip()
    
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        user = User.query.filter_by(username=username).first()
        
        if not user:
            flash('用户名或密码错误！')
            return render_template('login.html', hostname=hostname, local_ip=local_ip)
            
        if not user.is_active:
            flash('账号未通过审核，请联系管理员！')
            return render_template('login.html', hostname=hostname, local_ip=local_ip)
            
        if user.password == password:
            session['user_id'] = user.id
            session['username'] = user.username
            session['name'] = user.name
            session['role'] = user.role
            session['is_admin'] = user.is_admin()
            
            ip_address = request.remote_addr
            login_log = LoginLog(user_id=user.id, username=user.username, ip_address=ip_address)
            db.session.add(login_log)
            db.session.commit()
            
            flash(f'欢迎回来，{user.name}！')
            return redirect(url_for('home'))
        else:
            flash('用户名或密码错误！')
    
    return render_template('login.html', hostname=hostname, local_ip=local_ip)

@app.route('/logout')
def logout():
    session.clear()
    flash('已退出登录')
    return redirect(url_for('login'))

import socket

def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0)
        try:
            s.connect(('10.255.255.255', 1))
        except:
            s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return '127.0.0.1'

@app.route('/performance')
@login_required
def performance():
    user = User.query.get(session['user_id'])
    if not user.can_access_performance():
        abort(403)
    
    return render_template('performance.html', user=user)

@app.route('/')
@login_required
def home():
    user = User.query.get(session['user_id'])
    hostname = socket.gethostname()
    local_ip = get_local_ip()
    return render_template('home.html', 
                           is_admin=user.is_admin(), 
                           role=user.role, 
                           can_access_performance=user.can_access_performance(),
                           hostname=hostname, 
                           local_ip=local_ip)

@app.route('/project')
@login_required
def index():
    user = User.query.get(session['user_id'])
    tasks = Task.query

    start_filter = request.args.get('start_filter')
    end_filter = request.args.get('end_filter')
    status_filter = request.args.get('status_filter')
    search_keyword = request.args.get('search')
    tester_filter = request.args.get('tester_filter')
    page = request.args.get('page', 1, type=int)
    per_page = 10

    if search_keyword:
        tasks = tasks.filter(Task.title.like(f'%{search_keyword}%'))

    tester_filters = request.args.getlist('tester_filter')
    if tester_filters and tester_filters != ['all'] and tester_filters != []:
        if 'all' not in tester_filters:
            tasks = tasks.filter(Task.tester.in_(tester_filters))

    industry_filters = request.args.getlist('industry_filter')
    if industry_filters and industry_filters != ['all'] and industry_filters != []:
        if 'all' not in industry_filters:
            tasks = tasks.filter(Task.industry.in_(industry_filters))

    if start_filter:
        try:
            start_date = datetime.strptime(start_filter, '%Y-%m-%d').date()
            tasks = tasks.filter(Task.start_date >= start_date)
        except:
            pass

    if end_filter:
        try:
            end_date = datetime.strptime(end_filter, '%Y-%m-%d').date()
            tasks = tasks.filter(Task.end_date <= end_date)
        except:
            pass

    status_filters = request.args.getlist('status_filter')
    if status_filters and status_filters != ['all'] and status_filters != []:
        if 'all' not in status_filters:
            tasks = tasks.filter(Task.status.in_(status_filters))

    tasks = tasks.order_by(Task.created_at.desc()).paginate(page=page, per_page=per_page, error_out=False)
    
    testers = Task.query.with_entities(Task.tester).distinct().filter(Task.tester.isnot(None)).all()
    tester_list = [t[0] for t in testers]
    
    industries = Task.query.with_entities(Task.industry).distinct().filter(Task.industry.isnot(None)).all()
    industry_list = [i[0] for i in industries]

    return render_template('index.html', tasks=tasks.items,
                           pagination=tasks,
                           start_filter=start_filter, end_filter=end_filter,
                           status_filter=status_filter,
                           status_filter_list=status_filters,
                           search_keyword=search_keyword,
                           tester_filter=tester_filter,
                           tester_filter_list=tester_filters,
                           industry_filter_list=industry_filters,
                           is_admin=user.is_admin(),
                           tester_list=tester_list,
                           industry_list=industry_list,
                           can_edit=user.can_edit(),
                           can_delete=user.can_delete(),
                           current_page=page)

@app.route('/add', methods=['GET', 'POST'])
@editor_required
def add_task():
    if request.method == 'POST':
        title = request.form['title']
        description = request.form['description']
        status = request.form['status']
        priority = request.form['priority']
        submitter = request.form['submitter']
        tester = request.form['tester']
        industry = request.form['industry']
        jira_link = request.form['jira_link']
        test_result = request.form['test_result']
        test_round = request.form['test_round']
        di_value = float(request.form['di_value']) if request.form['di_value'] else None
        start_date = request.form['start_date']
        end_date = request.form['end_date']
        progress = int(request.form['progress']) if request.form['progress'] else 0
        blockers = request.form['blockers']

        start_date_val = datetime.strptime(start_date, '%Y-%m-%d').date() if start_date else None
        end_date_val = datetime.strptime(end_date, '%Y-%m-%d').date() if end_date else None

        new_task = Task(
            title=title,
            description=description,
            status=status,
            priority=priority,
            submitter=submitter,
            tester=tester,
            industry=industry,
            jira_link=jira_link,
            test_result=test_result if test_result else None,
            test_round=test_round if test_round else None,
            di_value=di_value,
            start_date=start_date_val,
            end_date=end_date_val,
            progress=progress,
            blockers=blockers
        )
        db.session.add(new_task)
        db.session.commit()
        flash('任务添加成功！')
        return redirect(url_for('index'))

    return render_template('add.html', industries=INDUSTRY_OPTIONS, 
                           test_result_options=TEST_RESULT_OPTIONS,
                           test_round_options=TEST_ROUND_OPTIONS)

@app.route('/edit/<int:id>', methods=['GET', 'POST'])
@editor_required
def edit_task(id):
    task = Task.query.get_or_404(id)

    if request.method == 'POST':
        task.title = request.form['title']
        task.description = request.form['description']
        task.status = request.form['status']
        task.priority = request.form['priority']
        task.submitter = request.form['submitter']
        task.tester = request.form['tester']
        task.industry = request.form['industry']
        task.jira_link = request.form['jira_link']
        task.test_result = request.form['test_result'] if request.form['test_result'] else None
        task.test_round = request.form['test_round'] if request.form['test_round'] else None
        task.di_value = float(request.form['di_value']) if request.form['di_value'] else None
        task.start_date = datetime.strptime(request.form['start_date'], '%Y-%m-%d').date() if request.form['start_date'] else None
        task.end_date = datetime.strptime(request.form['end_date'], '%Y-%m-%d').date() if request.form['end_date'] else None
        task.progress = int(request.form['progress']) if request.form['progress'] else 0
        task.blockers = request.form['blockers']
        db.session.commit()
        flash('任务更新成功！')
        
        page = request.form.get('page', 1, type=int)
        search = request.form.get('search', '')
        start_filter = request.form.get('start_filter', '')
        end_filter = request.form.get('end_filter', '')
        tester_filters = request.form.getlist('tester_filter')
        status_filters = request.form.getlist('status_filter')
        industry_filters = request.form.getlist('industry_filter')
        
        query_parts = [f'page={page}']
        if search:
            query_parts.append(f'search={quote(search)}')
        if start_filter:
            query_parts.append(f'start_filter={quote(start_filter)}')
        if end_filter:
            query_parts.append(f'end_filter={quote(end_filter)}')
        for tester in tester_filters:
            if tester and tester != 'all':
                query_parts.append(f'tester_filter={quote(tester)}')
        for status in status_filters:
            if status and status != 'all':
                query_parts.append(f'status_filter={quote(status)}')
        for industry in industry_filters:
            if industry and industry != 'all':
                query_parts.append(f'industry_filter={quote(industry)}')
        
        query_string = '&'.join(query_parts)
        redirect_url = url_for('index') + '?' + query_string
        return redirect(redirect_url)

    return render_template('edit.html', task=task, industries=INDUSTRY_OPTIONS,
                           test_result_options=TEST_RESULT_OPTIONS,
                           test_round_options=TEST_ROUND_OPTIONS)

@app.route('/delete/<int:id>')
@login_required
def delete_task(id):
    user = User.query.get(session['user_id'])
    
    if not user.is_admin():
        flash('您没有删除权限！')
        return redirect(url_for('index'))
    
    task = Task.query.get_or_404(id)
    db.session.delete(task)
    db.session.commit()
    flash('任务删除成功！')
    
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '')
    start_filter = request.args.get('start_filter', '')
    end_filter = request.args.get('end_filter', '')
    tester_filters = request.args.getlist('tester_filter')
    status_filters = request.args.getlist('status_filter')
    industry_filters = request.args.getlist('industry_filter')
    
    query_parts = [f'page={page}']
    if search:
        query_parts.append(f'search={quote(search)}')
    if start_filter:
        query_parts.append(f'start_filter={quote(start_filter)}')
    if end_filter:
        query_parts.append(f'end_filter={quote(end_filter)}')
    for tester in tester_filters:
        if tester and tester != 'all':
            query_parts.append(f'tester_filter={quote(tester)}')
    for status in status_filters:
        if status and status != 'all':
            query_parts.append(f'status_filter={quote(status)}')
    for industry in industry_filters:
        if industry and industry != 'all':
            query_parts.append(f'industry_filter={quote(industry)}')
    
    query_string = '&'.join(query_parts)
    redirect_url = url_for('index') + '?' + query_string
    return redirect(redirect_url)

@app.route('/delete_all_tasks', methods=['POST'])
@login_required
def delete_all_tasks():
    user = User.query.get(session['user_id'])
    
    if not user.is_admin():
        return jsonify({'success': False, 'message': '权限不足'}), 403
    
    data = request.get_json()
    password = data.get('password', '')
    
    if password != '88889999':
        return jsonify({'success': False, 'message': '密码错误'}), 401
    
    Task.query.delete()
    db.session.commit()
    flash('所有任务已删除！')
    return jsonify({'success': True}), 200

@app.route('/automation')
@login_required
def automation():
    return render_template('automation.html')

@app.route('/wiki')
@login_required
def wiki():
    return render_template('wiki.html')

@app.route('/ai')
@login_required
def ai():
    return render_template('ai.html')

@app.route('/cabinet')
@login_required
def cabinet():
    return render_template('cabinet.html')

@app.route('/ai_interviewer')
@login_required
def ai_interviewer():
    return render_template('ai_interviewer.html')

@app.route('/tools', methods=['GET', 'POST'])
@login_required
def tools():
    import os
    
    UPLOAD_FOLDER = 'uploads'
    if not os.path.exists(UPLOAD_FOLDER):
        os.makedirs(UPLOAD_FOLDER)
    
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('请选择要上传的文件', 'error')
            return redirect(url_for('tools'))
        
        file = request.files['file']
        if file.filename == '':
            flash('请选择要上传的文件', 'error')
            return redirect(url_for('tools'))
        
        if file:
            name = request.form.get('name', '')
            description = request.form.get('description', '')
            
            if not name:
                flash('请输入工具名称', 'error')
                return redirect(url_for('tools'))
            
            filename = file.filename
            file_path = os.path.join(UPLOAD_FOLDER, filename)
            
            counter = 1
            while os.path.exists(file_path):
                name_parts = filename.rsplit('.', 1)
                if len(name_parts) == 2:
                    filename = f"{name_parts[0]}_{counter}.{name_parts[1]}"
                else:
                    filename = f"{filename}_{counter}"
                file_path = os.path.join(UPLOAD_FOLDER, filename)
                counter += 1
            
            file.save(file_path)
            file_size = os.path.getsize(file_path)
            
            user = User.query.get(session['user_id'])
            
            new_tool = Tool(
                name=name,
                description=description,
                file_path=file_path,
                file_name=filename,
                file_size=file_size,
                uploader_id=user.id,
                uploader_name=user.name or user.username
            )
            
            db.session.add(new_tool)
            db.session.commit()
            
            flash('工具上传成功', 'success')
            return redirect(url_for('tools'))
    
    tools_list = Tool.query.order_by(Tool.upload_time.desc()).all()
    return render_template('tools.html', tools=tools_list)

@app.route('/tools/download/<int:tool_id>')
@login_required
def download_tool(tool_id):
    import os
    from flask import send_from_directory
    
    tool = Tool.query.get_or_404(tool_id)
    
    try:
        return send_from_directory(
            directory=os.path.dirname(tool.file_path),
            path=os.path.basename(tool.file_path),
            as_attachment=True,
            download_name=tool.file_name
        )
    except Exception as e:
        flash(f'下载失败: {str(e)}', 'error')
        return redirect(url_for('tools'))

@app.route('/tools/delete/<int:tool_id>')
@login_required
def delete_tool(tool_id):
    import os
    
    tool = Tool.query.get_or_404(tool_id)
    user = User.query.get(session['user_id'])
    
    if user.role != 'admin':
        flash('只有管理员可以删除工具', 'error')
        return redirect(url_for('tools'))
    
    try:
        if os.path.exists(tool.file_path):
            os.remove(tool.file_path)
        
        db.session.delete(tool)
        db.session.commit()
        flash('工具删除成功', 'success')
    except Exception as e:
        flash(f'删除失败: {str(e)}', 'error')
    
    return redirect(url_for('tools'))

@app.route('/gantt')
@login_required
def gantt():
    tasks = Task.query.all()
    tester_tasks = {}
    
    for task in tasks:
        tester = task.tester or '未分配'
        if tester not in tester_tasks:
            tester_tasks[tester] = []
        tester_tasks[tester].append({
            'id': str(task.id),
            'name': task.title,
            'start': task.start_date.strftime('%Y-%m-%d') if task.start_date else None,
            'end': task.end_date.strftime('%Y-%m-%d') if task.end_date else None,
            'progress': task.progress or 0,
            'status': task.status,
            'title_full': task.title,
            'test_result': task.test_result or '-',
            'test_round': task.test_round or '-',
            'di_value': task.di_value or '-'
        })
    
    for tester in tester_tasks:
        tester_tasks[tester].sort(key=lambda x: x['start'] if x['start'] else '9999-12-31')
    
    return render_template('gantt.html', tester_tasks=tester_tasks)

@app.route('/analysis')
@login_required
def analysis():
    period_type = request.args.get('period_type', 'monthly')
    year = request.args.get('year', datetime.now().year)
    month = request.args.get('month', datetime.now().month)
    quarter = request.args.get('quarter', 1)
    industry_filter = request.args.get('industry_filter', 'all')

    try:
        year = int(year)
        month = int(month)
        quarter = int(quarter)
    except:
        year = datetime.now().year
        month = datetime.now().month
        quarter = 1

    if period_type == 'monthly':
        start_date = datetime(year, month, 1)
        if month == 12:
            end_date = datetime(year + 1, 1, 1)
        else:
            end_date = datetime(year, month + 1, 1)
        period_name = f"{year}年{month}月"
    elif period_type == 'quarterly':
        quarter_start_month = (quarter - 1) * 3 + 1
        start_date = datetime(year, quarter_start_month, 1)
        if quarter_start_month + 3 > 12:
            end_date = datetime(year + 1, quarter_start_month + 3 - 12, 1)
        else:
            end_date = datetime(year, quarter_start_month + 3, 1)
        period_name = f"{year}年第{quarter}季度"
    else:
        start_date = datetime(year, 1, 1)
        end_date = datetime(year + 1, 1, 1)
        period_name = f"{year}年度"

    start_date_only = start_date.date() if isinstance(start_date, datetime) else start_date
    end_date_only = end_date.date() if isinstance(end_date, datetime) else end_date
    
    tasks = Task.query.filter(
        Task.start_date.isnot(None),
        Task.start_date >= start_date_only,
        Task.start_date < end_date_only
    )

    if industry_filter and industry_filter != 'all':
        tasks = tasks.filter(Task.industry == industry_filter)
    
    tasks = tasks.all()

    status_counts = defaultdict(int)
    industry_counts = defaultdict(int)
    test_result_counts = defaultdict(int)
    tester_counts = defaultdict(int)
    test_round_pass_rate = {}
    total_tasks = len(tasks)
    avg_progress = 0
    blocker_count = 0

    for task in tasks:
        status_counts[task.status] += 1
        if task.industry:
            industry_counts[task.industry] += 1
        if task.test_result:
            test_result_counts[task.test_result] += 1
        if task.tester:
            tester_counts[task.tester] += 1
        avg_progress += task.progress
        if task.blockers:
            blocker_count += 1

    round_pass_counts = {}
    for round_name in TEST_ROUND_OPTIONS:
        round_tasks = [t for t in tasks if t.test_round == round_name]
        round_pass = sum(1 for t in round_tasks if t.test_result == 'PASS')
        round_pass_counts[round_name] = round_pass
    
    total_pass = sum(round_pass_counts.values())
    
    for round_name in TEST_ROUND_OPTIONS:
        round_tasks = [t for t in tasks if t.test_round == round_name]
        round_total = len(round_tasks)
        round_pass = round_pass_counts[round_name]
        if total_pass > 0:
            test_round_pass_rate[round_name] = {'total': round_total, 'pass': round_pass, 'rate': round((round_pass / total_pass) * 100, 1)}
        else:
            test_round_pass_rate[round_name] = {'total': round_total, 'pass': round_pass, 'rate': 0}

    blocker_tasks = [t for t in tasks if t.blockers and t.blockers.strip()]
    rejected_tasks = [t for t in tasks if t.status == '送测打回']
    pass_tasks = [t for t in tasks if t.test_result == 'PASS']
    pass_count = len(pass_tasks)

    if total_tasks > 0:
        avg_progress = round(avg_progress / total_tasks, 1)

    months = []
    for m in range(1, 13):
        months.append({'num': m, 'name': datetime(year, m, 1).strftime('%Y年%m月'), 'selected': m == month})

    quarters = [
        {'num': 1, 'name': '第一季度', 'selected': quarter == 1},
        {'num': 2, 'name': '第二季度', 'selected': quarter == 2},
        {'num': 3, 'name': '第三季度', 'selected': quarter == 3},
        {'num': 4, 'name': '第四季度', 'selected': quarter == 4}
    ]

    years = []
    for y in range(2024, 2041):
        years.append({'num': y, 'selected': y == year})

    all_industries = Task.query.with_entities(Task.industry).distinct().filter(Task.industry.isnot(None)).all()
    industry_list = [i[0] for i in all_industries]

    return render_template('analysis.html',
                           tasks=tasks,
                           year=year,
                           month=month,
                           quarter=quarter,
                           period_type=period_type,
                           period_name=period_name,
                           industry_filter=industry_filter,
                           industry_list=industry_list,
                           status_counts=status_counts,
                           industry_counts=industry_counts,
                           test_result_counts=test_result_counts,
                           tester_counts=tester_counts,
                           test_round_pass_rate=test_round_pass_rate,
                           blocker_tasks=blocker_tasks,
                           rejected_tasks=rejected_tasks,
                           pass_tasks=pass_tasks,
                           pass_count=pass_count,
                           total_pass=total_pass,
                           total_tasks=total_tasks,
                           avg_progress=avg_progress,
                           blocker_count=blocker_count,
                           months=months,
                           quarters=quarters,
                           years=years)

@app.route('/tasks/export')
@login_required
def export_tasks():
    tasks = Task.query.all()
    
    output = StringIO()
    writer = csv.writer(output)
    
    writer.writerow(['标题', '描述', '状态', '优先级', '送测人', '测试人员', '行业', 'JIRA链接', '测试结果', '送测轮次', 'DI数值', '开始时间', '结束时间', '进度', '卡点问题', '创建时间'])
    
    for task in tasks:
        writer.writerow([
            task.title,
            task.description or '',
            task.status,
            task.priority,
            task.submitter or '',
            task.tester or '',
            task.industry or '',
            task.jira_link or '',
            task.test_result or '',
            task.test_round or '',
            task.di_value or '',
            task.start_date.strftime('%Y-%m-%d') if task.start_date else '',
            task.end_date.strftime('%Y-%m-%d') if task.end_date else '',
            task.progress,
            task.blockers or '',
            task.created_at.strftime('%Y-%m-%d %H:%M:%S')
        ])
    
    output.seek(0)
    response = make_response(output.getvalue().encode('utf-8'))
    
    filename = f'任务数据_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
    encoded_filename = quote(filename)
    response.headers['Content-Disposition'] = f'attachment; filename="{encoded_filename}"'
    response.headers['Content-Type'] = 'text/csv; charset=utf-8'
    
    return response

@app.route('/tasks/import', methods=['POST'])
@login_required
def import_tasks():
    if 'file' not in request.files:
        flash('请选择要导入的文件')
        return redirect(url_for('index'))
    
    file = request.files['file']
    
    if file.filename == '':
        flash('请选择要导入的文件')
        return redirect(url_for('index'))
    
    if file and file.filename.endswith('.csv'):
        try:
            stream = StringIO(file.stream.read().decode('utf-8-sig'))
            reader = csv.DictReader(stream)
            
            imported_count = 0
            for row in reader:
                try:
                    start_date = datetime.strptime(row['开始时间'], '%Y-%m-%d').date() if row.get('开始时间') else None
                    end_date = datetime.strptime(row['结束时间'], '%Y-%m-%d').date() if row.get('结束时间') else None
                    
                    def clean_text(text):
                        if text:
                            return text.replace('\n', ' ').replace('\r', ' ').replace('"', "'")
                        return text
                    
                    new_task = Task(
                        title=clean_text(row['标题']),
                        description=clean_text(row.get('描述')),
                        status=row.get('状态', '待处理'),
                        priority=row.get('优先级', '中等'),
                        submitter=clean_text(row.get('送测人')),
                        tester=clean_text(row.get('测试人员')),
                        industry=clean_text(row.get('行业')),
                        jira_link=clean_text(row.get('JIRA链接')),
                        test_result=clean_text(row.get('测试结果')),
                        test_round=clean_text(row.get('送测轮次')),
                        di_value=float(row.get('DI数值')) if row.get('DI数值') else None,
                        start_date=start_date,
                        end_date=end_date,
                        progress=int(row['进度']) if row.get('进度') else 0,
                        blockers=clean_text(row.get('卡点问题'))
                    )
                    db.session.add(new_task)
                    imported_count += 1
                except Exception as e:
                    flash(f'导入第{imported_count + 1}行时出错: {str(e)}')
            
            db.session.commit()
            flash(f'成功导入 {imported_count} 条任务数据')
        except Exception as e:
            flash(f'导入失败: {str(e)}')
    else:
        flash('只支持CSV格式文件')
    
    return redirect(url_for('index'))

@app.route('/analysis/export')
@login_required
def export_analysis():
    period_type = request.args.get('period_type', 'monthly')
    year = request.args.get('year', datetime.now().year)
    month = request.args.get('month', datetime.now().month)
    quarter = request.args.get('quarter', 1)
    industry_filter = request.args.get('industry_filter', 'all')

    try:
        year = int(year)
        month = int(month)
        quarter = int(quarter)
    except:
        year = datetime.now().year
        month = datetime.now().month
        quarter = 1

    if period_type == 'monthly':
        start_date = datetime(year, month, 1)
        if month == 12:
            end_date = datetime(year + 1, 1, 1)
        else:
            end_date = datetime(year, month + 1, 1)
        period_name = f"{year}年{month}月"
    elif period_type == 'quarterly':
        quarter_start_month = (quarter - 1) * 3 + 1
        start_date = datetime(year, quarter_start_month, 1)
        if quarter_start_month + 2 == 12:
            end_date = datetime(year + 1, 1, 1)
        else:
            end_date = datetime(year, quarter_start_month + 3, 1)
        period_name = f"{year}年第{quarter}季度"
    else:
        start_date = datetime(year, 1, 1)
        end_date = datetime(year + 1, 1, 1)
        period_name = f"{year}年度"

    start_date_only = start_date.date() if isinstance(start_date, datetime) else start_date
    end_date_only = end_date.date() if isinstance(end_date, datetime) else end_date
    
    query = Task.query.filter(
        Task.start_date >= start_date_only,
        Task.start_date < end_date_only
    )

    if industry_filter != 'all' and industry_filter:
        query = query.filter(Task.industry == industry_filter)

    tasks = query.all()

    status_counts = defaultdict(int)
    priority_counts = defaultdict(int)
    test_result_counts = defaultdict(int)
    total_tasks = len(tasks)
    pending_count = 0
    progress_count = 0
    completed_count = 0
    interrupted_count = 0
    rejected_count = 0
    avg_progress = 0
    blocker_count = 0

    test_round_pass_rate = {}
    blocker_tasks = []
    rejected_tasks = []
    pass_tasks = []
    industry_counts = defaultdict(int)
    tester_counts = defaultdict(int)

    for task in tasks:
        status_counts[task.status] += 1
        priority_counts[task.priority] += 1
        test_result_counts[task.test_result or 'N/A'] += 1
        avg_progress += task.progress
        if task.blockers and task.blockers.strip():
            blocker_count += 1
            blocker_tasks.append(task)
        if task.industry:
            industry_counts[task.industry] += 1
        if task.tester:
            tester_counts[task.tester] += 1
        if task.status == '待处理':
            pending_count += 1
        elif task.status == '进行中':
            progress_count += 1
        elif task.status == '已完成':
            completed_count += 1
        elif task.status == '异常中断':
            interrupted_count += 1
        elif task.status == '送测打回':
            rejected_count += 1
            rejected_tasks.append(task)
        if task.test_result == 'PASS':
            pass_tasks.append(task)
    
    pass_count = len(pass_tasks)

    round_pass_counts = {}
    for round_name in TEST_ROUND_OPTIONS:
        round_tasks = [t for t in tasks if t.test_round == round_name]
        round_pass = sum(1 for t in round_tasks if t.test_result == 'PASS')
        round_pass_counts[round_name] = round_pass
    
    total_pass = sum(round_pass_counts.values())
    
    for round_name in TEST_ROUND_OPTIONS:
        round_tasks = [t for t in tasks if t.test_round == round_name]
        round_total = len(round_tasks)
        round_pass = round_pass_counts[round_name]
        if total_pass > 0:
            test_round_pass_rate[round_name] = {'total': round_total, 'pass': round_pass, 'rate': round((round_pass / total_pass) * 100, 1)}
        else:
            test_round_pass_rate[round_name] = {'total': round_total, 'pass': round_pass, 'rate': 0}

    if total_tasks > 0:
        avg_progress = round(avg_progress / total_tasks, 1)

    years = []
    current_year = datetime.now().year
    for y in range(current_year - 5, current_year + 2):
        years.append({'num': y, 'selected': (y == year)})

    months = []
    month_names = ['1月', '2月', '3月', '4月', '5月', '6月', '7月', '8月', '9月', '10月', '11月', '12月']
    for m in range(1, 13):
        months.append({'num': m, 'name': month_names[m-1], 'selected': (m == month)})

    quarters = []
    quarter_names = ['第一季度', '第二季度', '第三季度', '第四季度']
    for q in range(1, 5):
        quarters.append({'num': q, 'name': quarter_names[q-1], 'selected': (q == quarter)})

    industry_list = Task.query.with_entities(Task.industry).distinct().all()
    industry_list = [i[0] for i in industry_list if i[0]]

    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    html_content = render_template('analysis_export.html',
                                   tasks=tasks,
                                   period_name=period_name,
                                   year=year,
                                   month=month,
                                   quarter=quarter,
                                   period_type=period_type,
                                   industry_filter=industry_filter,
                                   years=years,
                                   months=months,
                                   quarters=quarters,
                                   industry_list=industry_list,
                                   status_counts=status_counts,
                                   priority_counts=priority_counts,
                                   test_result_counts=test_result_counts,
                                   test_round_pass_rate=test_round_pass_rate,
                                   blocker_tasks=blocker_tasks,
                                   rejected_tasks=rejected_tasks,
                                   pass_tasks=pass_tasks,
                                   pass_count=pass_count,
                                   total_pass=total_pass,
                                   industry_counts=industry_counts,
                                   tester_counts=tester_counts,
                                   total_tasks=total_tasks,
                                   pending_count=pending_count,
                                   progress_count=progress_count,
                                   completed_count=completed_count,
                                   interrupted_count=interrupted_count,
                                   rejected_count=rejected_count,
                                   avg_progress=avg_progress,
                                   blocker_count=blocker_count,
                                   current_time=current_time)
    
    filename = f"report_{period_type}_{year}_{month if period_type == 'monthly' else quarter}.html"
    
    response = make_response(html_content)
    response.headers['Content-Type'] = 'text/html; charset=utf-8'
    response.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    return response

@app.route('/admin')
@admin_required
def admin_dashboard():
    pending_users = User.query.filter_by(is_active=False).all()
    active_users_list = User.query.filter_by(is_active=True).all()
    login_logs = LoginLog.query.order_by(LoginLog.login_time.desc()).limit(50).all()
    total_users = User.query.count()
    active_users = User.query.filter_by(is_active=True).count()
    
    return render_template('admin.html',
                           pending_users=pending_users,
                           active_users_list=active_users_list,
                           login_logs=login_logs,
                           total_users=total_users,
                           active_users=active_users)

@app.route('/admin/approve/<int:user_id>')
@admin_required
def approve_user(user_id):
    user = User.query.get_or_404(user_id)
    user.is_active = True
    db.session.commit()
    flash(f'已批准用户 {user.username}')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/reject/<int:user_id>')
@admin_required
def reject_user(user_id):
    user = User.query.get_or_404(user_id)
    db.session.delete(user)
    db.session.commit()
    flash(f'已拒绝用户 {user.username}')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/delete_user/<int:user_id>')
@admin_required
def delete_user(user_id):
    user = User.query.get_or_404(user_id)
    if user.role == 'admin':
        flash('不能删除管理员账号！')
        return redirect(url_for('admin_dashboard'))
    db.session.delete(user)
    db.session.commit()
    flash(f'已删除用户 {user.username}')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/set_role/<int:user_id>', methods=['GET', 'POST'])
@admin_required
def set_role(user_id):
    user = User.query.get_or_404(user_id)
    
    if request.method == 'POST':
        new_role = request.form['role']
        if new_role in ['admin', 'editor', 'viewer']:
            user.role = new_role
            user.can_access_performance = 'performance_access' in request.form
            db.session.commit()
            role_name = dict(ROLES).get(new_role, new_role)
            flash(f'已将用户 {user.username} 的权限设置为 {role_name}')
        else:
            flash('无效的权限设置！')
        return redirect(url_for('admin_dashboard'))
    
    return render_template('set_role.html', user=user, roles=ROLES)

@app.route('/change_password', methods=['GET', 'POST'])
@login_required
def change_password():
    user = User.query.get(session['user_id'])
    
    if request.method == 'POST':
        old_password = request.form['old_password']
        new_password = request.form['new_password']
        confirm_password = request.form['confirm_password']
        
        if user.password != old_password:
            flash('原密码不正确！')
            return redirect(url_for('change_password'))
        
        if new_password != confirm_password:
            flash('两次输入的新密码不一致！')
            return redirect(url_for('change_password'))
        
        if new_password == old_password:
            flash('新密码不能与原密码相同！')
            return redirect(url_for('change_password'))
        
        user.password = new_password
        db.session.commit()
        flash('密码修改成功！')
        return redirect(url_for('home'))
    
    return render_template('change_password.html')

@app.route('/task/<int:task_id>/notify', methods=['POST'])
@admin_required
def send_task_notification(task_id):
    task = Task.query.get_or_404(task_id)
    success = send_feishu_notification(task)
    if success:
        return jsonify({'success': True, 'message': '提醒已发送到飞书群'})
    else:
        return jsonify({'success': False, 'message': '发送失败，请稍后重试'})

@app.route('/analysis/send_report', methods=['POST'])
@login_required
def send_report_to_feishu():
    period_type = request.args.get('period_type', 'monthly')
    year = request.args.get('year', datetime.now().year)
    month = request.args.get('month', datetime.now().month)
    quarter = request.args.get('quarter', 1)
    industry_filter = request.args.get('industry_filter', 'all')

    try:
        year = int(year)
        month = int(month)
        quarter = int(quarter)
    except:
        year = datetime.now().year
        month = datetime.now().month
        quarter = 1

    print(f"收到发送报告请求: period_type={period_type}, year={year}, month={month}, quarter={quarter}, industry_filter={industry_filter}")

    if period_type == 'monthly':
        start_date = datetime(year, month, 1)
        if month == 12:
            end_date = datetime(year + 1, 1, 1)
        else:
            end_date = datetime(year, month + 1, 1)
        period_name = f"{year}年{month}月"
    elif period_type == 'quarterly':
        quarter_start_month = (quarter - 1) * 3 + 1
        start_date = datetime(year, quarter_start_month, 1)
        if quarter_start_month + 3 > 12:
            end_date = datetime(year + 1, quarter_start_month + 3 - 12, 1)
        else:
            end_date = datetime(year, quarter_start_month + 3, 1)
        period_name = f"{year}年第{quarter}季度"
        print(f"季度计算: quarter={quarter}, quarter_start_month={quarter_start_month}, start_date={start_date}, end_date={end_date}, period_name={period_name}")
    else:
        start_date = datetime(year, 1, 1)
        end_date = datetime(year + 1, 1, 1)
        period_name = f"{year}年度"

    start_date_only = start_date.date() if isinstance(start_date, datetime) else start_date
    end_date_only = end_date.date() if isinstance(end_date, datetime) else end_date
    
    query = Task.query.filter(
        Task.start_date >= start_date_only,
        Task.start_date < end_date_only
    )

    if industry_filter != 'all' and industry_filter:
        query = query.filter(Task.industry == industry_filter)

    tasks = query.all()

    status_counts = defaultdict(int)
    test_result_counts = defaultdict(int)
    total_tasks = len(tasks)
    avg_progress = 0
    blocker_count = 0
    test_round_pass_rate = {}
    industry_counts = defaultdict(int)
    tester_counts = defaultdict(int)

    for task in tasks:
        status_counts[task.status] += 1
        test_result_counts[task.test_result] += 1
        avg_progress += task.progress
        if task.blockers and task.blockers.strip():
            blocker_count += 1
        if task.industry:
            industry_counts[task.industry] += 1
        if task.tester:
            tester_counts[task.tester] += 1

    round_pass_counts = {}
    for round_name in TEST_ROUND_OPTIONS:
        round_tasks = [t for t in tasks if t.test_round == round_name]
        round_pass = sum(1 for t in round_tasks if t.test_result == 'PASS')
        round_pass_counts[round_name] = round_pass
    
    total_pass = sum(round_pass_counts.values())
    
    for round_name in TEST_ROUND_OPTIONS:
        round_tasks = [t for t in tasks if t.test_round == round_name]
        round_total = len(round_tasks)
        round_pass = round_pass_counts[round_name]
        if total_pass > 0:
            test_round_pass_rate[round_name] = {'total': round_total, 'pass': round_pass, 'rate': round((round_pass / total_pass) * 100, 1)}
        else:
            test_round_pass_rate[round_name] = {'total': round_total, 'pass': round_pass, 'rate': 0}

    if total_tasks > 0:
        avg_progress = round(avg_progress / total_tasks, 1)

    blocker_tasks = [t for t in tasks if t.blockers and t.blockers.strip()]
    rejected_tasks = [t for t in tasks if t.status == '送测打回']
    pass_tasks = [t for t in tasks if t.test_result == 'PASS']
    pass_count = len(pass_tasks)

    html_content = render_template('analysis_export.html',
                                   period_name=period_name,
                                   tasks=tasks,
                                   total_tasks=total_tasks,
                                   status_counts=status_counts,
                                   test_result_counts=test_result_counts,
                                   avg_progress=avg_progress,
                                   blocker_count=blocker_count,
                                   rejected_count=status_counts.get('送测打回', 0),
                                   pass_count=sum(1 for t in tasks if t.test_result == 'PASS'),
                                   fail_count=sum(1 for t in tasks if t.test_result == 'FAIL'),
                                   na_count=sum(1 for t in tasks if t.test_result == 'N/A'),
                                   total_pass=total_pass,
                                   test_round_pass_rate=test_round_pass_rate,
                                   blocker_tasks=blocker_tasks,
                                   rejected_tasks=rejected_tasks,
                                   industry_counts=industry_counts,
                                   tester_counts=tester_counts,
                                   year=year,
                                   month=month,
                                   quarter=quarter,
                                   period_type=period_type)

    success = send_feishu_report_with_html(period_name, total_tasks, status_counts, avg_progress, blocker_count, pass_count, test_round_pass_rate, html_content)
    
    if success:
        return jsonify({'success': True, 'message': '报告已发送到飞书群'})
    else:
        return jsonify({'success': False, 'message': '发送失败，请稍后重试'})

@app.route('/admin/reset_password/<int:user_id>', methods=['GET', 'POST'])
@admin_required
def reset_password(user_id):
    user = User.query.get_or_404(user_id)
    
    if request.method == 'POST':
        new_password = request.form['new_password']
        confirm_password = request.form['confirm_password']
        
        if new_password != confirm_password:
            flash('两次输入的密码不一致！')
            return redirect(url_for('reset_password', user_id=user_id))
        
        user.password = new_password
        db.session.commit()
        flash(f'已重置用户 {user.username} 的密码')
        return redirect(url_for('admin_dashboard'))
    
    return render_template('reset_password.html', user=user)

@app.route('/balongma')
@login_required
def balongma():
    machines = Machine.query.all()
    return render_template('balongma.html', machines=machines)

@app.route('/balongma/add', methods=['POST'])
@login_required
def add_machine():
    data = request.get_json()
    machine = Machine(
        name=data['name'],
        os_type=data['osType'],
        ip_address=data['ip'],
        port=int(data['port']),
        cpu=data.get('cpu'),
        memory=data.get('memory'),
        username=data.get('username'),
        password=data.get('password'),
        status='offline'
    )
    db.session.add(machine)
    db.session.commit()
    return jsonify({'success': True, 'machine': {
        'id': machine.id,
        'name': machine.name,
        'os_type': machine.os_type,
        'ip_address': machine.ip_address,
        'port': machine.port,
        'cpu': machine.cpu,
        'memory': machine.memory,
        'status': machine.status
    }})

@app.route('/balongma/check_status/<int:machine_id>')
@login_required
def check_machine_status(machine_id):
    machine = Machine.query.get_or_404(machine_id)
    return jsonify({'status': machine.status})

@app.route('/balongma/terminal/<int:machine_id>', methods=['POST'])
@login_required
def execute_command(machine_id):
    machine = Machine.query.get_or_404(machine_id)
    command = request.json.get('command', '')
    
    try:
        if machine.os_type == 'linux':
            import paramiko
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(
                machine.ip_address,
                port=machine.port,
                username=machine.username,
                password=machine.password,
                timeout=5
            )
            stdin, stdout, stderr = ssh.exec_command(command)
            output = stdout.read().decode('utf-8') + stderr.read().decode('utf-8')
            ssh.close()
            return jsonify({'output': output.strip()})
        else:
            import subprocess
            result = subprocess.run(
                ['powershell', '-Command', f'Invoke-Command -ComputerName {machine.ip_address} -ScriptBlock {{{command}}}', '-Credential', f'(New-Object System.Management.Automation.PSCredential("{machine.username}", (ConvertTo-SecureString "{machine.password}" -AsPlainText -Force)))'],
                capture_output=True,
                text=True,
                timeout=30
            )
            return jsonify({'output': result.stdout + result.stderr})
    except Exception as e:
        return jsonify({'output': f'执行失败: {str(e)}'})

@app.route('/balongma/delete/<int:machine_id>', methods=['DELETE'])
def delete_machine(machine_id):
    machine = Machine.query.get(machine_id)
    if machine:
        db.session.delete(machine)
        db.session.commit()
        return jsonify({'success': True})
    return jsonify({'success': False}, 404)

@app.route('/balongma/machine/<int:machine_id>')
def get_machine(machine_id):
    machine = Machine.query.get(machine_id)
    if machine:
        return jsonify({
            'id': machine.id,
            'name': machine.name,
            'os_type': machine.os_type,
            'ip_address': machine.ip_address,
            'port': machine.port,
            'username': machine.username,
            'cpu': machine.cpu,
            'memory': machine.memory
        })
    return jsonify({'error': '机器不存在'}, 404)

@app.route('/balongma/update/<int:machine_id>', methods=['PUT'])
def update_machine(machine_id):
    machine = Machine.query.get(machine_id)
    if machine:
        data = request.get_json()
        if 'name' in data:
            machine.name = data['name']
        if 'os_type' in data:
            machine.os_type = data['os_type']
        if 'ip_address' in data:
            machine.ip_address = data['ip_address']
        if 'port' in data:
            machine.port = int(data['port']) if data['port'] else 22
        if 'username' in data:
            machine.username = data['username']
        if 'cpu' in data:
            machine.cpu = data['cpu']
        if 'memory' in data:
            machine.memory = data['memory']
        db.session.commit()
        return jsonify({'success': True})
    return jsonify({'success': False}, 404)

@app.route('/balongma/machines')
def get_machines():
    machines = Machine.query.all()
    machines_list = []
    for m in machines:
        machines_list.append({
            'id': m.id,
            'name': m.name,
            'os_type': m.os_type,
            'ip_address': m.ip_address,
            'port': m.port,
            'username': m.username,
            'cpu': m.cpu,
            'memory': m.memory,
            'status': m.status
        })
    return jsonify({'machines': machines_list})

screen_resolutions = {}
last_heartbeat = {}
image_qualities = {}
dpi_scales = {}
resolution_scales = {}

@app.route('/balongma/register', methods=['POST'])
def register_machine():
    data = request.get_json()
    hostname = data.get('hostname', 'Unknown')
    os_type = data.get('os_type', 'windows')
    ip_address = data.get('ip_address', '')
    cpu_count = data.get('cpu_count', 0)
    screen_width = data.get('screen_width', 1920)
    screen_height = data.get('screen_height', 1080)
    dpi_scale = data.get('dpi_scale', 1.0)
    
    machine = Machine.query.filter_by(ip_address=ip_address).first()
    
    if machine:
        machine.status = 'online'
        machine.name = hostname
        machine.os_type = os_type
        machine.cpu = f"{cpu_count}核"
        db.session.commit()
        last_heartbeat[machine.id] = time.time()
        screen_resolutions[machine.id] = {'width': screen_width, 'height': screen_height, 'dpi_scale': dpi_scale}
        return jsonify({'success': True, 'machine_id': machine.id})
    
    machine = Machine(
        name=hostname,
        os_type=os_type,
        ip_address=ip_address,
        port=22,
        cpu=f"{cpu_count}核",
        status='online'
    )
    db.session.add(machine)
    db.session.commit()
    last_heartbeat[machine.id] = time.time()
    return jsonify({'success': True, 'machine_id': machine.id})

@app.route('/balongma/heartbeat/<int:machine_id>', methods=['POST'])
def heartbeat(machine_id):
    machine = Machine.query.get(machine_id)
    if machine:
        machine.status = 'online'
        db.session.commit()
        last_heartbeat[machine_id] = time.time()
        return jsonify({'success': True})
    return jsonify({'success': False}, 404)

@app.route('/balongma/check_status/<int:machine_id>')
def check_status(machine_id):
    machine = Machine.query.get(machine_id)
    if machine:
        if machine.status == 'online':
            return jsonify({'status': 'online'})
        return jsonify({'status': machine.status})
    return jsonify({'status': 'offline'})

@app.route('/balongma/refresh_status/<int:machine_id>')
def refresh_status(machine_id):
    machine = Machine.query.get(machine_id)
    if machine:
        if machine_id in last_heartbeat:
            elapsed = time.time() - last_heartbeat[machine_id]
            if elapsed < 30:
                machine.status = 'online'
                db.session.commit()
                return jsonify({'status': 'online', 'elapsed': int(elapsed)})
            else:
                del last_heartbeat[machine_id]
                machine.status = 'offline'
                db.session.commit()
                return jsonify({'status': 'offline', 'elapsed': int(elapsed)})
        else:
            machine.status = 'offline'
            db.session.commit()
            return jsonify({'status': 'offline', 'elapsed': -1})
    return jsonify({'status': 'offline'})

@app.route('/balongma/force_offline/<int:machine_id>', methods=['POST'])
def force_offline(machine_id):
    machine = Machine.query.get(machine_id)
    if machine:
        machine.status = 'offline'
        if machine_id in last_heartbeat:
            del last_heartbeat[machine_id]
        db.session.commit()
        return jsonify({'success': True})
    return jsonify({'success': False})

@app.route('/balongma/download')
@login_required
def download_page():
    return render_template('download_client.html')

@app.route('/balongma/download_client')
def download_client():
    platform = request.args.get('platform', 'windows')
    
    server_ip = request.host.split(':')[0]
    server_port = request.host.split(':')[1] if ':' in request.host else '5000'
    server_url = f"http://{server_ip}:{server_port}"
    
    base_dir = os.path.dirname(os.path.abspath(__file__))
    
    if platform == 'windows':
        client_path = os.path.normpath(os.path.join(base_dir, 'dist', 'balongma_agent.exe'))
        filename = 'balongma_agent.exe'
    elif platform == 'linux':
        client_path = os.path.normpath(os.path.join(base_dir, 'client_agent.sh'))
        filename = 'balongma_agent.sh'
    else:
        client_path = os.path.normpath(os.path.join(base_dir, 'client_agent.py'))
        filename = 'balongma_agent.py'
    
    if os.path.exists(client_path):
        if platform == 'windows':
            with open(client_path, 'rb') as f:
                content = f.read()
            response = make_response(content)
            response.headers['Content-Type'] = 'application/octet-stream'
        else:
            with open(client_path, 'r', encoding='utf-8-sig') as f:
                content = f.read()
            
            content = content.replace('http://192.168.31.182:5000', server_url)
            content = content.replace('set SERVER=http://192.168.31.182:5000', f'set SERVER={server_url}')
            content = content.replace('$serverUrl = "http://192.168.31.182:5000"', f'$serverUrl = "{server_url}"')
            content = content.replace('serverUrl = "http://192.168.31.182:5000"', 'serverUrl = "' + server_url + '"')
            
            response = make_response(content.encode('utf-8'))
            response.headers['Content-Type'] = 'text/plain; charset=utf-8'
        
        response.headers['Content-Disposition'] = f'attachment; filename={filename}'
        return response
    else:
        return f"File not found: {client_path}", 404

screenshots = {}
viewing_desktop = set()

@app.route('/balongma/need_screenshot/<int:machine_id>')
def need_screenshot(machine_id):
    return jsonify({'need': machine_id in viewing_desktop})

@app.route('/balongma/start_viewing/<int:machine_id>')
def start_viewing(machine_id):
    viewing_desktop.add(machine_id)
    return jsonify({'success': True})

@app.route('/balongma/stop_viewing/<int:machine_id>')
def stop_viewing(machine_id):
    viewing_desktop.discard(machine_id)
    return jsonify({'success': True})

@app.route('/balongma/screenshot/<int:machine_id>', methods=['POST'])
def receive_screenshot(machine_id):
    try:
        data = request.get_data(as_text=True)
        screenshots[machine_id] = data
        last_heartbeat[machine_id] = time.time()
        machine = Machine.query.get(machine_id)
        if machine:
            machine.status = 'online'
            db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/balongma/get_screenshot/<int:machine_id>')
def get_screenshot(machine_id):
    if machine_id in screenshots:
        return jsonify({'image': screenshots[machine_id]})
    return jsonify({'image': None})

control_commands = {}

@app.route('/balongma/control/<int:machine_id>', methods=['POST'])
def send_control(machine_id):
    try:
        data = request.get_json()
        control_commands[machine_id] = data
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/balongma/get_command/<int:machine_id>')
def get_command(machine_id):
    if machine_id in control_commands:
        cmd = control_commands[machine_id]
        del control_commands[machine_id]
        return jsonify(cmd)
    return jsonify({'type': None})

@app.route('/balongma/screen_resolution/<int:machine_id>')
def get_screen_resolution(machine_id):
    if machine_id in screen_resolutions:
        return jsonify(screen_resolutions[machine_id])
    return jsonify({'width': 1920, 'height': 1080, 'dpi_scale': 1.0})

@app.route('/balongma/set_quality/<int:machine_id>', methods=['POST'])
def set_image_quality(machine_id):
    data = request.get_json()
    quality = data.get('quality', 60)
    image_qualities[machine_id] = quality
    return jsonify({'status': 'success', 'quality': quality})

@app.route('/balongma/get_quality/<int:machine_id>')
def get_image_quality(machine_id):
    quality = image_qualities.get(machine_id, 60)
    return jsonify({'quality': quality})

@app.route('/balongma/set_dpi/<int:machine_id>', methods=['POST'])
def set_dpi_scale(machine_id):
    data = request.get_json()
    dpi = data.get('dpi', 1.0)
    dpi_scales[machine_id] = dpi
    return jsonify({'status': 'success', 'dpi': dpi})

@app.route('/balongma/get_dpi/<int:machine_id>')
def get_dpi_scale(machine_id):
    dpi = dpi_scales.get(machine_id, 1.0)
    return jsonify({'dpi': dpi})

@app.route('/balongma/set_resolution/<int:machine_id>', methods=['POST'])
def set_resolution_scale(machine_id):
    data = request.get_json()
    scale = data.get('scale', 0.5)
    resolution_scales[machine_id] = scale
    return jsonify({'status': 'success', 'scale': scale})

@app.route('/balongma/get_resolution/<int:machine_id>')
def get_resolution_scale(machine_id):
    scale = resolution_scales.get(machine_id, 0.5)
    return jsonify({'scale': scale})

import socket

ssh_tunnels = {}

def find_free_port():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(('localhost', 0))
    port = sock.getsockname()[1]
    sock.close()
    return port

from flask_sock import Sock
import threading

sock = Sock(app)

@sock.route('/echo')
def echo(ws):
    while True:
        data = ws.receive()
        if not data:
            break
        ws.send(data)

if __name__ == '__main__':
    offline_check_thread = threading.Thread(target=check_offline_machines, daemon=True)
    offline_check_thread.start()
    print("离线检测线程已启动")
    
    app.run(debug=False, host='0.0.0.0', port=5000, threaded=True)