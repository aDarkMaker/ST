import io
from PIL import Image
import time
import os
from config.config import LOGIN_CONFIG, setup_logging
from utils.api import ZhihuishuAPI

logger = setup_logging()

class AutoAnswer:
    def __init__(self):
        """初始化自动答题类"""
        self.api = ZhihuishuAPI()
        self.logger = logger

    def show_qr(self, qr_data):
        """显示登录二维码"""
        try:
            img = Image.open(io.BytesIO(qr_data))
            img.show()
        except Exception as e:
            self.logger.error(f"显示二维码失败: {str(e)}")
            
    def login(self):
        """处理登录逻辑"""
        # 首先检查是否存在二维码文件
        qr_path = os.path.join(os.path.dirname(__file__), "qrcode.png")
        
        # 判断是否使用二维码登录
        if LOGIN_CONFIG["use_qr"]:
            self.logger.info("使用二维码登录方式")
            if os.path.exists(qr_path):
                try:
                    # 如果已有二维码文件，显示它
                    img = Image.open(qr_path)
                    img.show()
                    print(f"\n请使用智慧树APP扫描二维码 ({qr_path}) 登录")
                except Exception as e:
                    self.logger.error(f"显示已有二维码失败: {str(e)}")
            
            return self.api.login(use_qr=True, qr_callback=self.show_qr)
        else:
            # 检查账号密码是否有效
            if not LOGIN_CONFIG["phone"] or not LOGIN_CONFIG["password"]:
                self.logger.warning("未提供手机号或密码，将尝试使用二维码登录")
                return self.api.login(use_qr=True, qr_callback=self.show_qr)
            else:
                return self.api.login(LOGIN_CONFIG["phone"], LOGIN_CONFIG["password"], use_qr=False)

    def _print_course_list(self, courses):
        """打印课程列表"""
        print("\n可用课程列表:")
        print("-" * 60)
        print(f"{'序号':<6}{'课程名称':<40}{'课程进度':<10}")
        print("-" * 60)
        for idx, course in enumerate(courses):
            print(f"{idx:<6}{course['name'][:38]:<40}{course['progress']:<10}")
        print("-" * 60)

    def select_course(self, courses):
        """选择要答题的课程"""
        if not courses:
            self.logger.warning("没有找到任何课程")
            return None

        self._print_course_list(courses)
        while True:
            try:
                choice = input("\n请选择要答题的课程序号 (-1 退出): ")
                if not choice.strip():
                    continue
                    
                choice = int(choice)
                if choice == -1:
                    return None
                if 0 <= choice < len(courses):
                    return courses[choice]
                else:
                    print("无效的选择，请输入有效的课程序号")
            except ValueError:
                print("请输入数字")

    def auto_answer_questions(self, course, max_questions=30, delay=2):
        """自动回答课程问题"""
        self.logger.info(f"开始为课程 《{course['name']}》 自动答题")
        self.logger.info(f"设置: 最大问题数={max_questions}, 答题延迟={delay}秒")

        questions = self.api.get_course_questions(
            course["course_id"], 
            course["recruit_id"],
            page_size=max_questions
        )

        if not questions:
            self.logger.warning("未找到可回答的问题")
            return 0

        answered_count = 0
        for idx, question in enumerate(questions, 1):
            question_id = question["questionId"]
            question_content = question["content"]

            # 显示进度
            print(f"\r正在处理第 {idx}/{len(questions)} 个问题...", end="")

            # 检查是否已回答
            question_info = self.api.get_question_info(question_id)
            if question_info and question_info.get("rt", {}).get("questionInfo", {}).get("isAnswer"):
                self.logger.debug(f"问题已回答，跳过: {question_content[:50]}...")
                continue

            # 获取其他人的回答
            answers = self.api.get_answer_in_info_order_by_time(
                question_id, 
                course["course_id"], 
                course["recruit_id"]
            )

            if answers and "rt" in answers and "answerInfos" in answers["rt"] and answers["rt"]["answerInfos"]:
                answer = answers["rt"]["answerInfos"][0]
                answer_text = answer["answerContent"]
                self.logger.info(f"\n正在回答问题: {question_content[:100]}...")
                self.logger.debug(f"使用答案: {answer_text[:100]}...")

                if self.api.answer_question(
                    question_id, 
                    course["course_id"], 
                    course["recruit_id"], 
                    answer_text
                ):
                    answered_count += 1
                    self.logger.info(f"已完成第 {answered_count} 个问题的回答")
                    # 随机延迟，避免操作过快
                    sleep_time = delay + (time.time() % 1)
                    time.sleep(sleep_time)
            else:
                self.logger.warning(f"\n未找到问题的可用答案: {question_content[:50]}...")

        print()  # 换行
        self.logger.info(f"自动答题完成，共回答 {answered_count} 个问题")
        return answered_count

    def run(self):
        """运行自动答题程序"""
        self.logger.info("智慧树自动答题程序启动")
        
        if not self.login():
            self.logger.error("登录失败，程序退出")
            return

        total_answered = 0
        while True:
            courses = self.api.get_course_list()
            if not courses:
                self.logger.error("获取课程列表失败，程序退出")
                return

            course = self.select_course(courses)
            if course is None:
                break

            try:
                max_questions = input("请输入要回答的最大问题数量 (默认30): ").strip()
                max_questions = int(max_questions) if max_questions else 30
                
                delay = input("请输入回答问题的延迟时间(秒) (默认2): ").strip()
                delay = float(delay) if delay else 2
                
                count = self.auto_answer_questions(course, max_questions, delay)
                total_answered += count
                
                choice = input("\n是否继续选择其他课程? (y/n): ").lower()
                if choice != 'y':
                    break
            except ValueError as e:
                self.logger.warning(f"输入无效: {str(e)}")
                print("使用默认值继续...")
                count = self.auto_answer_questions(course)
                total_answered += count

        self.logger.info(f"程序执行完毕，本次共回答 {total_answered} 个问题")
        print("\n感谢使用智慧树自动答题程序!")

if __name__ == "__main__":
    auto_answer = AutoAnswer()
    auto_answer.run()