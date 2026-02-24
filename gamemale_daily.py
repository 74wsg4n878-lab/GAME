import requests
import re
import ddddocr
import json
import time
import random
import os

def load_config():
    """从 GitHub Secrets 扫描 ACCOUNT_1 到 ACCOUNT_10"""
    all_accounts = []
    for i in range(1, 11):
        acc_str = os.environ.get(f"ACCOUNT_{i}")
        if acc_str and acc_str.strip():
            try:
                # 兼容你提供的这种 JSON 格式
                data = json.loads(acc_str)
                # 如果用户把整个 JSON 贴进去了，我们尝试提取里面的 gamemale 字段
                if "gamemale" in data:
                    all_accounts.append(data["gamemale"])
                else:
                    all_accounts.append(data)
                print(f"::notice::[配置] 成功加载账号变量 ACCOUNT_{i}")
            except Exception as e:
                print(f"::error::[配置] ACCOUNT_{i} 解析失败: {e}")
    if not all_accounts:
        print("::error::未找到配置，请检查 GitHub Secrets 是否包含 ACCOUNT_1")
        exit(1)
    return all_accounts

class GamemaleAutomation:
    def __init__(self, acc):
        self.acc = acc
        self.username = acc.get("username", "未知用户")
        self.password = str(acc.get("password", ""))
        self.session = requests.Session()
        self.formhash = None
        self.ocr = None # 只有需要时才初始化
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
            'Referer': 'https://www.gamemale.com/forum.php'
        })

    def login_by_cookie(self):
        """【第一优先级】尝试 Cookie 登录"""
        cookie = self.acc.get("cookie")
        if not cookie: 
            print(f"❓ [{self.username}] 未提供 Cookie，跳过此步")
            return False
        
        print(f"🍪 [{self.username}] 正在尝试使用 Cookie 登录...")
        try:
            # 处理 Cookie 字符串映射到 Session
            for item in cookie.split(';'):
                if '=' in item:
                    k, v = item.strip().split('=', 1)
                    self.session.cookies.set(k, v, domain='www.gamemale.com')
            
            # 访问空间中心验证是否登录成功
            res = self.session.get('https://www.gamemale.com/home.php?mod=spacecp', timeout=20)
            if 'formhash' in res.text:
                self.formhash = re.search(r'formhash" value="([a-f0-9]+)"', res.text).group(1)
                print(f"✅ [{self.username}] Cookie 登录成功！")
                return True
        except Exception as e:
            print(f"⚠️ [{self.username}] Cookie 登录尝试出错: {e}")
        
        print(f"❌ [{self.username}] Cookie 已失效或无效")
        return False

    def login_by_password(self):
        """【第二优先级】保底方案：账号密码登录"""
        if not self.username or not self.password:
            print(f"❌ [{self.username}] 未提供账号密码，无法尝试保底登录")
            return False
            
        print(f"🔄 [{self.username}] 正在启动账号密码保底登录...")
        try:
            if self.ocr is None:
                self.ocr = ddddocr.DdddOcr(show_ad=False)

            # 1. 初始化登录参数
            init_res = self.session.get('https://www.gamemale.com/member.php?mod=logging&action=login&infloat=yes&inajax=1', timeout=20)
            login_hash = re.search(r'loginform_(\w+)', init_res.text).group(1)
            init_fh = re.search(r'formhash" value="([a-f0-9]+)"', init_res.text).group(1)
            
            # 2. 验证码识别
            sec_url = f'https://www.gamemale.com/misc.php?mod=seccode&action=update&idhash={login_hash}&{random.random()}'
            sec_res = self.session.get(sec_url, timeout=20)
            code_url_match = re.search(r'src="([^"]+seccode[^"]+)"', sec_res.text)
            
            seccode_text = ""
            if code_url_match:
                img_res = self.session.get('https://www.gamemale.com/' + code_url_match.group(1), timeout=20)
                seccode_text = self.ocr.classification(img_res.content)
                print(f"🔍 [{self.username}] 验证码识别成功: {seccode_text}")
            
            # 3. 提交登录
            post_data = {
                'formhash': init_fh,
                'username': self.username,
                'password': self.password,
                'questionid': self.acc.get("questionid", "0"),
                'answer': self.acc.get("answer", ""),
                'seccodeverify': seccode_text
            }
            post_url = f'https://www.gamemale.com/member.php?mod=logging&action=login&loginsubmit=yes&loginhash={login_hash}&inajax=1'
            l_res = self.session.post(post_url, data=post_data, timeout=20)
            
            if '欢迎您回来' in l_res.text:
                cp_res = self.session.get('https://www.gamemale.com/home.php?mod=spacecp', timeout=20)
                self.formhash = re.search(r'formhash" value="([a-f0-9]+)"', cp_res.text).group(1)
                print(f"🔑 [{self.username}] 账号密码登录成功！")
                return True
        except Exception as e:
            print(f"⚠️ [{self.username}] 账号登录过程出现异常: {e}")
        return False

    def run(self):
        # 逻辑：先试 Cookie，不行再试密码
        if not self.login_by_cookie():
            if not self.login_by_password():
                print(f"🚨 [{self.username}] 所有登录手段均失败，请检查配置或手动更新 Cookie")
                return

        # 执行任务
        try:
            # 签到
            self.session.get(f"https://www.gamemale.com/k_misign-sign.html?operation=qiandao&format=button&formhash={self.formhash}", timeout=20)
            # 抽奖
            self.session.get(f"https://www.gamemale.com/plugin.php?id=it618_award:ajax&ac=getaward&formhash={self.formhash}", timeout=20)
            print(f"✨ [{self.username}] 每日任务（签到+抽奖）已尝试完成")
        except Exception as e:
            print(f"❌ [{self.username}] 任务执行时出错: {e}")

def main():
    accounts = load_config()
    for acc in accounts:
        bot = GamemaleAutomation(acc)
        bot.run()
        time.sleep(random.uniform(5, 12))

if __name__ == "__main__":
    main()
