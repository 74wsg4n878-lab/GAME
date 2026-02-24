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

# --- 配置加载与通知函数 ---
def load_config():
    """
    支持多 Secret 模式：自动扫描 ACCOUNT_1 到 ACCOUNT_10
    同时兼容 APP_CONFIG_JSON 中的通知配置
    """
    all_accounts = []
    for i in range(1, 11):
        acc_json = os.environ.get(f"ACCOUNT_{i}")
        if acc_json:
            try:
                all_accounts.append(json.loads(acc_json))
                print(f"::notice::已加载账号变量: ACCOUNT_{i}")
            except:
                print(f"::error::ACCOUNT_{i} 格式错误，请检查是否为标准 JSON")

    # 获取通知配置
    notification = {"enabled": True, "type": "console"}
    full_config_str = os.environ.get("APP_CONFIG_JSON")
    if full_config_str:
        try:
            data = json.loads(full_config_str)
            notification = data.get("notification", notification)
        except:
            pass

    if not all_accounts:
        print("::error::未找到任何账号配置，请在 Secrets 中添加 ACCOUNT_1 等变量")
        exit(1)

    return {"accounts": all_accounts, "notification": notification}

def send_notification(config, message):
    """发送通知消息"""
    notification_config = config.get("notification", {})
    if not notification_config.get("enabled", False):
        return

    notification_type = notification_config.get("type", "console")
    try:
        if notification_type == "telegram":
            telegram_config = notification_config.get("telegram", {})
            requests.post(f"https://api.telegram.org/bot{telegram_config.get('bot_token')}/sendMessage", 
                          json={"chat_id": telegram_config.get("chat_id"), "text": message}, timeout=10)
        elif notification_type == "wechat":
            requests.post(notification_config.get("wechat", {}).get("webhook"), 
                          json={"msgtype": "text", "text": {"content": message}}, timeout=10)
        elif notification_type == "email":
            email_cfg = notification_config.get("email", {})
            msg = MIMEMultipart()
            msg['Subject'] = "Gamemale 多账号任务统计"
            msg.attach(MIMEText(message, 'plain', 'utf-8'))
            server = smtplib.SMTP(email_cfg["smtp_server"], email_cfg.get("smtp_port", 587))
            server.starttls()
            server.login(email_cfg["username"], email_cfg["password"])
            server.sendmail(email_cfg["from"], email_cfg["to"], msg.as_string())
            server.quit()
        else:
            print(message)
    except Exception as e:
        print(f"发送通知失败: {e}")

# --- 互动函数 ---
def interact_with_blogs_regex(session, target_interactions=10):
    successful_user_ids = set()
    processed_blog_urls = set()
    page_num = 1
    
    while len(successful_user_ids) < target_interactions and page_num <= 5:
        try:
            url = f'https://www.gamemale.com/home.php?mod=space&do=blog&view=all&page={page_num}'
            res = session.get(url)
            hrefs = re.findall(r'href="([^"]*blog-\d+-\d+\.html[^"]*)"', res.text)
            
            for href in hrefs:
                full_url = href if href.startswith('http') else "https://www.gamemale.com/" + href
                if full_url in processed_blog_urls: continue
                processed_blog_urls.add(full_url)
                
                uid_match = re.search(r'blog-(\d+)-', full_url)
                if not uid_match: continue
                uid = uid_match.group(1)
                
                page_text = session.get(full_url).text
                shock_button = BeautifulSoup(page_text, 'html.parser').select_one('a[id*="click_blogid_"][id$="_1"]')
                
                if shock_button:
                    click_url = "https://www.gamemale.com/" + shock_button.get('href').lstrip('/') + '&inajax=1'
                    click_res = session.get(click_url, headers={'X-Requested-With': 'XMLHttpRequest'})
                    if 'succeed' in click_res.text or '表态成功' in click_res.text:
                        successful_user_ids.add(uid)
                        time.sleep(random.uniform(2, 4))
                
                if len(successful_user_ids) >= target_interactions: break
        except:
            break
        page_num += 1
    return list(successful_user_ids)

# --- 自动化类 ---
class GamemaleAutomation:
    def __init__(self, config):
        self.config = config
        self.session = requests.Session()
        self.formhash = None
        self.is_logged_in = False
        self.ocr = ddddocr.DdddOcr(show_ad=False)
        self.session.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'})

    def login(self):
        acc = self.config.get("gamemale", {})
        # Cookie 登录
        if acc.get("cookie"):
            for c in acc["cookie"].split(';'):
                if '=' in c:
                    n, v = c.strip().split('=', 1)
                    self.session.cookies.set(n, v, domain='www.gamemale.com')
            res = self.session.get('https://www.gamemale.com/home.php?mod=spacecp')
            if 'formhash' in res.text:
                self.formhash = re.search(r'formhash" value="([a-f0-9]+)"', res.text).group(1)
                self.is_logged_in = True
                return True
        return False

    def execute_all_tasks(self):
        results = {}
        # 1. 签到
        sign_url = f"https://www.gamemale.com/k_misign-sign.html?operation=qiandao&format=button&formhash={self.formhash}"
        results["签到"] = "succeed" in self.session.get(sign_url).text or "已签" in self.session.get(sign_url).text
        
        # 2. 抽奖
        lottery_url = f"https://www.gamemale.com/plugin.php?id=it618_award:ajax&ac=getaward&formhash={self.formhash}"
        results["抽奖"] = "ok" in self.session.get(lottery_url).text or "今日已" in self.session.get(lottery_url).text
        
        # 3. 震惊互动
        uids = interact_with_blogs_regex(self.session, 10)
        results["震惊互动"] = f"成功 {len(uids)} 次"
        
        return "\n".join([f"  • {k}: {v}" for k, v in results.items()])

# --- 主逻辑 ---
def main():
    config_data = load_config()
    accounts = config_data["accounts"]
    reports = []
    
    for idx, acc in enumerate(accounts):
        name = acc.get("username", f"账号_{idx+1}")
        client = GamemaleAutomation({"gamemale": acc, "notification": config_data["notification"]})
        try:
            if client.login():
                report = client.execute_all_tasks()
                reports.append(f"👤 {name}:\n{report}")
            else:
                reports.append(f"👤 {name}: ❌ 登录失败")
        except Exception as e:
            reports.append(f"👤 {name}: 💥 运行错误: {e}")
        time.sleep(10)

    final_msg = "📊 Gamemale 任务汇总报告：\n\n" + "\n\n".join(reports)
    print(final_msg)
    send_notification(config_data, final_msg)

if __name__ == "__main__":
    main()
