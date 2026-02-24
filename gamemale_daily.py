import requests
import re
import ddddocr
import json
import time
import random
import os

def load_config():
    """扫描 GitHub Secrets 中的 ACCOUNT_1 到 ACCOUNT_10"""
    all_accounts = []
    for i in range(1, 11):
        acc_str = os.environ.get(f"ACCOUNT_{i}")
        if acc_str and acc_str.strip():
            try:
                all_accounts.append(json.loads(acc_str))
                print(f"::notice::[配置] 成功加载 ACCOUNT_{i}")
            except:
                print(f"::error::[配置] ACCOUNT_{i} 格式错误")
    if not all_accounts:
        print("::error::未找到配置，请检查 Secrets 是否包含 ACCOUNT_1")
        exit(1)
    return all_accounts

class GamemaleAutomation:
    def __init__(self, acc):
        self.acc = acc
        self.username = acc.get("username", "未知用户")
        self.password = acc.get("password")
        self.session = requests.Session()
        self.formhash = None
        self.ocr = ddddocr.DdddOcr(show_ad=False)
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': 'https://www.gamemale.com/forum.php'
        })

    def login_by_cookie(self):
        """【优先级 1】尝试 Cookie 登录"""
        cookie = self.acc.get("cookie")
        if not cookie: return False
        try:
            # 这里的 Cookie 处理支持多种格式
            for item in cookie.split(';'):
                if '=' in item:
                    k, v = item.strip().split('=', 1)
                    self.session.cookies.set(k, v, domain='www.gamemale.com')
            
            # 访问个人设置页验证 Cookie 是否有效
            res = self.session.get('https://www.gamemale.com/home.php?mod=spacecp', timeout=20)
            if 'formhash' in res.text:
                self.formhash = re.search(r'formhash" value="([a-f0-9]+)"', res.text).group(1)
                return True
        except:
            pass
        return False

    def login_by_password(self):
        """【优先级 2】Cookie 失效时尝试账号密码登录"""
        if not self.username or not self.password: return False
        try:
            print(f"🔄 [{self.username}] Cookie 已失效，正在尝试账号密码登录...")
            # 1. 获取登录 loginhash
            init_res = self.session.get('https://www.gamemale.com/member.php?mod=logging&action=login&infloat=yes&inajax=1', timeout=20)
            login_hash = re.search(r'loginform_(\w+)', init_res.text).group(1)
            init_formhash = re.search(r'formhash" value="([a-f0-9]+)"', init_res.text).group(1)
            
            # 2. 识别验证码
            sec_url = f'https://www.gamemale.com/misc.php?mod=seccode&action=update&idhash={login_hash}&{random.random()}'
            sec_res = self.session.get(sec_url, timeout=20)
            code_url_match = re.search(r'src="([^"]+seccode[^"]+)"', sec_res.text)
            
            seccode_text = ""
            if code_url_match:
                img_res = self.session.get('https://www.gamemale.com/' + code_url_match.group(1), timeout=20)
                seccode_text = self.ocr.classification(img_res.content)
            
            # 3. 提交登录
            post_data = {
                'formhash': init_formhash,
                'username': self.username,
                'password': self.password,
                'questionid': self.acc.get("questionid", "0"),
                'answer': self.acc.get("answer", ""),
                'seccodeverify': seccode_text
            }
            post_url = f'https://www.gamemale.com/member.php?mod=logging&action=login&loginsubmit=yes&loginhash={login_hash}&inajax=1'
            login_res = self.session.post(post_url, data=post_data, timeout=20)
            
            if '欢迎您回来' in login_res.text:
                space_res = self.session.get('https://www.gamemale.com/home.php?mod=spacecp', timeout=20)
                self.formhash = re.search(r'formhash" value="([a-f0-9]+)"', space_res.text).group(1)
                return True
        except Exception as e:
            print(f"⚠️ [{self.username}] 账号登录异常: {e}")
        return False

    def run(self):
        print(f"\n▶️ 正在处理账号: {self.username}")
        # 执行优先级策略
        if self.login_by_cookie():
            print(f"🍪 [{self.username}] Cookie 登录成功 (优先模式)")
        elif self.login_by_password():
            print(f"🔑 [{self.username}] 账号密码登录成功 (补救模式)")
        else:
            print(f"❌ [{self.username}] 所有登录方式均失效，请检查 Secret 配置")
            return

        # 执行任务
        try:
            # 签到
            self.session.get(f"https://www.gamemale.com/k_misign-sign.html?operation=qiandao&format=button&formhash={self.formhash}", timeout=20)
            # 抽奖
            self.session.get(f"https://www.gamemale.com/plugin.php?id=it618_award:ajax&ac=getaward&formhash={self.formhash}", timeout=20)
            print(f"✨ [{self.username}] 每日任务已尝试提交")
        except Exception as e:
            print(f"❌ [{self.username}] 任务执行出错: {e}")

def main():
    accounts = load_config()
    for acc in accounts:
        bot = GamemaleAutomation(acc)
        bot.run()
        time.sleep(random.uniform(5, 10))

if __name__ == "__main__":
    main()
