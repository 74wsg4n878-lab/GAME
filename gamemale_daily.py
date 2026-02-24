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

# --- [配置加载] 支持 ACCOUNT_1 到 ACCOUNT_10 ---
def load_all_configs():
    all_configs = []
    # 尝试加载全局配置（用于获取通知设置）
    global_config = {}
    config_json_str = os.environ.get("APP_CONFIG_JSON")
    if config_json_str:
        try: global_config = json.loads(config_json_str)
        except: pass

    for i in range(1, 11):
        acc_str = os.environ.get(f"ACCOUNT_{i}")
        if acc_str and acc_str.strip():
            try:
                acc_data = json.loads(acc_str)
                # 兼容格式：如果 JSON 里没有 "gamemale" 键，则整段视为 gamemale 配置
                conf = global_config.copy()
                if "gamemale" in acc_data:
                    conf["gamemale"] = acc_data["gamemale"]
                else:
                    conf["gamemale"] = acc_data
                all_configs.append(conf)
                print(f"::notice::[配置] 成功加载 ACCOUNT_{i}")
            except Exception as e:
                print(f"::error::[配置] ACCOUNT_{i} 解析失败: {e}")
    
    if not all_configs and global_config.get("gamemale"):
        all_configs.append(global_config)
    
    if not all_configs:
        print("::error::未找到任何有效账号配置，请检查 Secrets。")
        exit(1)
    return all_configs

# --- [通知系统] ---
def send_notification(config, message):
    notif = config.get("notification", {})
    if not notif.get("enabled", False):
        print("::notice::通知未开启，仅控制台输出报表。")
        return

    n_type = notif.get("type", "console")
    try:
        if n_type == "telegram":
            tg = notif.get("telegram", {})
            requests.post(f"https://api.telegram.org/bot{tg.get('bot_token')}/sendMessage", 
                          json={"chat_id": tg.get("chat_id"), "text": message, "parse_mode": "HTML"}, timeout=10)
        elif n_type == "wechat":
            requests.post(notif.get("wechat", {}).get("webhook"), 
                          json={"msgtype": "text", "text": {"content": message}}, timeout=10)
        elif n_type == "email":
            em = notif.get("email", {})
            msg = MIMEMultipart()
            msg['Subject'] = "Gamemale 任务报告"
            msg.attach(MIMEText(message, 'plain', 'utf-8'))
            with smtplib.SMTP(em["smtp_server"], em.get("smtp_port", 587)) as s:
                s.starttls()
                s.login(em["username"], em["password"])
                s.sendmail(em["from"], em["to"], msg.as_string())
        print(f"✅ {n_type} 通知发送成功")
    except Exception as e:
        print(f"❌ 通知发送失败: {e}")

