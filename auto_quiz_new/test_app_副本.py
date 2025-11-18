import unittest
import os
import json
import sqlite3
import base64
from io import BytesIO
from unittest.mock import patch, MagicMock
from app import (
    DBHelper, TextGrader, AutoMarker, KnowledgeGraph, AdaptiveEngine,
    LearningPathGenerator, app
)
# Note: We patch 'matplotlib.pyplot' and 'app.DBHelper.get_conn' 
# to ensure tests are isolated and don't create real files or use the production DB.

# --- Test Data Setup ---
TEST_ASSIGNMENT_ID = 99
TEST_ASSIGNMENT_TITLE = "Test Math Module (Addition)"
TEST_USERNAME = "test_user_01"

TEST_QUESTION_1 = {
    "qid": "Q9901", "assignment_id": TEST_ASSIGNMENT_ID, "qtype": "mcq",
    "text": "What is 3 + 4?", "options": '["5", "7", "9"]', "answer": "7",
    "concepts": '["addition within 100"]', "difficulty": 2
}
TEST_QUESTION_2_SHORT = {
    "qid": "Q9902", "assignment_id": TEST_ASSIGNMENT_ID, "qtype": "short_answer",
    "text": "List two fruits.", "options": '[]', "answer": "apple, banana",
    "concepts": '["vocabulary"]', "difficulty": 1
}


