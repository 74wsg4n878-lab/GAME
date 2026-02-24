import requests
import re
import ddddocr
from bs4 import BeautifulSoup
import json
import time
import random
import os

def load_config():
    all_accounts = []
    for i in range(1, 11):
        acc_str = os.environ.get(f"ACCOUNT_{i}")
        if acc_str and acc_str.strip():
            try:
                all_accounts.append(json.loads(acc_str))
            except:
                pass
    if not all_accounts:
        print("::error::未找到配置，请检查 Secrets 是否包含 ACCOUNT_1")
        exit(1)
    return all_accounts

class GamemaleAutomation:
    def __init__(self, acc):
        self.acc = acc
        self.username = acc.get("username")
        self.password = acc.get("password")
        self.session = requests.Session()
        self.formhash = None
        self.ocr = ddddocr.DdddOcr(show_ad=False)
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        })

    def login_by_cookie(self):
        """尝试用 Cookie 登录"""
        cookie = self.acc.get("cookie")
        if not cookie: return False
        for item in cookie.split(';'):
            if '=' in item:
                k, v = item.strip().split('=', 1)
                self.session.cookies.set(k, v, domain='www.gamemale.com')
        res = self.session.get('https://www.gamemale.com/home.php?mod=spacecp')
        if 'formhash' in res.text:
            self.formhash = re.search(r'formhash" value="([a-f0-9]+)"', res.text).group(1)
            return True
        return False

    def login_by_password(self):
        """尝试用账号密码登录 (识别验证码)"""
        try:
            # 1. 初始化登录页
            init_res = self.session.get('https://www.gamemale.com/member.php?mod=logging&action=login&infloat=yes&inajax=1')
            login_hash = re.search(r'loginform_(\w+)', init_res.text).group(1)
            
            # 2. 验证码识别
            seccode_res = self.session.get(f'https://www.gamemale.com/misc.php?mod=seccode&action=update&idhash={login_hash}&{random.random()}')
            code_url_match = re.search(r'src="([^"]+seccode[^"]+)"', seccode_res.text)
            seccode_text = ""
            if code_url_match:
                img_res = self.session.get('https://www.gamemale.com/' + code_url_match.group(1))
                seccode_text = self.ocr.classification(img_res.content)
            
            # 3. 提交
            post_data = {
                'formhash': re.search(r'formhash" value="([a-f0-9]+)"', init_res.text).group(1),
                'username': self.username,
                'password': self.password,
                'questionid': self.acc.get("questionid", "0"),
                'answer': self.acc.get("answer", ""),
                'seccodeverify': seccode_text
            }
            post_url = f'https://www.gamemale.com/member.php?mod=logging&action=login&loginsubmit=yes&loginhash={login_hash}&inajax=1'
            login_res = self.session.post(post_url, data=post_data)
            
            if '欢迎您回来' in login_res.text:
                space_res = self.session.get('https://www.gamemale.com/home.php?mod=spacecp')
                self.formhash = re.search(r'formhash" value="([a-f0-9]+)"', space_res.text).group(1)
                return True
        except:
            pass
        return False

    def run(self):
        print(f"正在处理: {self.username}")
        # 策略：优先密码登录，失败则用 Cookie
        if self.login_by_password():
            print("🔑 账号密码登录成功")
        elif self.login_by_cookie():
            print("🍪 Cookie 登录成功")
        else:
            print("❌ 登录失败，请检查账号密码或 Cookie")
            return

        # 签到
        self.session.get(f"https://www.gamemale.com/k_misign-sign.html?operation=qiandao&format=button&formhash={self.formhash}")
        # 抽奖
        self.session.get(f"https://www.gamemale.com/plugin.php?id=it618_award:ajax&ac=getaward&formhash={self.formhash}")
        print(f"✨ {self.username} 任务执行完毕")

def main():
    accounts = load_config()
    for acc in accounts:
        GamemaleAutomation(acc).run()
        time.sleep(10)

if __name__ == "__main__":
    main()
