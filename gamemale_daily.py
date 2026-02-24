import requests
import re
import ddddocr
from bs4 import BeautifulSoup
import base64
import json
import time
import random
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# --- [修改部分：支持多账号配置加载] ---
def load_all_configs():
    """
    扫描 ACCOUNT_1 到 ACCOUNT_10 环境变量。
    如果没有，则回退到 APP_CONFIG_JSON 或 config.json。
    """
    all_configs = []
    
    # 尝试加载 ACCOUNT_1 到 ACCOUNT_10
    for i in range(1, 11):
        acc_str = os.environ.get(f"ACCOUNT_{i}")
        if acc_str and acc_str.strip():
            try:
                acc_data = json.loads(acc_str)
                # 兼容性：如果 JSON 只有 gamemale 的内容，则嵌套进字典
                if "gamemale" not in acc_data:
                    acc_data = {"gamemale": acc_data}
                # 继承全局通知配置（如果有的话）
                all_configs.append(acc_data)
            except Exception as e:
                print(f"::error::ACCOUNT_{i} 解析失败: {e}")

    # 如果没找到多账号变量，回退到原有逻辑
    if not all_configs:
        config_json_str = os.environ.get("APP_CONFIG_JSON")
        if config_json_str:
            try: all_configs.append(json.loads(config_json_str))
            except: pass
        elif os.path.exists("config.json"):
            with open("config.json", "r", encoding="utf-8") as f:
                try: all_configs.append(json.load(f))
                except: pass

    if not all_configs:
        print("::error::错误：未找到任何配置。请设置 ACCOUNT_1 或 APP_CONFIG_JSON。")
        exit(1)
    return all_configs

def send_notification(config, message):
    """发送通知消息"""
    notification_config = config.get("notification", {})
    if not notification_config.get("enabled", False):
        return

    notification_type = notification_config.get("type", "console")
    
    try:
        if notification_type == "telegram":
            telegram_config = notification_config.get("telegram", {})
            bot_token = telegram_config.get("bot_token")
            chat_id = telegram_config.get("chat_id")
            if bot_token and chat_id:
                telegram_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
                payload = {"chat_id": chat_id, "text": message, "parse_mode": "HTML"}
                requests.post(telegram_url, json=payload, timeout=10)
                print("Telegram通知发送成功")

        elif notification_type == "wechat":
            wechat_config = notification_config.get("wechat", {})
            webhook = wechat_config.get("webhook")
            if webhook:
                payload = {"msgtype": "text", "text": {"content": message}}
                requests.post(webhook, json=payload, timeout=10)
                print("企业微信通知发送成功")

        elif notification_type == "email":
            email_config = notification_config.get("email", {})
            if all(k in email_config for k in ["smtp_server", "username", "password", "from", "to"]):
                msg = MIMEMultipart()
                msg['From'] = email_config["from"]
                msg['To'] = email_config["to"]
                msg['Subject'] = "Gamemale 多账号任务完成统计"
                text_content = message.replace('🎉', '').replace('📊', '').replace('🎰', '').replace('📈', '').replace('📋', '').replace('•', '-')
                msg.attach(MIMEText(text_content, 'plain', 'utf-8'))
                
                server = smtplib.SMTP(email_config["smtp_server"], email_config.get("smtp_port", 587))
                server.starttls()
                server.login(email_config["username"], email_config["password"])
                server.sendmail(email_config["from"], email_config["to"], msg.as_string())
                server.quit()
                print("邮箱通知发送成功")
        else:
            print("::notice::" + message.replace('\n', '\n::notice::'))

    except Exception as e:
        print(f"发送通知时出错: {e}")

