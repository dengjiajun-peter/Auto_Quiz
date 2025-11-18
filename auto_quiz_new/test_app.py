import unittest
import os
import json
import sqlite3
import tempfile
import base64
from io import BytesIO
from unittest.mock import patch, MagicMock

# 设置环境变量以避免加载 .env 文件
os.environ['SECRET_KEY'] = 'test_secret_key'

# 导入应用模块
import sys
sys.path.append('.')

from app import app, DBHelper, TextGrader, AutoMarker, KnowledgeGraph, AdaptiveEngine, LearningPathGenerator

class TestDatabaseSetup(unittest.TestCase):
    """测试数据库初始化和基本操作"""
    
    def setUp(self):
        """创建临时数据库"""
        self.db_fd, self.db_path = tempfile.mkstemp()
        self.conn = sqlite3.connect(self.db_path)
        self.setup_test_database()
    
    def setup_test_database(self):
        """设置测试数据库结构"""
        cursor = self.conn.cursor()
        
        # 创建所有必要的表
        cursor.executescript('''
            CREATE TABLE IF NOT EXISTS assignments (
                id INTEGER PRIMARY KEY AUTOINCREMENT, 
                title TEXT NOT NULL
            );
            
            CREATE TABLE IF NOT EXISTS questions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                qid TEXT UNIQUE NOT NULL,
                assignment_id INTEGER NOT NULL,
                qtype TEXT NOT NULL,
                text TEXT NOT NULL,
                options TEXT,
                answer TEXT NOT NULL,
                concepts TEXT NOT NULL,
                difficulty INTEGER NOT NULL,
                FOREIGN KEY (assignment_id) REFERENCES assignments (id)
            );
            
            CREATE TABLE IF NOT EXISTS user_mastery (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                mastery_json TEXT NOT NULL,
                error_history TEXT NOT NULL DEFAULT '[]',
                learning_behavior TEXT NOT NULL DEFAULT '{}'
            );
            
            CREATE TABLE IF NOT EXISTS submissions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                assignment_id INTEGER NOT NULL,
                score REAL NOT NULL,
                total INTEGER NOT NULL,
                date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            
            CREATE TABLE IF NOT EXISTS learning_paths (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                path_json TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        ''')
        
        # 插入测试数据
        cursor.execute("INSERT OR IGNORE INTO assignments (id, title) VALUES (1, 'Addition & Subtraction')")
        cursor.execute("INSERT OR IGNORE INTO assignments (id, title) VALUES (2, 'Multiplication')")
        cursor.execute("INSERT OR IGNORE INTO assignments (id, title) VALUES (3, 'Fractions')")
        
        # 插入测试问题
        test_questions = [
            ('AS01', 1, 'mcq', 'What is 5 + 3?', '["8", "7", "9", "6"]', '8', '["addition within 100"]', 1),
            ('AS02', 1, 'judge', '5 + 5 = 10 (True/False)', '[]', 'true', '["addition within 100"]', 1),
            ('AS03', 1, 'blank', 'What is 2 + 3?', '[]', '5', '["addition within 100"]', 1),
            ('MD01', 2, 'mcq', 'What is 2 × 2?', '["4", "5", "3", "6"]', '4', '["multiplication (2x)"]', 1),
            ('FR01', 3, 'mcq', '1 slice of pizza cut into 2 parts: what fraction?', '["1/2", "1/3", "1/4", "2/1"]', '1/2', '["fraction recognition (1/2)"]', 1)
        ]
        
        for q in test_questions:
            cursor.execute('''
                INSERT OR IGNORE INTO questions 
                (qid, assignment_id, qtype, text, options, answer, concepts, difficulty)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', q)
        
        self.conn.commit()
    
    def tearDown(self):
        """清理测试数据库"""
        self.conn.close()
        os.close(self.db_fd)
        os.unlink(self.db_path)
    
    def test_database_creation(self):
        """测试数据库创建和表结构"""
        cursor = self.conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]
        
        expected_tables = ['assignments', 'questions', 'user_mastery', 'submissions', 'learning_paths']
        for table in expected_tables:
            self.assertIn(table, tables)
    
    def test_test_data_insertion(self):
        """测试测试数据插入"""
        cursor = self.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM questions")
        count = cursor.fetchone()[0]
        self.assertGreaterEqual(count, 5)

class TestTextGrader(unittest.TestCase):
    """测试文本评分功能"""
    
    def setUp(self):
        self.ref_texts = [
            "Addition means combining numbers to get a sum.",
            "Subtraction means taking one number away from another.",
            "Multiplication is repeated addition.",
            "A fraction represents equal parts of a whole."
        ]
        self.grader = TextGrader(self.ref_texts)
    
    def test_tfidf_similarity_identical(self):
        """测试相同文本的相似度"""
        similarity = self.grader.tfidf_sim("addition of numbers", "addition of numbers")
        self.assertAlmostEqual(similarity, 1.0, places=2)
    
    def test_tfidf_similarity_related(self):
        """测试相关文本的相似度"""
        similarity = self.grader.tfidf_sim("adding numbers", "combining numbers to get sum")
        self.assertGreater(similarity, 0.15)  # 应该有一定相似度（短文本相似度较低）
    
    def test_tfidf_similarity_unrelated(self):
        """测试不相关文本的相似度"""
        similarity = self.grader.tfidf_sim("addition", "fraction recognition")
        self.assertLess(similarity, 0.5)  # 应该相似度较低
    
    def test_grade_short_perfect_match(self):
        """测试完美匹配的简答题评分"""
        score, analysis = self.grader.grade_short(
            "Addition is combining numbers to find the total sum",
            "addition, combining numbers, sum"
        )
        self.assertGreaterEqual(score, 0.8)  # 应该高分
        self.assertGreaterEqual(len(analysis["mastered"]), 2)
    
    def test_grade_short_partial_match(self):
        """测试部分匹配的简答题评分"""
        score, analysis = self.grader.grade_short(
            "Addition is putting numbers together",
            "addition, combining numbers, sum, total"
        )
        self.assertGreaterEqual(score, 0.0)
        self.assertLessEqual(score, 1.0)

class TestAutoMarker(unittest.TestCase):
    """测试自动评分器"""
    
    def setUp(self):
        self.grader = TextGrader(["test reference"])
        self.marker = AutoMarker(self.grader)
    
    def test_grade_mcq_correct(self):
        """测试选择题正确回答"""
        question = {
            "qtype": "mcq",
            "answer": "8",
            "concepts": '["addition within 100"]'
        }
        score, analysis = self.marker.grade(question, "8")
        self.assertEqual(score, 1.0)
        self.assertEqual(len(analysis["mastered"]), 1)
        self.assertEqual(analysis["mastered"][0], "addition within 100")
    
    def test_grade_mcq_incorrect(self):
        """测试选择题错误回答"""
        question = {
            "qtype": "mcq",
            "answer": "8", 
            "concepts": '["addition within 100"]'
        }
        score, analysis = self.marker.grade(question, "7")
        self.assertEqual(score, 0.0)
        self.assertEqual(len(analysis["missed"]), 1)
        self.assertEqual(analysis["missed"][0], "addition within 100")
    
    def test_grade_judge_correct(self):
        """测试判断题正确回答"""
        question = {
            "qtype": "judge",
            "answer": "true",
            "concepts": '["addition within 100"]'
        }
        score, analysis = self.marker.grade(question, "true")
        self.assertEqual(score, 1.0)
    
    def test_grade_judge_incorrect(self):
        """测试判断题错误回答"""
        question = {
            "qtype": "judge",
            "answer": "true",
            "concepts": '["addition within 100"]'
        }
        score, analysis = self.marker.grade(question, "false")
        self.assertEqual(score, 0.0)
    
    def test_grade_blank_correct(self):
        """测试填空题正确回答"""
        question = {
            "qtype": "blank", 
            "answer": "5",
            "concepts": '["addition within 100"]'
        }
        score, analysis = self.marker.grade(question, "5")
        self.assertEqual(score, 1.0)
    
    def test_grade_blank_incorrect(self):
        """测试填空题错误回答"""
        question = {
            "qtype": "blank",
            "answer": "5",
            "concepts": '["addition within 100"]'
        }
        score, analysis = self.marker.grade(question, "6")
        self.assertEqual(score, 0.0)

class TestKnowledgeGraph(unittest.TestCase):
    """测试知识图谱功能"""
    
    def setUp(self):
        self.kg = KnowledgeGraph()
    
    def test_graph_construction(self):
        """测试知识图谱构建"""
        # 检查图谱是否包含预期的节点
        self.assertIn("addition within 100", self.kg.graph.nodes)
        self.assertIn("multiplication tables (2-9)", self.kg.graph.nodes)
        self.assertIn("fraction recognition (1/2, 1/3, ..., 1/10)", self.kg.graph.nodes)
    
    def test_related_concepts(self):
        """测试相关概念查询"""
        related = self.kg.get_related_concepts("addition within 100")
        self.assertIsInstance(related, list)
        # 检查是否包含预期的相关概念
        self.assertIn("carry addition", related)
    
    def test_related_questions(self):
        """测试相关问题查询"""
        # 由于测试环境可能没有完整的问题数据，我们主要测试函数调用不报错
        related_questions = self.kg.get_related_questions(["addition within 100"])
        self.assertIsInstance(related_questions, list)

class TestAdaptiveEngine(unittest.TestCase):
    """测试自适应引擎"""
    
    def setUp(self):
        self.kg = KnowledgeGraph()
        # 创建临时数据库连接用于测试
        self.db_fd, self.db_path = tempfile.mkstemp()
        self.conn = sqlite3.connect(self.db_path)
        self.setup_test_database()
        self.engine = AdaptiveEngine(self.kg)
        # 手动设置问题缓存
        self.engine.question_cache = self.load_test_questions()
    
    def load_test_questions(self):
        """加载测试问题到缓存"""
        return {
            "Q1": {
                "qid": "Q1", 
                "assignment_id": 1, 
                "qtype": "mcq", 
                "text": "Test Question", 
                "options": [], 
                "answer": "A", 
                "concepts": '["test"]', 
                "difficulty": 1
            },
            "Q2": {
                "qid": "Q2", 
                "assignment_id": 1, 
                "qtype": "mcq", 
                "text": "Test Question 2", 
                "options": [], 
                "answer": "B", 
                "concepts": '["test"]', 
                "difficulty": 1
            }
        }
    
    def setup_test_database(self):
        """设置测试数据库"""
        cursor = self.conn.cursor()
        cursor.executescript('''
            CREATE TABLE IF NOT EXISTS questions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                qid TEXT UNIQUE NOT NULL,
                assignment_id INTEGER NOT NULL,
                qtype TEXT NOT NULL,
                text TEXT NOT NULL,
                options TEXT,
                answer TEXT NOT NULL,
                concepts TEXT NOT NULL,
                difficulty INTEGER NOT NULL
            );
            
            CREATE TABLE IF NOT EXISTS user_mastery (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                mastery_json TEXT NOT NULL,
                error_history TEXT NOT NULL DEFAULT '[]',
                learning_behavior TEXT NOT NULL DEFAULT '{}'
            );
        ''')
        
        self.conn.commit()
    
    def tearDown(self):
        self.conn.close()
        os.close(self.db_fd)
        os.unlink(self.db_path)
    
    def test_mastery_calculation_new_user(self):
        """测试新用户的掌握度计算"""
        mastery = self.engine.calculate_mastery("new_test_user")
        self.assertIsInstance(mastery, dict)
        # 新用户应该有一些初始掌握度值
        self.assertIn("addition within 100", mastery)
        self.assertGreater(mastery["addition within 100"], 0.0)
    
    def test_mastery_update(self):
        """测试掌握度更新"""
        test_question = {
            "concepts": ["addition within 100"],  # Use list instead of JSON string
            "qid": "AS01"
        }
        
        # Mock DBHelper.get_conn to use test DB connection
        with patch('app.DBHelper.get_conn', return_value=self.conn):
            # 获取初始掌握度
            initial_mastery = self.engine.calculate_mastery("update_test_user")
            initial_value = initial_mastery["addition within 100"]
            
            # 更新掌握度（正确回答）
            self.engine.update_mastery("update_test_user", test_question, 1.0)
            
            # 获取更新后的掌握度
            updated_mastery = self.engine.calculate_mastery("update_test_user")
            updated_value = updated_mastery["addition within 100"]
            
            # 掌握度应该提高（0.7 * 0.4 + 0.3 * 1.0 = 0.58）
            self.assertGreater(updated_value, initial_value)
    
    def test_question_selection(self):
        """测试问题选择功能"""
        questions = self.engine.choose_next_questions("test_user", 1, 2)
        self.assertEqual(len(questions), 2)
        # Check that both questions are from module 1, order may vary due to shuffle
        qids = {q["qid"] for q in questions}
        self.assertTrue(qids.issubset({"Q1", "Q2"}))

class TestLearningPathGenerator(unittest.TestCase):
    """测试学习路径生成器"""
    
    def setUp(self):
        self.kg = KnowledgeGraph()
        self.adaptive_engine = AdaptiveEngine(self.kg)
        self.generator = LearningPathGenerator(self.kg, self.adaptive_engine)
    
    def test_path_generation_new_user(self):
        """测试新用户的学习路径生成"""
        path = self.generator.generate_path("completely_new_user")
        self.assertIsInstance(path, list)
        # 新用户应该收到基础复习路径
        if len(path) > 0:
            self.assertIn("No Recent Errors!", path[0]["stage"])
    
    def test_concept_explanation(self):
        """测试概念解释生成"""
        explanation = self.generator._get_concept_explanation("addition within 100")
        self.assertIsInstance(explanation, str)
        self.assertGreater(len(explanation), 10)
    
    def test_simple_example(self):
        """测试简单示例生成"""
        example = self.generator._get_simple_example("addition within 100")
        self.assertIsInstance(example, str)
        self.assertGreater(len(example), 5)
    
    def test_kid_tip(self):
        """测试学习提示生成"""
        tip = self.generator._get_kid_tip("addition within 100")
        self.assertIsInstance(tip, str)
        self.assertGreater(len(tip), 5)

class TestFlaskRoutes(unittest.TestCase):
    """测试Flask路由"""
    
    def setUp(self):
        app.config['TESTING'] = True
        app.config['WTF_CSRF_ENABLED'] = False  # 修正拼写错误
        self.client = app.test_client()
        
        # 创建临时数据库
        self.db_fd, self.db_path = tempfile.mkstemp()
        self.conn = sqlite3.connect(self.db_path)
        self.setup_test_database()
        
        # 模拟数据库连接
        self.db_patch = patch('app.DBHelper.get_conn')
        self.mock_get_conn = self.db_patch.start()
        self.mock_get_conn.return_value = self.conn
    
    def setup_test_database(self):
        """设置测试数据库"""
        cursor = self.conn.cursor()
        
        # 创建表
        cursor.executescript('''
            CREATE TABLE IF NOT EXISTS assignments (
                id INTEGER PRIMARY KEY AUTOINCREMENT, 
                title TEXT NOT NULL
            );
            
            CREATE TABLE IF NOT EXISTS questions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                qid TEXT UNIQUE NOT NULL,
                assignment_id INTEGER NOT NULL,
                qtype TEXT NOT NULL,
                text TEXT NOT NULL,
                options TEXT,
                answer TEXT NOT NULL,
                concepts TEXT NOT NULL,
                difficulty INTEGER NOT NULL
            );
            
            CREATE TABLE IF NOT EXISTS user_mastery (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                mastery_json TEXT NOT NULL,
                error_history TEXT NOT NULL DEFAULT '[]',
                learning_behavior TEXT NOT NULL DEFAULT '{}'
            );
            
            CREATE TABLE IF NOT EXISTS submissions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                assignment_id INTEGER NOT NULL,
                score REAL NOT NULL,
                total INTEGER NOT NULL,
                date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            
            CREATE TABLE IF NOT EXISTS learning_paths (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                path_json TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        ''')

        
        # 插入测试数据
        cursor.execute("INSERT OR IGNORE INTO assignments (id, title) VALUES (1, 'Test Module')")
        
        # 插入几个测试问题
        test_questions = [
            ('TEST01', 1, 'mcq', 'Test question 1?', '["A", "B", "C", "D"]', 'A', '["test concept"]', 1),
            ('TEST02', 1, 'judge', 'Test statement (True/False)?', '[]', 'true', '["test concept"]', 1),
        ]
        
        for q in test_questions:
            cursor.execute('''
                INSERT OR IGNORE INTO questions 
                (qid, assignment_id, qtype, text, options, answer, concepts, difficulty)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', q)
        
        self.conn.commit()
    
    def tearDown(self):
        self.conn.close()
        os.close(self.db_fd)
        os.unlink(self.db_path)
        self.db_patch.stop()
    
    def test_index_route(self):
        """测试主页路由"""
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'1st Grade Math Quiz', response.data)
    
    def test_enter_username_route(self):
        """测试用户名输入页面"""
        response = self.client.get('/enter-username?module_id=1')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Enter Your Name', response.data)
    
    def test_quiz_route(self):
        """测试测验页面"""
        response = self.client.get('/quiz?username=testuser&module_id=1')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'testuser', response.data)
    
    def test_learning_path_route(self):
        """测试学习路径页面"""
        response = self.client.get('/learning-path?username=testuser')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Learning Path', response.data)
    
    def test_report_route(self):
        """测试报告页面"""
        response = self.client.get('/report?username=testuser')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Progress Report', response.data)

