import requests
import re
import ddddocr
from bs4 import BeautifulSoup
import json
import time
import random
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# --- 核心配置加载逻辑 ---
def load_config():
    """
    智能加载：优先扫描 ACCOUNT_1 到 ACCOUNT_10 变量。
    不再强制要求 APP_CONFIG_JSON 存在。
    """
    all_accounts = []
    
    # 1. 扫描 1-10 号账户变量
    for i in range(1, 11):
        acc_str = os.environ.get(f"ACCOUNT_{i}")
        if acc_str and acc_str.strip():
            try:
                acc_data = json.loads(acc_str)
                all_accounts.append(acc_data)
                print(f"::notice::[账号扫描] 成功识别变量 ACCOUNT_{i}")
            except Exception as e:
                print(f"::error::[账号扫描] ACCOUNT_{i} 格式错误 (需要JSON): {e}")

    # 2. 读取通知配置 (可选)
    notification = {"enabled": True, "type": "console"}
    app_config_str = os.environ.get("APP_CONFIG_JSON")
    if app_config_str:
        try:
            data = json.loads(app_config_str)
            if "notification" in data:
                notification = data["notification"]
            # 兼容旧格式的账号数据
            if "gamemale" in data:
                acc_part = data["gamemale"]
                if isinstance(acc_part, list): all_accounts.extend(acc_part)
                else: all_accounts.append(acc_part)
        except:
            print("::warning::APP_CONFIG_JSON 存在但解析失败，将使用默认控制台输出。")

    # 3. 终极检查
    if not all_accounts:
        print("::error::错误：未找到任何账号配置！")
        print("请检查 GitHub Secrets 中是否添加了 ACCOUNT_1 (内容为 JSON 格式)。")
        exit(1)

    return {"accounts": all_accounts, "notification": notification}

# --- 通知发送函数 ---
def send_notification(config, message):
    notif_cfg = config.get("notification", {})
    if not notif_cfg.get("enabled", False): return
    
    ntype = notif_cfg.get("type", "console")
    try:
        if ntype == "telegram":
            tg = notif_cfg.get("telegram", {})
            requests.post(f"https://api.telegram.org/bot{tg.get('bot_token')}/sendMessage", 
                          json={"chat_id": tg.get('chat_id'), "text": message}, timeout=10)
        elif ntype == "wechat":
            requests.post(notif_cfg.get("wechat", {}).get("webhook"), 
                          json={"msgtype": "text", "text": {"content": message}}, timeout=10)
        elif ntype == "email":
            mail = notif_cfg.get("email", {})
            msg = MIMEMultipart(); msg['Subject'] = "Gamemale 任务汇总"; msg.attach(MIMEText(message, 'plain', 'utf-8'))
            server = smtplib.SMTP(mail["smtp_server"], mail.get("smtp_port", 587)); server.starttls()
            server.login(mail["username"], mail["password"])
            server.sendmail(mail["from"], mail["to"], msg.as_string()); server.quit()
        else:
            print(f"\n--- 任务汇总报告 ---\n{message}")
    except Exception as e:
        print(f"通知发送失败: {e}")

# --- 互动逻辑 ---
def interact_with_blogs_regex(session, target=10):
    uids = set(); page = 1
    while len(uids) < target and page <= 5:
        try:
            res = session.get(f'https://www.gamemale.com/home.php?mod=space&do=blog&view=all&page={page}')
            links = re.findall(r'href="([^"]*blog-\d+-\d+\.html[^"]*)"', res.text)
            for link in links:
                if len(uids) >= target: break
                full_url = "https://www.gamemale.com/" + link.lstrip('/')
                uid_m = re.search(r'blog-(\d+)-', full_url)
                if not uid_m: continue
                uid = uid_m.group(1)
                blog_page = session.get(full_url).text
                btn = BeautifulSoup(blog_page, 'html.parser').select_one('a[id*="click_blogid_"][id$="_1"]')
                if btn:
                    c_url = "https://www.gamemale.com/" + btn.get('href').lstrip('/') + '&inajax=1'
                    if 'succeed' in session.get(c_url, headers={'X-Requested-With': 'XMLHttpRequest'}).text:
                        uids.add(uid)
                        time.sleep(random.uniform(2, 4))
        except: break
        page += 1
    return list(uids)

# --- 自动化类 ---
class GamemaleAutomation:
    def __init__(self, acc_cfg, global_cfg):
        self.acc = acc_cfg
        self.global_cfg = global_cfg
        self.session = requests.Session()
        self.formhash = None
        self.session.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'})

    def login(self):
        cookie = self.acc.get("cookie")
        if cookie:
            for item in cookie.split(';'):
                if '=' in item:
                    k, v = item.strip().split('=', 1)
                    self.session.cookies.set(k, v, domain='www.gamemale.com')
            res = self.session.get('https://www.gamemale.com/home.php?mod=spacecp')
            if 'formhash' in res.text:
                self.formhash = re.search(r'formhash" value="([a-f0-9]+)"', res.text).group(1)
                return True
        return False

    def run_tasks(self):
        msg = []
        # 签到
        res_s = self.session.get(f"https://www.gamemale.com/k_misign-sign.html?operation=qiandao&format=button&formhash={self.formhash}").text
        msg.append(f"✅ 签到: {'成功' if 'succeed' in res_s or '已签' in res_s else '失败'}")
        # 互动
        count = len(interact_with_blogs_regex(self.session, 10))
        msg.append(f"📊 震惊互动: 成功 {count} 次")
        return "\n".join(msg)

# --- 主入口 ---
def main():
    config = load_config()
    summary = []
    for idx, acc in enumerate(config["accounts"]):
        user = acc.get("username", f"账号_{idx+1}")
        client = GamemaleAutomation(acc, config)
        try:
            if client.login():
                report = client.run_tasks()
                summary.append(f"👤 {user}:\n{report}")
            else:
                summary.append(f"👤 {user}: ❌ 登录失败 (Cookie失效)")
        except Exception as e:
            summary.append(f"👤 {user}: 💥 运行异常")
        time.sleep(5)
    
    final_report = "Gamemale 每日自动任务汇总：\n\n" + "\n\n".join(summary)
    send_notification(config, final_report)

if __name__ == "__main__":
    main()