# --- [完全保留的原有震惊互动函数] ---
def interact_with_blogs_regex(session, target_interactions=10, max_pages_to_scan=10):
    print("::group::任务: 开始与日志互动 (目标: 10次成功)")
    successful_user_ids = set()
    processed_user_ids = set()
    processed_blog_urls = set()
    page_num = 1
    while len(successful_user_ids) < target_interactions and page_num <= max_pages_to_scan:
        print(f"🔄 正在扫描第 {page_num}/{max_pages_to_scan} 页以寻找新日志...")
        try:
            base_blog_list_url = 'https://www.gamemale.com/home.php?mod=space&do=blog&view=all'
            current_url = f"{base_blog_list_url}&page={page_num}"
            response = session.get(current_url)
            response.raise_for_status()
            href_matches = re.findall(r'href="([^"]*blog-\d+-\d+\.html[^"]*)"', response.text)
            if not href_matches:
                print("⏹️ 在当前页未找到任何日志链接，停止扫描。")
                break
            new_blogs_found_on_page = 0
            for href in href_matches:
                full_url = href if href.startswith('http') else "https://www.gamemale.com/" + href
                if full_url in processed_blog_urls: continue
                new_blogs_found_on_page += 1
                processed_blog_urls.add(full_url)
                try:
                    print(f"  -> 正在处理新日志... (当前成功: {len(successful_user_ids)}/{target_interactions})")
                    uid_match = re.search(r'blog-(\d+)-', full_url)
                    if not uid_match: continue
                    uid = uid_match.group(1)
                    processed_user_ids.add(uid)
                    page_response = session.get(full_url)
                    page_response.raise_for_status()
                    page_text = page_response.text
                    if "您不能访问当前内容" in page_text or "指定的主题不存在" in page_text: continue

                    shock_button = BeautifulSoup(page_text, 'html.parser').select_one('a[id*="click_blogid_"][id$="_1"]')
                    if not shock_button:
                        print(f"    -> ℹ️ 已表过态或页面结构不同。 (作者UID: {uid})")
                        continue

                    click_url_raw = shock_button.get('href')
                    click_url = (click_url_raw.replace('&', '&') + '&inajax=1') if '&inajax=1' not in click_url_raw else click_url_raw.replace('&', '&')
                    if not click_url.startswith('http'):
                        click_url = "https://www.gamemale.com/" + click_url.lstrip('/')

                    ajax_headers = {'Referer': full_url, 'X-Requested-With': 'XMLHttpRequest'}
                    click_response = session.get(click_url, headers=ajax_headers)
                    response_text = click_response.text.strip()

                    if 'succeed' in response_text or '表态成功' in response_text:
                        print(f"    -> ✅ 成功点击震惊! (作者UID: {uid})")
                        successful_user_ids.add(uid)
                    elif '您已表过态' in response_text:
                        print(f"    -> ℹ️ 已表态过。 (作者UID: {uid})")
                    
                    time.sleep(random.uniform(2, 5))
                    if len(successful_user_ids) >= target_interactions: break
                except Exception as e:
                    print(f"    -> ✗ 处理日志出错: {e}")
            if len(successful_user_ids) >= target_interactions: break
            if new_blogs_found_on_page == 0: break
        except Exception as e:
            print(f"❌ 抓取列表出错: {e}")
            break
        page_num += 1
    print(f"日志互动完成。成功互动 {len(successful_user_ids)} 次。")
    print("::endgroup::")
    return list(successful_user_ids), list(processed_user_ids)