def setup_in_memory_db(conn):
    """Creates the necessary schema and inserts base test data into the in-memory connection."""
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS assignments 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL)''')
    c.execute('''CREATE TABLE IF NOT EXISTS questions 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, qid TEXT UNIQUE NOT NULL, 
                  assignment_id INTEGER NOT NULL, qtype TEXT NOT NULL, text TEXT NOT NULL, 
                  options TEXT, answer TEXT NOT NULL, concepts TEXT NOT NULL, 
                  difficulty INTEGER NOT NULL)''')
    c.execute('''CREATE TABLE IF NOT EXISTS user_mastery 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL, 
                  mastery_json TEXT NOT NULL, error_history TEXT NOT NULL DEFAULT '[]', 
                  learning_behavior TEXT NOT NULL DEFAULT '{}')''')
    c.execute('''CREATE TABLE IF NOT EXISTS submissions
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT NOT NULL, 
                  score REAL NOT NULL, total_questions INTEGER NOT NULL, 
                  module_id INTEGER NOT NULL, submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    c.execute('''CREATE TABLE IF NOT EXISTS learning_paths
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT NOT NULL, 
                  path_json TEXT NOT NULL DEFAULT '[]', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, 
                  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')

    # Insert test assignment
    c.execute("INSERT OR IGNORE INTO assignments (id, title) VALUES (?, ?)", (TEST_ASSIGNMENT_ID, TEST_ASSIGNMENT_TITLE))

    # Insert test questions (1 for specific testing, 10+ for the quiz route)
    c.execute("INSERT OR IGNORE INTO questions VALUES (?,?,?,?,?,?,?,?,?)",
              (None, TEST_QUESTION_1['qid'], TEST_ASSIGNMENT_ID,
               TEST_QUESTION_1['qtype'], TEST_QUESTION_1['text'], TEST_QUESTION_1['options'],
               TEST_QUESTION_1['answer'], TEST_QUESTION_1['concepts'], TEST_QUESTION_1['difficulty']))
    
    # Add 10 more questions for module 99 so the quiz route can fetch 10 unique questions
    for i in range(10): 
         c.execute("INSERT OR IGNORE INTO questions VALUES (?,?,?,?,?,?,?,?,?)",
              (None, f'Q{TEST_ASSIGNMENT_ID:02}{i:02}', TEST_ASSIGNMENT_ID,
               TEST_QUESTION_1['qtype'], TEST_QUESTION_1['text'], TEST_QUESTION_1['options'],
               TEST_QUESTION_1['answer'], TEST_QUESTION_1['concepts'], TEST_QUESTION_1['difficulty']))
    
    conn.commit()




# --- Grading Logic Tests ---

class TestTextGrader(unittest.TestCase):
    def setUp(self):
        # TextGrader internal object should be mocked or initialized correctly
        self.grader = TextGrader(["The sky is blue.", "Grass is green."])
        
    def test_tfidf_sim_high_and_low(self):
        """Tests high similarity for identical texts and low for unrelated texts."""
        # High similarity
        sim_high = self.grader.tfidf_sim("This is a test.", "This is a test.")
        self.assertAlmostEqual(sim_high, 1.0)
        
        # Low similarity
        sim_low = self.grader.tfidf_sim("Cat.", "Dog.")
        self.assertLess(sim_low, 0.1)

    def test_grade_short_perfect_match(self):
        """Test perfect score when all key points are covered."""
        ref = "apple, banana, orange"
        student = "I like bananas, apples, and oranges very much."
        score, info = self.grader.grade_short(student, ref)
        self.assertAlmostEqual(score, 1.0)
        self.assertEqual(len(info["mastered"]), 3)
        self.assertEqual(len(info["missed"]), 0)

    def test_grade_short_partial_match(self):
        """Test partial score when some key points are missed."""
        ref = "apple, banana, orange"
        student = "I only mentioned apple and banana."
        score, info = self.grader.grade_short(student, ref)
        # 2/3 points should be covered, approximately 0.66
        self.assertAlmostEqual(score, 2/3, places=2) 
        self.assertEqual(len(info["mastered"]), 2)
        self.assertEqual(len(info["missed"]), 1)


class TestAutoMarker(unittest.TestCase):
    def setUp(self):
        self.grader = MagicMock(spec=TextGrader)
        self.marker = AutoMarker(self.grader)

    def test_grade_judge(self):
        """Test grading for Judge (True/False) questions."""
        q = {"qtype": "judge", "answer": "True", "concepts": json.dumps(["concept_A"])}
        score_c, info_c = self.marker.grade(q, "True")
        self.assertEqual(score_c, 1.0)
        score_i, info_i = self.marker.grade(q, "FALSE") # Case insensitive check
        self.assertEqual(score_i, 0.0)

    def test_grade_blank(self):
        """Test grading for Blank (Fill-in-the-blank) questions (case/space insensitive)."""
        q = {"qtype": "blank", "answer": "3r2", "concepts": json.dumps(["concept_C"])}
        score_c1, _ = self.marker.grade(q, "3 r 2") # Space insensitive check
        self.assertEqual(score_c1, 1.0) 

        score_i, _ = self.marker.grade(q, "4r1")
        self.assertEqual(score_i, 0.0)

    def test_grade_delegation_to_textgrader(self):
        """Test that short_answer questions use TextGrader."""
        q = {"qtype": "short_answer", "answer": "key", "concepts": json.dumps(["vocab"])}
        # Mock TextGrader's return value
        self.grader.grade_short.return_value = (0.7, {"mastered": ["vocab"], "missed": []})

        score, info = self.marker.grade(q, "student_answer")
        self.assertEqual(score, 0.7)
        self.grader.grade_short.assert_called_once()


# --- Adaptive Engine Core Tests ---

class TestAdaptiveEngine(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(':memory:')
        setup_in_memory_db(self.conn)
        self.kg = KnowledgeGraph() 
        # 直接将测试连接注入 AdaptiveEngine，避免依赖 DBHelper.get_conn
        self.engine = AdaptiveEngine(kg=self.kg, conn=self.conn)  

    def tearDown(self):
        self.conn.close()

    def test_calculate_mastery_update(self):
        """Tests the ELO-like update rule (M_new = 0.7*M_old + 0.3*score)."""
        concept = "addition within 100"
        q = {"concepts": json.dumps([concept])}
        
        # 1. Initial mastery (default is 0.4 for core concepts)
        initial_mastery = self.engine.calculate_mastery(TEST_USERNAME)[concept]
        self.assertAlmostEqual(initial_mastery, 0.4) 

        # 2. Correct answer (score=1.0)
        self.engine.update_mastery(TEST_USERNAME, q, 1.0)
        updated_mastery_1 = self.engine.calculate_mastery(TEST_USERNAME)[concept]
        # Expected: 0.7 * 0.4 + 0.3 * 1.0 = 0.28 + 0.3 = 0.58
        self.assertAlmostEqual(updated_mastery_1, 0.58)

        # 3. Incorrect answer (score=0.0)
        self.engine.update_mastery(TEST_USERNAME, q, 0.0)
        updated_mastery_2 = self.engine.calculate_mastery(TEST_USERNAME)[concept]
        # Expected: 0.7 * 0.58 + 0.3 * 0.0 = 0.406
        self.assertAlmostEqual(updated_mastery_2, 0.406)

    def test_choose_next_questions_count(self):
        """Test that exactly 10 questions are returned for the module."""
        questions = self.engine.choose_next_questions(TEST_USERNAME, TEST_ASSIGNMENT_ID, target_count=10)
        self.assertEqual(len(questions), 10)
        self.assertTrue(all(q['assignment_id'] == TEST_ASSIGNMENT_ID for q in questions))

    def test_choose_next_questions_no_questions(self):
        """Test error handling when the module ID is unknown."""
        with self.assertRaises(ValueError):
            self.engine.choose_next_questions(TEST_USERNAME, 9999, target_count=10)


# --- Learning Path Generator Tests ---

class TestLearningPathGenerator(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(':memory:')
        setup_in_memory_db(self.conn)
        self.db_patch = patch('app.DBHelper.get_conn', return_value=self.conn)
        self.db_patch.start()

        self.kg = KnowledgeGraph()
        self.adaptive_engine = AdaptiveEngine(kg=self.kg)
        self.generator = LearningPathGenerator(kg=self.kg, adaptive_engine=self.adaptive_engine)

    def tearDown(self):
        self.conn.close()
        self.db_patch.stop()

    def test_generate_path_with_error(self):
        """Test path generation when an error is logged."""
        # 1. Manually insert error history for a core concept
        error_history = [{
            "qid": "Q9901",
            "concept": "addition within 100",
            "user_answer": "9",
            "correct_answer": "7",
            "score": 0.0
        }]
        mastery = self.adaptive_engine.calculate_mastery(TEST_USERNAME)
        self.conn.cursor().execute(
            "INSERT INTO user_mastery (username, mastery_json, error_history) VALUES (?, ?, ?)",
            (TEST_USERNAME, json.dumps(dict(mastery)), json.dumps(error_history))
        )
        self.conn.commit()

        # 2. Generate path
        path = self.generator.generate_path(TEST_USERNAME)
        self.assertEqual(len(path), 1)
        self.assertIn("Fix Your Mistake:", path[0]["stage"])
        self.assertEqual(path[0]["related_error"]["question"], TEST_QUESTION_1['text'])
        
        # 3. Verify path was saved
        c = self.conn.cursor()
        c.execute("SELECT path_json FROM learning_paths WHERE username=?", (TEST_USERNAME,))
        self.assertIsNotNone(c.fetchone())


# --- Flask Route Tests ---

class TestFlaskRoutes(unittest.TestCase):
    def setUp(self):
        self.app = app.test_client()
        self.app.testing = True

        self.conn = sqlite3.connect(':memory:')
        setup_in_memory_db(self.conn)
        self.db_patch = patch('app.DBHelper.get_conn', return_value=self.conn)
        self.db_patch.start()
        
        # Mock matplotlib for the /report route to prevent file I/O
        self.mpl_patch = patch('app.plt.savefig', MagicMock())
        self.mpl_patch.start()

    def tearDown(self):
        self.conn.close()
        self.db_patch.stop()
        self.mpl_patch.stop()

    def test_index_route(self):
        """Test the homepage loads module titles."""
        response = self.app.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertIn(TEST_ASSIGNMENT_TITLE.encode(), response.data)

    def test_enter_username_route(self):
        """Test the username entry page loads the correct module context."""
        response = self.app.get(f'/enter-username?module_id={TEST_ASSIGNMENT_ID}')
        self.assertEqual(response.status_code, 200)
        self.assertIn(TEST_ASSIGNMENT_TITLE.encode(), response.data)

    def test_quiz_route_loads_questions(self):
        """Test the quiz page loads and displays question text."""
        response = self.app.get(f'/quiz?username={TEST_USERNAME}&module_id={TEST_ASSIGNMENT_ID}')
        self.assertEqual(response.status_code, 200)
        self.assertIn(TEST_USERNAME.encode(), response.data)
        # Check for one of the known question texts
        self.assertIn(TEST_QUESTION_1['text'].encode(), response.data)

    def test_submit_route_correct_answer_updates_mastery(self):
        """Test correct submission and score calculation (1.0)."""
        form_data = {
            'username': TEST_USERNAME,
            'module_id': str(TEST_ASSIGNMENT_ID),
            'Q9901': TEST_QUESTION_1['answer'], # Correct Answer
            'Q9900': '7', # Also correct
            # ... and 8 more questions answered correctly
        }
        # Populate all 10 dynamically generated questions in the form data
        for i in range(10):
            form_data[f'Q{TEST_ASSIGNMENT_ID:02}{i:02}'] = TEST_QUESTION_1['answer']
        
        response = self.app.post('/submit', data=form_data, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Your Score: 1.0", response.data)

        # Verify mastery update (mastery must be > initial 0.4)
        c = self.conn.cursor()
        c.execute("SELECT mastery_json FROM user_mastery WHERE username=?", (TEST_USERNAME,))
        mastery = json.loads(c.fetchone()[0])
        self.assertGreater(mastery["addition within 100"], 0.4)
    
    def test_submit_route_incorrect_answer_logs_error(self):
        """Test incorrect submission logs an error in user_mastery table."""
        form_data = {
            'username': TEST_USERNAME,
            'module_id': str(TEST_ASSIGNMENT_ID),
            'Q9901': "Wrong Answer", # Incorrect Answer
        }
        # Need to populate all 10 fields for the app logic to run correctly
        for i in range(10):
            form_data[f'Q{TEST_ASSIGNMENT_ID:02}{i:02}'] = '0' # Fill others with dummy data
        
        self.app.post('/submit', data=form_data) 

        # Verify error history was saved
        c = self.conn.cursor()
        c.execute("SELECT error_history FROM user_mastery WHERE username=?", (TEST_USERNAME,))
        errors = json.loads(c.fetchone()[0])
        
        q_error = [e for e in errors if e.get("qid") == "Q9901"]
        self.assertTrue(len(q_error) > 0)
        self.assertEqual(q_error[0]["user_answer"], "wrong answer")
    
    def test_learning_path_route(self):
        """Test the learning path page (requires error history)."""
        # First, log an error
        self.test_submit_route_incorrect_answer_logs_error()

        response = self.app.get(f'/learning-path?username={TEST_USERNAME}')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Your Learning Path", response.data)
        # Should show a remediation stage based on the error
        self.assertIn(b"Fix Your Mistake:", response.data)

    def test_report_route(self):
        """Test the report page loads history and generates a chart (mocking chart save)."""
        # First, log a submission
        self.test_submit_route_correct_answer_updates_mastery()

        response = self.app.get(f'/report?username={TEST_USERNAME}')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Quiz History", response.data)
        self.assertIn(b"Concept Mastery Report", response.data)
        # Check that the plotting function was called
        self.assertTrue(self.mpl_patch.temp_original.called)
        
        
if __name__ == '__main__':
    # Initializing the database is not strictly necessary here since the tests use :memory:
    # but for completeness or if run outside of IDE, it can be useful.
    # DBHelper.init_db() 
    unittest.main()