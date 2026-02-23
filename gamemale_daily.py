import requests
import re
import ddddocr  # 核心修复：确保导入正确
from bs4 import BeautifulSoup
import base64
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
    加载配置.
    优先级: 环境变量 APP_CONFIG_JSON > 本地 config.json 文件.
    """
    config_json_str = os.environ.get("APP_CONFIG_JSON")
    if config_json_str:
        print("::notice::从环境变量 APP_CONFIG_JSON 加载配置。")
        try:
            return json.loads(config_json_str)
        except json.JSONDecodeError:
            print("::error::环境变量 APP_CONFIG_JSON 的值不是有效的 JSON。")
            exit(1)
    
    if os.path.exists("config.json"):
        print("::notice::从本地 config.json 文件加载配置。")
        with open("config.json", "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                print("::error::本地 config.json 文件格式无效。")
                exit(1)

    print("::error::错误：未找到配置。请设置 APP_CONFIG_JSON 环境变量或创建 config.json 文件。")
    exit(1)

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
                msg['Subject'] = "Gamemale 每日任务完成统计"
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

def interact_with_blogs_regex(session, target_interactions=10, max_pages_to_scan=10):
    """
    持续查找并与日志互动，直到达到目标次数。
    """
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
                if full_url in processed_blog_urls:
                    continue
                
                new_blogs_found_on_page += 1
                processed_blog_urls.add(full_url)
                
                try:
                    print(f"  -> 正在处理新日志... (当前成功: {len(successful_user_ids)}/{target_interactions})")
                    uid_match = re.search(r'blog-(\d+)-', full_url)
                    if not uid_match:
                        print("    -> ✗ 无法从URL中解析UID，跳过。")
                        continue
                    
                    uid = uid_match.group(1)
                    processed_user_ids.add(uid)
                    
                    page_response = session.get(full_url)
                    page_response.raise_for_status()
                    page_text = page_response.text
                    
                    if "您不能访问当前内容" in page_text or "指定的主题不存在或已被删除或正在被审核" in page_text:
                        print(f"    -> ✗ 无法访问：日志有隐私设置或已删除。 (作者UID: {uid})")
                        continue

                    shock_button = BeautifulSoup(page_text, 'html.parser').select_one('a[id*="click_blogid_"][id$="_1"]')
                    if not shock_button:
                        print(f"    -> ℹ️ 已表过态或页面结构不同，跳过。 (作者UID: {uid})")
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
                        print(f"    -> ℹ️ 您已对该日志表过态，跳过。 (作者UID: {uid})")
                    else:
                        print(f"    -> ❓ 响应内容未知，跳过。 (作者UID: {uid})")

                    time.sleep(random.uniform(2, 5))

                    if len(successful_user_ids) >= target_interactions:
                        print(f"🎉 已完成 {target_interactions} 次成功互动目标！")
                        break # 跳出内层 for 循环
                
                except Exception as e:
                    print(f"    -> ✗ 处理日志 {full_url} 时出错: {e}")

            if len(successful_user_ids) >= target_interactions:
                break # 跳出外层 while 循环

            if new_blogs_found_on_page == 0:
                print("⏹️ 当前页所有日志均已处理过，停止扫描。")
                break

        except Exception as e:
            print(f"❌ 抓取第 {page_num} 页日志列表时出错: {e}")
            break # 发生严重错误时终止
            
        page_num += 1

    if page_num > max_pages_to_scan:
        print(f"⚠️ 已扫描达到最大页数 ({max_pages_to_scan}页)，但未完成目标。")

    print(f"日志互动完成。成功互动 {len(successful_user_ids)} 次，共处理 {len(processed_user_ids)} 个不同作者的日志。")
    print("::endgroup::")
    return list(successful_user_ids), list(processed_user_ids)

class GamemaleAutomation:
    """Gamemale 自动化任务客户端"""
    
    def __init__(self, config):
        self.config = config
        self.session = requests.Session()
        self.formhash = None
        self.is_logged_in = False
        # 核心修复：兼容新版 ddddocr 的初始化方式
        try:
            # 优先尝试新版初始化（无 show_ad 参数）
            self.ocr = ddddocr.DdddOcr()
            print("✅ ddddocr 初始化成功（新版模式）")
        except TypeError:
            # 兼容旧版本（带 show_ad 参数）
            self.ocr = ddddocr.DdddOcr(show_ad=False)
            print("✅ ddddocr 初始化成功（旧版模式）")
        
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': 'https://www.gamemale.com/forum.php',
        })
    
    def _send_request(self, method, url,** kwargs):
        """统一的请求发送方法，包含错误处理和日志记录"""
        try:
            response = self.session.request(method, url, **kwargs)
            response.raise_for_status()
            return response
        except requests.RequestException as e:
            if e.response is not None:
                print(f"请求失败: {url}, 状态码: {e.response.status_code}")
            else:
                print(f"请求失败: {url}, 错误: {e}")
            raise

    def login(self):
        """统一的登录管理"""
        print("::group::登录流程")
        
        login_successful = False
        if self.config.get("gamemale", {}).get("cookie"):
            if self._login_with_cookie():
                print("✅ Cookie 登录成功")
                login_successful = True
        
        if not login_successful and self._login_with_password():
            print("✅ 密码登录成功") 
            login_successful = True
        
        if login_successful:
            self.is_logged_in = True
            self.get_and_store_formhash()
        else:
            print("❌ 所有登录方式均失败")
        
        print("::endgroup::")
        return self.is_logged_in

    def _login_with_cookie(self):
        """使用Cookie尝试登录 (版本B的可靠实现)"""
        cookie_string = self.config.get("gamemale", {}).get("cookie")
        username = self.config.get("gamemale", {}).get("username")
        if not cookie_string:
            return False

        for cookie in cookie_string.split(';'):
            cookie = cookie.strip()
            if '=' in cookie:
                name, value = cookie.split('=', 1)
                self.session.cookies.set(name.strip(), value.strip(), domain='www.gamemale.com')

        try:
            test_url = 'https://www.gamemale.com/home.php?mod=space&do=profile'
            response = self.session.get(test_url, allow_redirects=False)

            if response.status_code == 200 and '登录' not in response.text:
                # 如果提供了用户名，则额外验证用户名是否存在于页面中
                if username and username.lower() in response.text.lower():
                    return True
                # 如果没有提供用户名，则检查通用登录标识
                elif '我的资料' in response.text:
                    return True
            return False
        except Exception as e:
            print(f"::warning::Cookie登录验证过程中出错: {e}")
            return False

    def _login_with_password(self):
        """使用密码进行登录"""
        gamemale_config = self.config.get("gamemale", {})
        username = gamemale_config.get("username")
        password = gamemale_config.get("password")

        if not all([username, password]):
            print("::warning::密码登录所需信息不完整 (用户名或密码缺失)。")
            return False
        
        max_retries = 8
        for attempt in range(max_retries):
            print(f"\n尝试密码登录 ({attempt + 1}/{max_retries})...")
            
            try:
                loginhash, formhash, seccodehash, seccode_verify = self._get_login_parameters()
                
                if not all([loginhash, formhash, seccodehash, seccode_verify]):
                    raise ValueError("获取登录参数失败")

                login_url = f"https://www.gamemale.com/member.php?mod=logging&action=login&loginsubmit=yes&handlekey=login&loginhash={loginhash}&inajax=1"
                payload = {
                    'formhash': formhash,
                    'referer': 'https://www.gamemale.com/forum.php',
                    'loginfield': 'username',
                    'username': username,
                    'password': password,
                    'questionid': gamemale_config.get("questionid", "0"),
                    'answer': gamemale_config.get("answer", ""),
                    'seccodehash': seccodehash,
                    'seccodeverify': seccode_verify
                }
                
                login_response = self._send_request('POST', login_url, data=payload, headers={'X-Requested-With': 'XMLHttpRequest'})
                if 'succeed' in login_response.text or '欢迎您回来' in login_response.text:
                    return True
                else:
                    error_match = re.search(r'<!\[CDATA\[(.*?)(?:<script|\]\])', login_response.text)
                    raise ValueError(error_match.group(1).strip() if error_match else "未知登录错误")
            
            except Exception as e:
                print(f"登录尝试失败: {e}")
                if attempt < max_retries - 1:
                    time.sleep(random.uniform(2, 5))
        
        return False

    def _get_login_parameters(self):
        """获取登录所需的动态参数和验证码"""
        ajax_headers = {'X-Requested-With': 'XMLHttpRequest'}
        login_popup_url = 'https://www.gamemale.com/member.php?mod=logging&action=login&infloat=yes&handlekey=login&inajax=1'
        response = self._send_request('GET', login_popup_url, headers=ajax_headers)
        
        html_content_match = re.search(r'<!\[CDATA\[(.*)\]\]>', response.text, re.DOTALL)
        if not html_content_match:
            # 增加日志，帮助调试
            print("::warning::在 _get_login_parameters 中未能从响应中提取到 CDATA 内容。")
            print(f"::debug::响应文本预览: {response.text[:500]}")
            raise ValueError("无法从登录弹窗响应中提取HTML内容。")
        html_content = html_content_match.group(1)

        soup = BeautifulSoup(html_content, 'html.parser')
        
        action_tag = soup.find('form', {'name': 'login'})
        if not action_tag or not action_tag.has_attr('action'):
             raise ValueError("未找到登录表单的action URL。")
        action_url = action_tag['action']

        loginhash_match = re.search(r'loginhash=(\w+)', action_url)
        if not loginhash_match:
            raise ValueError("未找到loginhash。")
        loginhash = loginhash_match.group(1)

        formhash_tag = soup.find('input', {'name': 'formhash'})
        if not formhash_tag or not formhash_tag.has_attr('value'):
            raise ValueError("未找到formhash。")
        formhash = formhash_tag['value']

        seccodehash_match = re.search(r"updateseccode\('([a-zA-Z0-9]+)'", html_content)
        if not seccodehash_match:
            raise ValueError\)