# --- [完全保留的原有自动化类] ---
class GamemaleAutomation:
    def __init__(self, config):
        self.config = config
        self.session = requests.Session()
        self.formhash = None
        self.is_logged_in = False
        self.ocr = ddddocr.DdddOcr(show_ad=False)
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': 'https://www.gamemale.com/forum.php',
        })
    
    def _send_request(self, method, url, **kwargs):
        try:
            response = self.session.request(method, url, **kwargs)
            response.raise_for_status()
            return response
        except requests.RequestException as e:
            print(f"请求失败: {url}")
            raise

    def login(self):
        print("::group::登录流程")
        login_successful = False
        if self.config.get("gamemale", {}).get("cookie"):
            if self._login_with_cookie(): login_successful = True
        if not login_successful and self._login_with_password():
            login_successful = True
        if login_successful:
            self.is_logged_in = True
            self.get_and_store_formhash()
        print("::endgroup::")
        return self.is_logged_in

    def _login_with_cookie(self):
        cookie_string = self.config.get("gamemale", {}).get("cookie")
        username = self.config.get("gamemale", {}).get("username")
        if not cookie_string: return False
        for cookie in cookie_string.split(';'):
            cookie = cookie.strip()
            if '=' in cookie:
                name, value = cookie.split('=', 1)
                self.session.cookies.set(name.strip(), value.strip(), domain='www.gamemale.com')
        try:
            test_url = 'https://www.gamemale.com/home.php?mod=space&do=profile'
            response = self.session.get(test_url, allow_redirects=False)
            if response.status_code == 200 and '登录' not in response.text:
                if not username or (username and username.lower() in response.text.lower()):
                    return True
            return False
        except: return False

    def _login_with_password(self):
        gamemale_config = self.config.get("gamemale", {})
        username = gamemale_config.get("username")
        password = gamemale_config.get("password")
        if not username or not password: return False
        for attempt in range(5):
            try:
                loginhash, formhash, seccodehash, seccode_verify = self._get_login_parameters()
                login_url = f"https://www.gamemale.com/member.php?mod=logging&action=login&loginsubmit=yes&handlekey=login&loginhash={loginhash}&inajax=1"
                payload = {
                    'formhash': formhash, 'referer': 'https://www.gamemale.com/forum.php',
                    'loginfield': 'username', 'username': username, 'password': password,
                    'questionid': gamemale_config.get("questionid", "0"), 'answer': gamemale_config.get("answer", ""),
                    'seccodehash': seccodehash, 'seccodeverify': seccode_verify
                }
                res = self._send_request('POST', login_url, data=payload, headers={'X-Requested-With': 'XMLHttpRequest'})
                if 'succeed' in res.text or '欢迎您回来' in res.text: return True
            except Exception as e:
                print(f"登录重试 {attempt+1}: {e}")
                time.sleep(3)
        return False

    def _get_login_parameters(self):
        ajax_headers = {'X-Requested-With': 'XMLHttpRequest'}
        login_popup_url = 'https://www.gamemale.com/member.php?mod=logging&action=login&infloat=yes&handlekey=login&inajax=1'
        response = self._send_request('GET', login_popup_url, headers=ajax_headers)
        html_content = re.search(r'<!\[CDATA\[(.*)\]\]>', response.text, re.DOTALL).group(1)
        soup = BeautifulSoup(html_content, 'html.parser')
        action_url = soup.find('form', {'name': 'login'})['action']
        loginhash = re.search(r'loginhash=(\w+)', action_url).group(1)
        formhash = soup.find('input', {'name': 'formhash'})['value']
        seccodehash = re.search(r"updateseccode\('([a-zA-Z0-9]+)'", html_content).group(1)
        js_url = f"https://www.gamemale.com/misc.php?mod=seccode&action=update&idhash={seccodehash}&inajax=1"
        js_res = self._send_request('GET', js_url, headers=ajax_headers)
        img_path = re.search(r'src="([^"]+mod=seccode[^"]+)"', js_res.text).group(1).replace('&', '&')
        img_url = "https://www.gamemale.com/" + img_path
        seccode_verify = self.ocr.classification(self._send_request('GET', img_url).content)
        return loginhash, formhash, seccodehash, seccode_verify

    def get_and_store_formhash(self):
        try:
            home_url = 'https://www.gamemale.com/home.php?mod=spacecp'
            response = self._send_request('GET', home_url)
            match = re.search(r'formhash" value="([a-f0-9]+)"', response.text)
            if match: self.formhash = match.group(1)
        except: pass

    def execute_all_tasks(self):
        if not self.is_logged_in: return None
        task_results = {}
        task_results["签到"] = self.quick_daily_sign()
        task_results["抽奖"] = self.quick_daily_lottery()
        successful_uids, processed_uids = interact_with_blogs_regex(self.session, 10)
        task_results["震惊互动"] = len(successful_uids) >= 10
        if processed_uids:
            target_uids = processed_uids[:3]
            task_results["空间访问"] = self.quick_visit_spaces(target_uids)
            task_results["打招呼"] = self.quick_poke_users(target_uids)
        user_credits, exchange_result = self.get_user_credits_and_exchange()
        if exchange_result is not None: task_results["血液兑换"] = exchange_result
        summary_data = self.get_daily_task_summary()
        return self.generate_detailed_report(task_results, user_credits, summary_data)

    def quick_daily_sign(self):
        try:
            url = f"https://www.gamemale.com/k_misign-sign.html?operation=qiandao&format=button&formhash={self.formhash}"
            res = self._send_request('GET', url, headers={'X-Requested-With': 'XMLHttpRequest'}).text
            return 'succeed' in res or '签到成功' in res or '已签' in res
        except: return False

    def quick_daily_lottery(self):
        try:
            url = f"https://www.gamemale.com/plugin.php?id=it618_award:ajax&ac=getaward&formhash={self.formhash}"
            res_json = self._send_request('GET', url, headers={'X-Requested-With': 'XMLHttpRequest'}).json()
            return res_json.get("tipname") == "ok" or res_json.get("tipname") == ""
        except: return False

    def quick_visit_spaces(self, user_ids):
        success = 0
        for uid in user_ids:
            try:
                if self.session.head(f"https://www.gamemale.com/space-uid-{uid}.html").status_code == 200: success += 1
                time.sleep(1)
            except: pass
        return success > 0

    def quick_poke_users(self, user_ids):
        success = 0
        for uid in user_ids:
            try:
                get_url = f"https://www.gamemale.com/home.php?mod=spacecp&ac=poke&op=send&uid={uid}&inajax=1"
                res = self._send_request('GET', get_url, headers={'X-Requested-With': 'XMLHttpRequest'}).text
                if '今天您已经打过招呼了' in res: 
                    success += 1; continue
                content = re.search(r'<!\[CDATA\[(.*)\]\]>', res, re.DOTALL).group(1)
                soup = BeautifulSoup(content, 'html.parser')
                form = soup.find('form', id=f'pokeform_{uid}')
                payload = {'formhash': self.formhash, 'handlekey': f'a_poke_{uid}', 'pokeuid': uid, 'pokesubmit': 'true', 'iconid': '3'}
                post_res = self._send_request('POST', f"https://www.gamemale.com/{form['action'].lstrip('/')}", data=payload, headers={'X-Requested-With': 'XMLHttpRequest'})
                if '已发送' in post_res.text: success += 1
                time.sleep(2)
            except: pass
        return success > 0

    def get_user_credits_and_exchange(self):
        try:
            res = self._send_request('GET', 'https://www.gamemale.com/home.php?mod=spacecp&ac=credit&op=base')
            soup = BeautifulSoup(res.text, 'html.parser')
            credits = {item.get_text(" ", strip=True).split(':')[0].strip(): item.get_text(" ", strip=True).split(':')[1].strip() for item in soup.select('ul.creditl li')}
            blood = int(credits.get("血液", "0 滴").split()[0])
            status = None
            if blood > 34 and self.config.get("gamemale", {}).get("auto_exchange_enabled", True):
                pwd = self.config.get("gamemale", {}).get("password")
                if pwd:
                    p_res = self._send_request('POST', 'https://www.gamemale.com/home.php?mod=spacecp&ac=credit&op=exchange&inajax=1', 
                                              data={'formhash': self.formhash, 'exchangeamount': '1', 'fromcredits': '3', 'tocredits': '1', 'exchangesubmit': 'true', 'password': pwd},
                                              headers={'X-Requested-With': 'XMLHttpRequest'}).text
                    status = '积分操作成功' in p_res
            return credits, status
        except: return {}, None

    def get_daily_task_summary(self):
        try:
            res = self._send_request('GET', 'https://www.gamemale.com/home.php?mod=spacecp&ac=credit&op=log&suboperation=creditrulelog')
            soup = BeautifulSoup(res.text, 'html.parser')
            table = soup.find('table', class_='dt')
            return [{"name": cols[0].get_text(strip=True), "count": cols[1].get_text(strip=True), "time": cols[-1].get_text(strip=True)} 
                    for row in table.find_all('tr')[1:] if len(cols := row.find_all('td')) >= 3]
        except: return []

    def generate_detailed_report(self, results, user_credits, summary):
        msg = f"👤 账号: {self.config.get('gamemale', {}).get('username', '未知')}\n"
        msg += "💳 积分: " + ", ".join([f"{k}:{v}" for k,v in user_credits.items()]) + "\n"
        msg += "📋 任务: " + ", ".join([f"{k}:{'✅' if v else '❌'}" for k,v in results.items()]) + "\n"
        return msg

# --- [修改部分：主程序循环调度] ---
def main():
    try:
        configs = load_all_configs()
        full_report = "📊 Gamemale 多账号执行汇总\n" + "="*30 + "\n"
        
        for index, config in enumerate(configs):
            user_id = config.get("gamemale", {}).get("username", f"Account_{index+1}")
            print(f"\n>>> 正在处理账号: {user_id}")
            
            try:
                client = GamemaleAutomation(config)
                if not client.login():
                    report = f"❌ {user_id}: 登录失败\n"
                else:
                    report = client.execute_all_tasks()
                
                full_report += report + "\n"
                
                # 账号间随机冷却
                if index < len(configs) - 1:
                    time.sleep(random.uniform(10, 20))
                    
            except Exception as e:
                full_report += f"❌ {user_id}: 运行崩溃 ({str(e)})\n"

        print("\n" + "="*50)
        print(full_report)
        print("="*50)
        
        # 使用第一个账号的通知配置发送汇总报告
        send_notification(configs[0], full_report)
            
    except Exception as e:
        print(f"脚本执行失败: {e}")
        exit(1)

if __name__ == "__main__":
    main()
