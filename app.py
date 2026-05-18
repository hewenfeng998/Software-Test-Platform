from flask import Flask, render_template, request, redirect, url_for, flash, session, make_response, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from collections import defaultdict
from functools import wraps
import csv
from io import StringIO
from urllib.parse import quote
import requests
import json

FEISHU_WEBHOOK_URL = 'https://open.feishu.cn/open-apis/bot/v2/hook/deea26d5-c11e-4c21-88d1-2f25d29b1d88'

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
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<User {self.username}>'
    
    def is_admin(self):
        return self.role == 'admin'
    
    def can_edit(self):
        return self.role in ['admin', 'editor']
    
    def can_delete(self):
        return self.role == 'admin'
    
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

@app.route('/')
@login_required
def home():
    user = User.query.get(session['user_id'])
    hostname = socket.gethostname()
    local_ip = get_local_ip()
    return render_template('home.html', is_admin=user.is_admin(), role=user.role, hostname=hostname, local_ip=local_ip)

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

    if tester_filter and tester_filter != 'all':
        tasks = tasks.filter(Task.tester == tester_filter)

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

    if status_filter and status_filter != 'all':
        tasks = tasks.filter(Task.status == status_filter)

    tasks = tasks.order_by(Task.created_at.desc()).paginate(page=page, per_page=per_page, error_out=False)
    
    testers = Task.query.with_entities(Task.tester).distinct().filter(Task.tester.isnot(None)).all()
    tester_list = [t[0] for t in testers]

    return render_template('index.html', tasks=tasks.items,
                           pagination=tasks,
                           start_filter=start_filter, end_filter=end_filter,
                           status_filter=status_filter,
                           search_keyword=search_keyword,
                           tester_filter=tester_filter,
                           is_admin=user.is_admin(),
                           tester_list=tester_list,
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
        return redirect(url_for('index'))

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
    return redirect(url_for('index'))

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

    tasks = Task.query.filter(
        Task.created_at >= start_date,
        Task.created_at < end_date
    )

    if industry_filter and industry_filter != 'all':
        tasks = tasks.filter(Task.industry == industry_filter)
    
    tasks = tasks.all()

    status_counts = defaultdict(int)
    industry_counts = defaultdict(int)
    test_result_counts = defaultdict(int)
    tester_counts = defaultdict(int)
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

    query = Task.query.filter(
        Task.created_at >= start_date,
        Task.created_at < end_date
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

    for task in tasks:
        status_counts[task.status] += 1
        priority_counts[task.priority] += 1
        test_result_counts[task.test_result or 'N/A'] += 1
        avg_progress += task.progress
        if task.blockers:
            blocker_count += 1
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

if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=5000, threaded=True)