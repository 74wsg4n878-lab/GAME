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

# --- [配置加载] 扫描 ACCOUNT_1 到 ACCOUNT_10 ---
def load_all_configs():
    all_configs = []
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
                conf = global_config.copy()
                if "gamemale" in acc_data:
                    conf["gamemale"] = acc_data["gamemale"]
                else:
                    conf["gamemale"] = acc_data
                all_configs.append(conf)
            except Exception as e:
                print(f"::error::ACCOUNT_{i} 解析失败: {e}")
    
    if not all_configs and global_config.get("gamemale"):
        all_configs.append(global_config)
    
    if not all_configs:
        print("::error::未找到配置，请设置 ACCOUNT_1 等环境变量。")
        exit(1)
    return all_configs

# --- [通知系统] ---
def send_notification(config, message):
    notif = config.get("notification", {})
    if not notif.get("enabled", False):
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
    except Exception as e:
        print(f"通知失败: {e}")

# --- [自动化类] ---
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
        # 优先使用 Cookie
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

        # 密码登录 + 验证码
        print(f"🔄 [{self.username}] 尝试密码登录...")
        try:
            popup = self.session.get('https://www.gamemale.com/member.php?mod=logging&action=login&infloat=yes&handlekey=login&inajax=1').text
            loginhash = re.search(r'loginhash=(\w+)', popup).group(1)
            f_hash = re.search(r'formhash" value="([a-f0-9]+)"', popup).group(1)
            
            js_res = self.session.get(f'https://www.gamemale.com/misc.php?mod=seccode&action=update&idhash={loginhash}&inajax=1').text
            img_path = re.search(r'src="([^"]+mod=seccode[^"]+)"', js_res).group(1).replace('&amp;', '&')
            code = self.ocr.classification(self.session.get('https://www.gamemale.com/' + img_path).content)
            
            data = {
                'formhash': f_hash, 'username': self.username, 'password': self.acc.get("password"),
                'questionid': self.acc.get("questionid", "0"), 'answer': self.acc.get("answer", ""),
                'seccodeverify': code, 'loginfield': 'username', 'referer': 'https://www.gamemale.com/forum.php'
            }
            l_res = self.session.post(f'https://www.gamemale.com/member.php?mod=logging&action=login&loginsubmit=yes&loginhash={loginhash}&inajax=1', data=data).text
            if '欢迎您回来' in l_res or 'succeed' in l_res:
                self.formhash = re.search(r'formhash" value="([a-f0-9]+)"', self.session.get('https://www.gamemale.com/home.php?mod=spacecp').text).group(1)
                print(f"✅ [{self.username}] 密码登录成功")
                return True
        except Exception as e:
            print(f"❌ 登录出错: {e}")
        return False

    def do_interact(self, target_count=10):
        """核心震惊逻辑：还原你原本的 BeautifulSoup 解析方式"""
        print(f"🔄 [{self.username}] 开始日志互动...")
        successful_uids = []
        try:
            res = self.session.get('https://www.gamemale.com/home.php?mod=space&do=blog&view=all')
            blog_urls = re.findall(r'href="(blog-\d+-\d+\.html)"', res.text)
            
            for b_url in list(dict.fromkeys(blog_urls))[:20]: # 去重并取前20
                if len(successful_uids) >= target_count: break
                
                full_url = "https://www.gamemale.com/" + b_url
                uid = re.search(r'blog-(\d+)-', b_url).group(1)
                page_text = self.session.get(full_url).text
                
                # 寻找震惊按钮 (click_blogid_xxx_1)
                soup = BeautifulSoup(page_text, 'html.parser')
                shock_button = soup.select_one('a[id*="click_blogid_"][id$="_1"]')
                
                if shock_button:
                    click_url = shock_button.get('href').replace('&amp;', '&')
                    if 'inajax=1' not in click_url: click_url += '&inajax=1'
                    click_url = "https://www.gamemale.com/" + click_url.lstrip('/')
                    
                    c_res = self.session.get(click_url, headers={'X-Requested-With': 'XMLHttpRequest', 'Referer': full_url}).text
                    if 'succeed' in c_res or '表态成功' in c_res:
                        successful_uids.append(uid)
                        print(f"  └ ✅ 震惊成功 (UID: {uid})")
                        time.sleep(random.uniform(2, 4))
            
            # 对成功震惊的前3人打招呼
            for t_uid in successful_uids[:3]:
                self.session.get(f"https://www.gamemale.com/home.php?mod=spacecp&ac=poke&op=send&uid={t_uid}")
                poke_data = {'formhash': self.formhash, 'pokeuid': t_uid, 'pokesubmit': 'true', 'iconid': '3'}
                self.session.post(f"https://www.gamemale.com/home.php?mod=spacecp&ac=poke&op=send&uid={t_uid}&inajax=1", data=poke_data)
        except: pass
        return len(successful_uids)

    def run(self):
        if not self.login(): return f"❌ [{self.username}] 登录失败"
        
        # 基础任务
        self.session.get(f'https://www.gamemale.com/k_misign-sign.html?operation=qiandao&format=button&formhash={self.formhash}')
        self.session.get(f'https://www.gamemale.com/plugin.php?id=it618_award:ajax&ac=getaward&formhash={self.formhash}')
        
        # 互动 & 兑换
        shock_num = self.do_interact(10)
        
        # 积分 & 血液兑换
        ex_msg = "SKIP"
        res_c = self.session.get('https://www.gamemale.com/home.php?mod=spacecp&ac=credit&op=base').text
        soup = BeautifulSoup(res_c, 'html.parser')
        credits = {li.get_text().split(':')[0].strip(): li.get_text().split(':')[1].strip() for li in soup.select('ul.creditl li')}
        
        blood = int(credits.get("血液", "0").split()[0])
        if blood > 34 and self.acc.get("auto_exchange_enabled", True):
            ex_res = self.session.post('https://www.gamemale.com/home.php?mod=spacecp&ac=credit&op=exchange&inajax=1', 
                                     data={'formhash': self.formhash, 'exchangeamount': '1', 'fromcredits': '3', 'tocredits': '1', 'exchangesubmit': 'true', 'password': self.acc.get("password")}).text
            ex_msg = "OK" if "成功" in ex_res else "FAIL"
            # 刷新积分
            res_c = self.session.get('https://www.gamemale.com/home.php?mod=spacecp&ac=credit&op=base').text
            soup = BeautifulSoup(res_c, 'html.parser')
            credits = {li.get_text().split(':')[0].strip(): li.get_text().split(':')[1].strip() for li in soup.select('ul.creditl li')}

        return f"👤 {self.username} | 震惊:{shock_num} | 兑换:{ex_msg} | 血液:{credits.get('血液','?')} | 旅程:{credits.get('旅程','?')}"

def main():
    configs = load_all_configs()
    report = "📋 Gamemale 任务报表\n"
    for c in configs:
        bot = GamemaleAutomation(c)
        report += bot.run() + "\n"
        time.sleep(5)
    print(report)
    send_notification(configs[0], report)

if __name__ == "__main__":
    main()