def run_all_tests():
    """运行所有测试并生成报告"""
    # 创建测试套件
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # 添加所有测试类
    suite.addTests(loader.loadTestsFromTestCase(TestDatabaseSetup))
    suite.addTests(loader.loadTestsFromTestCase(TestTextGrader))
    suite.addTests(loader.loadTestsFromTestCase(TestAutoMarker))
    suite.addTests(loader.loadTestsFromTestCase(TestKnowledgeGraph))
    suite.addTests(loader.loadTestsFromTestCase(TestAdaptiveEngine))
    suite.addTests(loader.loadTestsFromTestCase(TestLearningPathGenerator))
    suite.addTests(loader.loadTestsFromTestCase(TestFlaskRoutes))
    
    # 运行测试
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    return result

if __name__ == '__main__':
    print("=" * 70)
    print("🧪 智能数学辅导系统 - 完整测试套件")
    print("=" * 70)
    
    # 运行测试
    result = run_all_tests()
    
    # 生成测试报告
    print("\n" + "=" * 70)
    print("📊 测试结果总结")
    print("=" * 70)
    print(f"✅ 运行测试总数: {result.testsRun}")
    print(f"❌ 失败测试: {len(result.failures)}")
    print(f"🚨 错误测试: {len(result.errors)}")
    
    if result.wasSuccessful():
        print("\n🎉 所有测试通过！系统功能正常。")
        print("✨ 智能辅导系统准备就绪，可以投入使用。")
    else:
        print("\n⚠️  部分测试未通过，需要检查：")
        if result.failures:
            print("\n失败的测试:")
            for test, traceback in result.failures:
                print(f"  - {test}: {traceback.splitlines()[-1]}")
        if result.errors:
            print("\n错误的测试:")
            for test, traceback in result.errors:
                print(f"  - {test}: {traceback.splitlines()[-1]}")
    
    print("=" * 70)