# --- [核心逻辑类] ---
class GamemaleAutomation:
    def __init__(self, config):
        self.config = config
        self.acc = config.get("gamemale", {})
        self.username = self.acc.get("username", "未知用户")
        self.session = requests.Session()
        self.formhash = None
        self.ocr = ddddocr.DdddOcr(show_ad=False)
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': 'https://www.gamemale.com/forum.php'
        })

    def login(self):
        # 1. 尝试 Cookie 登录
        cookie_str = self.acc.get("cookie")
        if cookie_str:
            for item in cookie_str.split(';'):
                if '=' in item:
                    k, v = item.strip().split('=', 1)
                    self.session.cookies.set(k, v, domain='www.gamemale.com')
            res = self.session.get('https://www.gamemale.com/home.php?mod=spacecp', timeout=20)
            if 'formhash' in res.text:
                self.formhash = re.search(r'formhash" value="([a-f0-9]+)"', res.text).group(1)
                print(f"✅ [{self.username}] Cookie 登录成功")
                return True

        # 2. 保底密码登录
        print(f"🔄 [{self.username}] 尝试密码登录...")
        try:
            # 获取登录参数
            popup = self.session.get('https://www.gamemale.com/member.php?mod=logging&action=login&infloat=yes&handlekey=login&inajax=1').text
            loginhash = re.search(r'loginform_(\w+)', popup).group(1)
            f_hash = re.search(r'formhash" value="([a-f0-9]+)"', popup).group(1)
            # 验证码识别
            sec_res = self.session.get(f'https://www.gamemale.com/misc.php?mod=seccode&action=update&idhash={loginhash}&{random.random()}').text
            img_url = 'https://www.gamemale.com/' + re.search(r'src="([^"]+seccode[^"]+)"', sec_res).group(1)
            code = self.ocr.classification(self.session.get(img_url).content)
            
            data = {
                'formhash': f_hash, 'username': self.username, 'password': self.acc.get("password"),
                'questionid': self.acc.get("questionid", "0"), 'answer': self.acc.get("answer", ""),
                'seccodeverify': code, 'referer': 'https://www.gamemale.com/forum.php'
            }
            l_res = self.session.post(f'https://www.gamemale.com/member.php?mod=logging&action=login&loginsubmit=yes&loginhash={loginhash}&inajax=1', data=data).text
            if '欢迎您回来' in l_res:
                self.formhash = re.search(r'formhash" value="([a-f0-9]+)"', self.session.get('https://www.gamemale.com/home.php?mod=spacecp').text).group(1)
                return True
        except: pass
        return False

    def interact_tasks(self):
        """震惊、访问空间、打招呼综合任务"""
        results = {"震惊": False, "访问": False, "招呼": False}
        try:
            res = self.session.get('https://www.gamemale.com/home.php?mod=space&do=blog&view=all', timeout=20)
            blogs = re.findall(r'blog-(\d+)-(\d+)\.html', res.text)
            
            poked_uids = []
            shock_count = 0
            for uid, bid in blogs[:10]:
                blog_url = f'https://www.gamemale.com/blog-{uid}-{bid}.html'
                blog_page = self.session.get(blog_url).text
                # 震惊互动
                shock_btn = re.search(r'id="click_blogid_' + bid + r'_1".*?href="([^"]+)"', blog_page)
                if shock_btn:
                    self.session.get('https://www.gamemale.com/' + shock_btn.group(1).replace('&amp;', '&') + '&inajax=1')
                    shock_count += 1
                if uid not in poked_uids: poked_uids.append(uid)
                time.sleep(1)
            
            results["震惊"] = shock_count > 0
            # 空间访问 & 打招呼 (取前3人)
            for target_uid in poked_uids[:3]:
                self.session.get(f'https://www.gamemale.com/space-uid-{target_uid}.html')
                poke_url = f'https://www.gamemale.com/home.php?mod=spacecp&ac=poke&op=send&uid={target_uid}'
                p_page = self.session.get(poke_url).text
                p_hash = re.search(r'formhash" value="([a-f0-9]+)"', p_page)
                if p_hash:
                    p_data = {'formhash': p_hash.group(1), 'referer': poke_url, 'pokeuid': target_uid, 'pokesubmit': 'true', 'iconid': '3'}
                    self.session.post(f"{poke_url}&inajax=1", data=p_data)
            results["访问"] = results["招呼"] = len(poked_uids) > 0
        except: pass
        return results

    def check_and_exchange(self):
        """血液兑换旅程"""
        try:
            res = self.session.get('https://www.gamemale.com/home.php?mod=spacecp&ac=credit&op=base').text
            soup = BeautifulSoup(res, 'html.parser')
            credits = {li.get_text().split(':')[0].strip(): li.get_text().split(':')[1].strip() for li in soup.select('ul.creditl li')}
            blood = int(credits.get("血液", "0").split()[0])
            
            if blood > 34 and self.acc.get("auto_exchange_enabled", True):
                data = {'formhash': self.formhash, 'exchangeamount': '1', 'fromcredits': '3', 'tocredits': '1', 'exchangesubmit': 'true', 'password': self.acc.get("password")}
                self.session.post('https://www.gamemale.com/home.php?mod=spacecp&ac=credit&op=exchange&inajax=1', data=data)
                return True, credits
            return False, credits
        except: return False, {}

    def run(self):
        if not self.login(): return f"❌ [{self.username}] 登录失败"
        
        # 签到 & 抽奖
        self.session.get(f'https://www.gamemale.com/k_misign-sign.html?operation=qiandao&format=button&formhash={self.formhash}')
        self.session.get(f'https://www.gamemale.com/plugin.php?id=it618_award:ajax&ac=getaward&formhash={self.formhash}')
        
        interact = self.interact_tasks()
        ex_ok, final_credits = self.check_and_exchange()
        
        # 生成报表
        report = f"👤 账号: {self.username}\n"
        report += f"💰 积分: {final_credits.get('血液','?')} | {final_credits.get('旅程','?')}\n"
        report += f"✅ 任务: 签到+抽奖 | 震惊:{'OK' if interact['震惊'] else 'SKIP'} | 兑换:{'OK' if ex_ok else 'SKIP'}\n"
        return report

# --- [执行入口] ---
def main():
    configs = load_all_configs()
    summary = "📊 Gamemale 多账号执行报告\n" + "="*25 + "\n"
    for conf in configs:
        bot = GamemaleAutomation(conf)
        res = bot.run()
        summary += res + "\n"
        time.sleep(random.uniform(10, 20))
    
    print(summary)
    send_notification(configs[0], summary)

if __name__ == "__main__":
    main()
