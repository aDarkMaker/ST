import logging
import requests
import json
import time
import hashlib
import base64
import re
import os
from requests.adapters import HTTPAdapter
from retry import retry
from bs4 import BeautifulSoup
from config.config import setup_logging

logger = setup_logging()

class ZhihuishuAPI:
    def __init__(self):
        self.session = requests.Session()
        self.logger = logger
        self.base_url = "https://passport.zhihuishu.com"
        self.api_url = "https://onlineservice-api.zhihuishu.com"
        
        # 更新请求头
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Origin": "https://www.zhihuishu.com",
            "Referer": "https://www.zhihuishu.com/",
            "Connection": "keep-alive",
            "sec-ch-ua": '"Not A;Brand";v="99", "Chromium";v="121"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-site"
        }
        
        self.uuid = None
        self.student_id = None
        self.session_id = None
        
        # 配置重试策略
        retry_strategy = retry(
            exceptions=Exception, tries=3, delay=2, backoff=2, jitter=1)
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        
    def _get_csrf_token(self):
        """获取CSRF Token"""
        try:
            # 先访问登录页面
            url = "https://www.zhihuishu.com/login"
            resp = self.session.get(url, headers=self.headers)
            if resp.status_code == 200:
                # 从响应中提取csrf token
                match = re.search(r'csrf-token["\']\\s*content=[\'"](.*?)[\'"]', resp.text)
                if match:
                    return match.group(1)
                
                # 尝试使用BeautifulSoup解析
                soup = BeautifulSoup(resp.text, 'html.parser')
                meta = soup.find('meta', attrs={'name': 'csrf-token'})
                if meta and 'content' in meta.attrs:
                    return meta['content']
            return None
        except Exception as e:
            self.logger.error(f"获取CSRF Token失败: {str(e)}")
            return None

    def _encrypt_password(self, password):
        """加密密码 - MD5"""
        return hashlib.md5(password.encode()).hexdigest()

    def _make_request(self, method, url, service_type="passport", **kwargs):
        """统一的请求处理方法"""
        try:
            # 根据服务类型选择基础URL
            base = self.base_url if service_type == "passport" else self.api_url
            
            # 确保URL是完整的
            if not url.startswith('http'):
                url = f"{base}{url}"

            self.logger.debug(f"正在请求: {url}")
            self.logger.debug(f"请求方法: {method}")
            self.logger.debug(f"请求参数: {kwargs}")

            # 确保headers正确设置
            headers = kwargs.pop('headers', {})
            kwargs['headers'] = {**self.headers, **headers}

            # 添加默认超时
            kwargs.setdefault('timeout', 30)

            response = self.session.request(method, url, **kwargs)
            
            # 记录响应状态和内容
            self.logger.debug(f"响应状态码: {response.status_code}")
            self.logger.debug(f"响应内容: {response.text[:500]}")

            if response.status_code == 200:
                content_type = response.headers.get('content-type', '')
                if 'json' in content_type or 'application/json' in content_type:
                    try:
                        return response.json()
                    except json.JSONDecodeError:
                        self.logger.error(f"JSON解析失败: {response.text[:200]}...")
                        return None
                elif 'text/html' in content_type:
                    # 处理HTML响应
                    self.logger.debug("收到HTML响应，尝试解析...")
                    return {'html': response.text, 'url': response.url}
                return response.text
            else:
                response.raise_for_status()
            
        except Exception as e:
            self.logger.error(f"请求失败 ({url}): {str(e)}")
            return None

    def _get_verify_code(self):
        """获取登录验证码"""
        try:
            url = "https://passport.zhihuishu.com/user/validateAccount"
            headers = {
                "Content-Type": "application/x-www-form-urlencoded",
                "Host": "passport.zhihuishu.com",
                "Origin": "https://passport.zhihuishu.com",
                "Referer": "https://passport.zhihuishu.com/login",
                "X-Requested-With": "XMLHttpRequest"
            }
            resp = self.session.get(url, headers={**self.headers, **headers})
            if resp.status_code == 200:
                return True
            return False
        except Exception as e:
            self.logger.error(f"获取验证码失败: {str(e)}")
            return False

    def _prepare_login(self):
        """进行登录预处理"""
        try:
            # 1. 访问主页获取初始cookie
            resp = self.session.get(
                "https://www.zhihuishu.com/",
                headers=self.headers,
                allow_redirects=True
            )
            if resp.status_code != 200:
                return False

            # 2. 访问登录页面
            resp = self.session.get(
                "https://passport.zhihuishu.com/login",
                headers={
                    **self.headers,
                    "Referer": "https://www.zhihuishu.com/"
                },
                allow_redirects=True
            )
            return resp.status_code == 200
        except Exception as e:
            self.logger.error(f"登录预处理失败: {str(e)}")
            return False

    def login(self, username=None, password=None, use_qr=True, qr_callback=None):
        """登录方法，默认使用二维码登录"""
        self.logger.info("开始登录智慧树...")
        try:
            # 进行登录预处理
            if not self._prepare_login():
                self.logger.error("登录预处理失败")
                return False

            # 首先尝试二维码登录方式，更可靠
            if use_qr:
                self.logger.info("使用二维码登录方式")
                # 获取二维码
                qr_url = "https://passport.zhihuishu.com/login/qrcode/login"
                headers = {
                    "Accept": "application/json, text/plain, */*",
                    "Content-Type": "application/json",
                    "Host": "passport.zhihuishu.com",
                    "Origin": "https://passport.zhihuishu.com",
                    "Referer": "https://passport.zhihuishu.com/login"
                }
                
                # 获取二维码
                qr_response = self._make_request('GET', qr_url, headers=headers)
                
                if qr_response:
                    # 处理可能的JSON字符串响应
                    if isinstance(qr_response, str):
                        try:
                            qr_response = json.loads(qr_response)
                        except json.JSONDecodeError:
                            self.logger.error("二维码响应解析失败")
                            return False
                    
                    # 处理HTML响应，尝试从中获取二维码数据
                    if isinstance(qr_response, dict) and 'html' in qr_response:
                        soup = BeautifulSoup(qr_response['html'], 'html.parser')
                        script_tags = soup.find_all('script')
                        for script in script_tags:
                            if script.string and 'qrData' in script.string:
                                match = re.search(r'qrData[\'"]\s*:\s*[\'"]([^"\']+)[\'"]', script.string)
                                qr_uuid_match = re.search(r'qrUuid[\'"]\s*:\s*[\'"]([^"\']+)[\'"]', script.string)
                                if match and qr_uuid_match:
                                    qr_data = match.group(1)
                                    self.uuid = qr_uuid_match.group(1)
                                    if qr_data and self.uuid:
                                        qr_img_path = os.path.join(os.path.dirname(__file__), "../qrcode.png")
                                        with open(qr_img_path, "wb") as f:
                                            f.write(base64.b64decode(qr_data))
                                        self.logger.info(f"二维码已保存到: {qr_img_path}")
                                        print(f"\n请使用智慧树APP扫描二维码 ({qr_img_path}) 登录")
                                        
                                        # 轮询扫码状态
                                        max_attempts = 120  # 提高超时时间
                                        for _ in range(max_attempts):
                                            status = self._check_qr_login_status()
                                            if status == "CONFIRMED":  # 已确认
                                                self.logger.info("二维码登录成功")
                                                time.sleep(1)  # 等待用户信息同步
                                                return self._get_user_info()
                                            elif status == "EXPIRED":  # 已过期
                                                self.logger.error("二维码已过期")
                                                return False
                                            elif status == "SCANNED":  # 已扫码
                                                self.logger.info("请在手机上确认登录")
                                                print("请在手机上确认登录")
                                            time.sleep(1)
                                        
                                        self.logger.error("登录超时")
                                        return False

                    # 处理常规JSON响应
                    if isinstance(qr_response, dict) and 'qrData' in qr_response:
                        qr_data = qr_response.get("qrData", "")
                        self.uuid = qr_response.get("qrUuid", "")
                        
                        if qr_data and self.uuid:
                            qr_img_path = os.path.join(os.path.dirname(__file__), "../qrcode.png")
                            with open(qr_img_path, "wb") as f:
                                f.write(base64.b64decode(qr_data))
                            self.logger.info(f"二维码已保存到: {qr_img_path}")
                            print(f"\n请使用智慧树APP扫描二维码 ({qr_img_path}) 登录")
                            
                            # 轮询扫码状态
                            max_attempts = 120  # 提高超时时间
                            for i in range(max_attempts):
                                status = self._check_qr_login_status()
                                if status == "CONFIRMED":  # 已确认
                                    self.logger.info("二维码登录成功")
                                    time.sleep(1)  # 等待用户信息同步
                                    return self._get_user_info()
                                elif status == "EXPIRED":  # 已过期
                                    self.logger.error("二维码已过期")
                                    return False
                                elif status == "SCANNED":  # 已扫码
                                    self.logger.info("请在手机上确认登录")
                                    print("请在手机上确认登录")
                                
                                # 每10秒更新一次提示
                                if i % 10 == 0 and i > 0:
                                    print(f"等待扫码中... ({i}/{max_attempts}秒)")
                                time.sleep(1)
                            
                            self.logger.error("登录超时")
                            return False
                
                self.logger.error("获取二维码失败，尝试使用账号密码登录")
                
            # 如果二维码登录失败或未使用二维码登录，则尝试账号密码登录
            if username and password:
                self.logger.info(f"使用账号 {username} 登录")
                
                # 直接使用账号密码登录
                # 注意: 将请求方法更改为POST，因为GET不被支持
                login_url = "https://passport.zhihuishu.com/user/validateAccountAndPassword"
                login_data = {
                    "userName": username,
                    "password": self._encrypt_password(password),
                    "areaCode": "86",
                    "clientType": "1"
                }
                
                login_headers = {
                    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                    "Host": "passport.zhihuishu.com",
                    "Origin": "https://passport.zhihuishu.com",
                    "Referer": "https://passport.zhihuishu.com/login",
                    "X-Requested-With": "XMLHttpRequest"
                }
                
                # 明确指定POST方法
                login_response = self.session.post(
                    login_url, 
                    headers={**self.headers, **login_headers}, 
                    data=login_data
                )
                
                self.logger.debug(f"登录响应状态码: {login_response.status_code}")
                self.logger.debug(f"登录响应内容: {login_response.text[:200]}...")
                
                if login_response.status_code == 200:
                    try:
                        login_json = login_response.json()
                        # 检查登录是否成功
                        if login_json.get("status") == 1 or login_json.get("success"):
                            student_info = login_json.get("student") or login_json.get("user", {})
                            self.student_id = student_info.get("studentId") or student_info.get("userId")
                            self.session_id = self.session.cookies.get("SESSION")
                            self.logger.info(f"登录成功，用户ID: {self.student_id}")
                            return True
                        else:
                            error_msg = login_json.get("message", "未知错误")
                            if "验证码" in error_msg:
                                self.logger.error(f"登录需要验证码: {error_msg}")
                            else:
                                self.logger.error(f"登录失败: {error_msg}")
                            return False
                    except json.JSONDecodeError:
                        # 检查响应是否为HTML且包含成功重定向
                        if "www.zhihuishu.com" in login_response.url:
                            self.logger.info("登录成功，正在获取用户信息...")
                            return self._get_user_info()
                        self.logger.error("登录返回的不是有效的JSON数据")
                        return False
                else:
                    self.logger.error(f"登录请求失败，状态码: {login_response.status_code}")
                    return False
                
            self.logger.error("登录失败: 二维码登录失败且未提供有效的用户名和密码")
            return False
            
        except Exception as e:
            self.logger.error(f"登录失败: {str(e)}")
            return False

    def _check_qr_login_status(self):
        """检查二维码登录状态"""
        if not self.uuid:
            return None
            
        check_url = f"https://passport.zhihuishu.com/login/qrcode/status?qrUuid={self.uuid}&timestamp={int(time.time() * 1000)}"
        headers = {
            "Accept": "application/json, text/plain, */*",
            "Host": "passport.zhihuishu.com",
            "Origin": "https://passport.zhihuishu.com",
            "Referer": "https://passport.zhihuishu.com/login"
        }
        
        try:
            resp = self.session.get(check_url, headers=headers)
            if resp.status_code == 200:
                try:
                    data = resp.json()
                    if isinstance(data, dict):
                        return data.get("status")
                    return None
                except json.JSONDecodeError:
                    self.logger.debug("检查二维码状态返回非JSON响应")
                    return None
            return None
        except Exception as e:
            self.logger.error(f"检查二维码状态失败: {str(e)}")
            return None

    def _get_user_info(self):
        """获取用户信息"""
        try:
            # 1. 尝试获取用户基本信息
            basic_info_url = "https://onlineservice.zhihuishu.com/student/user/info"
            headers = {
                "Accept": "application/json, text/plain, */*",
                "Host": "onlineservice.zhihuishu.com", 
                "Origin": "https://onlineservice.zhihuishu.com",
                "Referer": "https://onlineservice.zhihuishu.com/"
            }
            resp = self.session.get(basic_info_url, headers=headers)
            
            if resp.status_code == 200:
                try:
                    data = resp.json()
                    if data.get("status") == 1 and data.get("data"):
                        user_info = data.get("data", {})
                        self.student_id = user_info.get("userId")
                        self.logger.info(f"获取用户信息成功，用户ID: {self.student_id}")
                        return bool(self.student_id)
                except json.JSONDecodeError:
                    pass
                    
            # 2. 备用方法：从学生空间获取信息
            space_url = "https://onlineservice-api.zhihuishu.com/gateway/t/v1/student/space/index"
            headers = {
                "Accept": "application/json, text/plain, */*",
                "Host": "onlineservice-api.zhihuishu.com",
                "Origin": "https://onlineservice-api.zhihuishu.com", 
                "Referer": "https://onlineservice.zhihuishu.com/"
            }
            resp = self.session.get(space_url, headers=headers)
            
            if resp.status_code == 200:
                try:
                    data = resp.json()
                    if data.get("success") and data.get("result"):
                        user_info = data.get("result", {})
                        self.student_id = user_info.get("studentId") or user_info.get("userId")
                        self.logger.info(f"获取用户信息成功，用户ID: {self.student_id}")
                        return bool(self.student_id)
                except json.JSONDecodeError:
                    pass
            
            # 3. 通过课程列表页面获取用户ID
            courses_url = "https://onlineservice-api.zhihuishu.com/gateway/t/v1/student/course/v2/getCourseList"
            headers = {
                "Accept": "application/json, text/plain, */*", 
                "Host": "onlineservice-api.zhihuishu.com",
                "Origin": "https://onlineservice.zhihuishu.com",
                "Referer": "https://onlineservice.zhihuishu.com/learning"
            }
            resp = self.session.get(courses_url, headers=headers)
            if resp.status_code == 200:
                try:
                    data = resp.json()
                    if data.get("code") == 0 and data.get("result"):
                        self.student_id = data.get("result", {}).get("studentId")
                        if self.student_id:
                            self.logger.info(f"通过课程列表获取用户ID成功: {self.student_id}")
                            return True
                except json.JSONDecodeError:
                    pass
                    
            self.logger.error("获取用户信息失败")
            return False
        except Exception as e:
            self.logger.error(f"获取用户信息失败: {str(e)}")
            return False

    def get_course_list(self):
        """获取课程列表"""
        self.logger.info("正在获取课程列表...")
        try:
            url = f"{self.base_url}/course/getData"
            courses = []
            params = {
                "studentId": self.student_id,
                "pageSize": 50,
                "pageIndex": 1
            }
            
            resp = self.session.get(url, params=params, headers=self.headers)
            if resp.status_code == 200:
                data = resp.json()
                if data["success"]:
                    for course in data["data"]["courseList"]:
                        course_info = {
                            "course_id": course["courseId"],
                            "name": course["courseName"],
                            "progress": course.get("progress", "0%"),
                            "recruit_id": course["recruitId"],
                            "secret": course.get("secret", "")
                        }
                        courses.append(course_info)
                        self.logger.debug(f"获取到课程: {course_info['name']}")
                    
                    self.logger.info(f"共获取到 {len(courses)} 门课程")
                    return courses
                else:
                    self.logger.error(f"获取课程列表失败: {data.get('message', '未知错误')}")
            return []
        except Exception as e:
            self.logger.error(f"获取课程列表失败: {str(e)}")
            return []

    def get_course_questions(self, course_id, recruit_id, page_size=50):
        """获取课程问题列表"""
        self.logger.info(f"正在获取课程 {course_id} 的问题列表...")
        try:
            url = f"{self.base_url}/exam/questionList"
            params = {
                "courseId": course_id,
                "recruitId": recruit_id,
                "pageSize": page_size,
                "pageIndex": 1,
                "studentId": self.student_id
            }
            resp = self.session.get(url, params=params, headers=self.headers)
            if resp.status_code == 200:
                data = resp.json()
                if data["success"] and "questionList" in data["data"]:  # 修复这里的语法错误
                    questions = data["data"]["questionList"]
                    self.logger.info(f"获取到 {len(questions)} 个问题")
                    return questions
                else:
                    self.logger.error(f"获取问题列表失败: {data.get('message', '未知错误')}")
            return []
        except Exception as e:
            self.logger.error(f"获取问题列表失败: {str(e)}")
            return []

    def get_question_info(self, question_id):
        """获取问题详情"""
        try:
            url = f"{self.base_url}/exam/questionDetail"
            params = {
                "questionId": question_id,
                "studentId": self.student_id
            }
            resp = self.session.get(url, params=params, headers=self.headers)
            if resp.status_code == 200:
                return resp.json()
            return None
        except Exception as e:
            self.logger.error(f"获取问题详情失败: {str(e)}")
            return None

    def get_answer_in_info_order_by_time(self, question_id, course_id, recruit_id):
        """获取问题的回答列表"""
        try:
            url = f"{self.base_url}/exam/answerList"
            params = {
                "questionId": question_id,
                "courseId": course_id,
                "recruitId": recruit_id,
                "pageSize": 10,
                "pageIndex": 1,
                "orderType": 1,  # 按时间排序
                "studentId": self.student_id
            }
            resp = self.session.get(url, params=params, headers=self.headers)
            if resp.status_code == 200:
                return resp.json()
            return None
        except Exception as e:
            self.logger.error(f"获取回答列表失败: {str(e)}")
            return None

    def answer_question(self, question_id, course_id, recruit_id, answer_text):
        """回答问题"""
        self.logger.info(f"正在回答问题 {question_id}...")
        try:
            url = f"{self.base_url}/exam/saveAnswer"
            data = {
                "questionId": question_id,
                "courseId": course_id,
                "recruitId": recruit_id,
                "answerContent": answer_text,
                "studentId": self.student_id
            }
            resp = self.session.post(url, data=data, headers=self.headers)
            if resp.status_code == 200:
                result = resp.json()
                if result["success"]:
                    answer_id = result["data"]["answerId"]
                    self.logger.info(f"回答成功，答案ID: {answer_id}")
                    # 自动点赞
                    if self.set_answer_like(answer_id):
                        self.logger.debug("已为回答点赞")
                    return True
                else:
                    self.logger.error(f"回答问题失败: {result.get('message', '未知错误')}")
            return False
        except Exception as e:
            self.logger.error(f"回答问题失败: {str(e)}")
            return False

    def set_answer_like(self, answer_id):
        """为回答点赞"""
        try:
            url = f"{self.base_url}/exam/likeAnswer"
            data = {
                "answerId": answer_id,
                "studentId": self.student_id
            }
            resp = self.session.post(url, data=data, headers=self.headers)
            if resp.status_code == 200:
                result = resp.json()
                return result["success"]
            return False
        except Exception as e:
            self.logger.error(f"点赞失败: {str(e)}")
            return False