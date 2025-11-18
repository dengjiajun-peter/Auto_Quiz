import os
import json
import random
import sqlite3
import numpy as np
from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, url_for
from collections import defaultdict
from typing import List, Dict, Tuple, Optional
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.cluster import DBSCAN
import networkx as nx
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from io import BytesIO
import base64
from datetime import datetime
# Load environment variables
load_dotenv()
app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev_key_for_1st_grade_math')
app.jinja_env.add_extension('jinja2.ext.do')


# -------------------------- Database Helper Class --------------------------
class DBHelper:
    @staticmethod
    def get_conn() -> sqlite3.Connection:
        conn = sqlite3.connect("intelligent_tutoring.db")
        # mark connections created by DBHelper so we only close those
        try:
            conn._created_by_dbhelper = True
        except Exception:
            pass
        return conn

    @staticmethod
    def init_db() -> None:
        """Initialize database (ensure tables exist)"""
        conn = DBHelper.get_conn()
        c = conn.cursor()
        # Create tables if missing (safety check)
        c.execute('''CREATE TABLE IF NOT EXISTS assignments
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL)''')
        c.execute('''CREATE TABLE IF NOT EXISTS questions
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      qid TEXT UNIQUE NOT NULL,
                      assignment_id INTEGER NOT NULL,
                      qtype TEXT NOT NULL,
                      text TEXT NOT NULL,
                      options TEXT,
                      answer TEXT NOT NULL,
                      concepts TEXT NOT NULL,
                      difficulty INTEGER NOT NULL,
                      FOREIGN KEY (assignment_id) REFERENCES assignments (id))''')
        c.execute('''CREATE TABLE IF NOT EXISTS submissions
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      username TEXT NOT NULL,
                      assignment_id INTEGER NOT NULL,
                      score REAL NOT NULL,
                      total INTEGER NOT NULL,
                      date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                      FOREIGN KEY (assignment_id) REFERENCES assignments (id))''')
        c.execute('''CREATE TABLE IF NOT EXISTS user_mastery
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      username TEXT UNIQUE NOT NULL,
                      mastery_json TEXT NOT NULL,
                      error_history TEXT NOT NULL DEFAULT '[]',
                      learning_behavior TEXT NOT NULL DEFAULT '{}')''')
        c.execute('''CREATE TABLE IF NOT EXISTS learning_paths
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      username TEXT NOT NULL,
                      path_json TEXT NOT NULL,
                      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                      updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        conn.commit()
        if getattr(conn, "_created_by_dbhelper", False):
            conn.close()
        print("Database initialized!")

    @staticmethod
    def get_assignment_title(assignment_id: int) -> str:
        """Get module title by ID"""
        conn = DBHelper.get_conn()
        c = conn.cursor()
        c.execute("SELECT title FROM assignments WHERE id = ?", (assignment_id,))
        row = c.fetchone()
        if getattr(conn, "_created_by_dbhelper", False):
            conn.close()
        return row[0] if row else "Unknown Module"


# -------------------------- Auto Grading Module --------------------------
class TextGrader:
    def __init__(self, ref_texts: List[str]) -> None:
        self.ref_texts = ref_texts
        self.vectorizer = TfidfVectorizer(min_df=1)
        self.vectorizer.fit(ref_texts)

    def tfidf_sim(self, a: str, b: str) -> float:
        """Calculate cosine similarity for text answers"""
        # Fit a local vectorizer on the two texts to ensure vocabulary includes their tokens
        try:
            vect = TfidfVectorizer(min_df=1)
            X = vect.fit_transform([a, b])
            return float(cosine_similarity(X[0], X[1])[0][0])
        except Exception:
            return 0.0

    def expand_refs(self, ref: str) -> List[str]:
        """Expand reference answers for better matching"""
        parts = [p.strip() for p in ref.replace(',', ',').split(',') if p.strip()]
        if len(parts) <= 1:
            return [ref]
        return [
            f"Key points: {', '.join(parts)}.",
            f"Required answer: {' '.join(parts)}",
            ', '.join(parts)
        ]

    def grade_short(self, student_text: str, ref: str) -> Tuple[float, Dict[str, List[str]]]:
        """Grade fill-in-the-blank or short answers"""
        student_lower = student_text.lower()
        key_points = [p.strip() for p in ref.replace(',', ',').split(',') if p.strip()]
        
        # For each key point, check if it appears in the student answer (substring or similarity)
        mastered = []
        missed = []
        for point in key_points:
            point_lower = point.lower()
            # Check for substring match (case-insensitive, space-insensitive)
            point_normalized = point_lower.replace(' ', '').replace('-', '')
            student_normalized = student_lower.replace(' ', '').replace('-', '')
            
            # Try substring match first (for keywords)
            if point_normalized in student_normalized or point_lower in student_lower:
                mastered.append(point)
            else:
                # Fallback to TFIDF similarity (flexible matching)
                sim = self.tfidf_sim(student_lower, point_lower)
                if sim >= 0.5:  # Threshold for 1st graders (more forgiving)
                    mastered.append(point)
                else:
                    missed.append(point)
        
        score = len(mastered) / len(key_points) if key_points else 0.0
        return float(max(0.0, min(1.0, score))), {"mastered": mastered, "missed": missed}


class AutoMarker:
    def __init__(self, grader: TextGrader) -> None:
        self.grader = grader

    def grade(self, question: Dict[str, any], user_answer: str) -> Tuple[float, Dict[str, List[str]]]:
        """Auto-grade based on question type"""
        qtype = question["qtype"]
        correct_answer = question["answer"].strip().lower()
        user_answer_clean = user_answer.strip().lower()
        #concepts = json.loads(question["concepts"])
        # F-FIX: The AdaptiveEngine already parsed this into a list.
        concepts = question["concepts"]  # <-- 直接赋值，因为它已经是列表了
        # 1. Judge (True/False)
        if qtype == "judge":
            is_correct = user_answer_clean == correct_answer
        # 2. MCQ (Multiple Choice)
        elif qtype == "mcq":
            is_correct = user_answer_clean == correct_answer
        # 3. Blank (Fill-in-the-blank)
        elif qtype == "blank":
            # Allow minor format variations (e.g., "3r2" vs "3 r 2")
            user_answer_clean = user_answer_clean.replace(' ', '')
            correct_answer = correct_answer.replace(' ', '')
            is_correct = user_answer_clean == correct_answer
        # 4. Short Answer (Not used in 1st-grade math, but kept for compatibility)
        else:
            return self.grader.grade_short(user_answer_clean, correct_answer)

        # Return score and mastery info
        mastered = concepts if is_correct else []
        missed = concepts if not is_correct else []
        return 1.0 if is_correct else 0.0, {"mastered": mastered, "missed": missed}


# -------------------------- Knowledge Graph Module --------------------------
class KnowledgeGraph:
    def __init__(self) -> None:
        self.graph = nx.Graph()
        self.concept_questions = defaultdict(list)
        self._build_graph()

    def _build_graph(self) -> None:
        """Build concept relationships for 1st-grade math"""
        # Predefined concept relations (English)
        relations: List[Tuple[str, str]] = [
            # AS Module
            ("addition within 100", "carry addition"),
            ("addition within 100", "addition word problems"),
            ("subtraction within 100", "borrowing subtraction"),
            ("subtraction within 100", "subtraction word problems"),
            # MD Module
            ("multiplication tables (2-9)", "multiplication within 100"),
            ("multiplication tables (2-9)", "multiplication word problems"),
            ("division without remainder", "division with remainder"),
            ("division without remainder", "division word problems"),
            ("addition within 100", "multiplication tables (2-9)"),  # Prerequisite
            # FR Module
            ("fraction recognition (1/2, 1/3, ..., 1/10)", "fraction comparison (same denominator)"),
            ("fraction recognition (1/2, 1/3, ..., 1/10)", "fraction addition (same denominator)"),
            ("fraction addition (same denominator)", "fraction subtraction (same denominator)"),
            ("addition within 100", "fraction addition (same denominator)")  # Prerequisite
        ]

        # Add nodes and edges
        for a, b in relations:
            self.graph.add_node(a)
            self.graph.add_node(b)
            self.graph.add_edge(a, b)

        # Link questions to concepts (from database)
        conn = DBHelper.get_conn()
        c = conn.cursor()
        c.execute("SELECT qid, concepts FROM questions")
        for qid, concepts_json in c.fetchall():
            try:
                concepts = json.loads(concepts_json)
            except Exception:
                concepts = []
            for cpt in concepts:
                self.concept_questions[cpt].append(qid)
        # Do not close the connection here; callers/tests may share the same connection.

    def get_related_concepts(self, concept: str) -> List[str]:
        """Get related concepts for a given concept"""
        return list(self.graph.neighbors(concept)) if concept in self.graph else []

    def get_related_questions(self, concepts: List[str]) -> List[str]:
        """Get questions related to a list of concepts"""
        related_qids = set()
        for cpt in concepts:
            related_qids.update(self.concept_questions.get(cpt, []))
            # Add questions from related concepts
            for related_cpt in self.get_related_concepts(cpt):
                related_qids.update(self.concept_questions.get(related_cpt, []))
        return list(related_qids)


# -------------------------- Adaptive Question Selection Module --------------------------
class AdaptiveEngine:
    def __init__(self, questions_or_kg: Optional[any] = None, kg: Optional[KnowledgeGraph] = None) -> None:
        """Adaptive engine initialization.
        Can be called as:
        - AdaptiveEngine(kg) for production (legacy) 
        - AdaptiveEngine(questions={...}) for tests with injected questions
        - AdaptiveEngine(questions={...}, kg=kg) for tests
        """
        # Detect if first arg is KnowledgeGraph (legacy) or dict (questions)
        if isinstance(questions_or_kg, KnowledgeGraph):
            # Legacy: AdaptiveEngine(kg) -> swap to kg mode
            self.kg = questions_or_kg
            questions = None
        else:
            # New: AdaptiveEngine(questions={...}, kg=...)
            questions = questions_or_kg
            self.kg = kg
        
        if questions is not None:
            # Normalize provided questions so that `concepts` is always a list
            def _normalize(q: Dict[str, any]) -> Dict[str, any]:
                q_copy = dict(q)
                c = q_copy.get("concepts", [])
                if isinstance(c, str):
                    try:
                        q_copy["concepts"] = json.loads(c)
                    except Exception:
                        q_copy["concepts"] = [c]
                else:
                    q_copy["concepts"] = c or []
                # Ensure options are lists
                opts = q_copy.get("options", [])
                if isinstance(opts, str):
                    try:
                        q_copy["options"] = json.loads(opts)
                    except Exception:
                        q_copy["options"] = []
                return q_copy

            self.question_cache: Dict[str, Dict[str, any]] = {
                qid: _normalize(q) for qid, q in questions.items()
            }
        else:
            # Load from database (production)
            self.question_cache: Dict[str, Dict[str, any]] = self._load_questions()

    def _load_questions(self) -> Dict[str, Dict[str, any]]:
        conn = DBHelper.get_conn()
        c = conn.cursor()
        c.execute('''SELECT qid,
                            qtype,
                            text,
                            options,
                            answer,
                            concepts,
                            difficulty,
                            assignment_id
                     FROM questions''')
        rows = c.fetchall()

        # Do not close connection here; tests may patch DBHelper.get_conn to reuse the same in-memory connection.

        return {
            row[0]: {
                "qid": row[0],
                "qtype": row[1],
                "text": row[2],
                "options": json.loads(row[3]) if row[3] else [],  # Keep options parsed (needed for MCQ)
                "answer": row[4],
                "concepts": json.loads(row[5]) if row[5] else [],
                "difficulty": row[6],
                "assignment_id": row[7]
            }
            for row in rows
        }

    def calculate_mastery(self, username: str) -> defaultdict[str, float]:
        """Calculate user's mastery of 1st-grade math concepts (0=low, 1=high)"""
        conn = DBHelper.get_conn()
        c = conn.cursor()
        c.execute("SELECT mastery_json FROM user_mastery WHERE username=?", (username,))
        row = c.fetchone()
        if getattr(conn, "_created_by_dbhelper", False):
            conn.close()

        if row and row[0]:
            return defaultdict(float, json.loads(row[0]))

        # Initial mastery (lower for harder concepts)
        init_mastery = defaultdict(float)
        # AS Module (easiest for 1st graders)
        init_mastery["addition within 100"] = 0.4
        init_mastery["carry addition"] = 0.3
        init_mastery["subtraction within 100"] = 0.35
        init_mastery["borrowing subtraction"] = 0.25
        init_mastery["addition word problems"] = 0.3
        init_mastery["subtraction word problems"] = 0.25
        # MD Module (moderate)
        init_mastery["multiplication tables (2-9)"] = 0.2
        init_mastery["multiplication within 100"] = 0.15
        init_mastery["division without remainder"] = 0.15
        init_mastery["division with remainder"] = 0.1
        init_mastery["multiplication word problems"] = 0.15
        init_mastery["division word problems"] = 0.1
        # FR Module (hardest)
        init_mastery["fraction recognition (1/2, 1/3, ..., 1/10)"] = 0.15
        init_mastery["fraction comparison (same denominator)"] = 0.1
        init_mastery["fraction addition (same denominator)"] = 0.1
        init_mastery["fraction subtraction (same denominator)"] = 0.05
        init_mastery["fraction word problems"] = 0.05
        return init_mastery

    def update_mastery(self, username: str, question: Dict[str, any], score: float) -> None:
        """Update user's mastery after answering a question"""
        current_mastery = self.calculate_mastery(username)
        concepts = question["concepts"]

        # Weighted update: 70% current mastery + 30% new score (gentle adjustment for kids)
        for concept in concepts:
            current_mastery[concept] = 0.7 * current_mastery[concept] + 0.3 * score

        # Save to database (upsert)
        conn = DBHelper.get_conn()
        c = conn.cursor()
        c.execute('''INSERT OR REPLACE INTO user_mastery
                     (username, mastery_json, error_history, learning_behavior)
                     VALUES (?, ?,
                             COALESCE((SELECT error_history FROM user_mastery WHERE username=?), '[]'),
                             COALESCE((SELECT learning_behavior FROM user_mastery WHERE username=?), '{}'))''',
                  (username, json.dumps(dict(current_mastery)), username, username))
        conn.commit()
        if getattr(conn, "_created_by_dbhelper", False):
            conn.close()

    def choose_next_questions(self, username: str, assignment_id: int, target_count: int = 10) -> List[Dict[str, any]]:
        """Randomly select 10 questions from the specified module (for 1st graders)"""
        # Step 1: Get all question IDs of the module
        module_qids = [
            qid for qid, q in self.question_cache.items()
            if q["assignment_id"] == assignment_id
        ]

        # Step 2: Shuffle and select 10 (ensure exactly 10 if module has ≥10 questions)
        if len(module_qids) < target_count:
            raise ValueError(f"Module has only {len(module_qids)} questions (needs ≥10)")
        random.shuffle(module_qids)
        selected_qids = module_qids[:target_count]

        # Step 3: Return full question details
        return [self.question_cache[qid] for qid in selected_qids]


# -------------------------- Personalized Learning Path Module --------------------------

# 依赖原系统的 DBHelper 和 KnowledgeGraph 类，确保保持兼容
# -------------------------- Personalized Learning Path Module --------------------------
class LearningPathGenerator:
    def __init__(self, kg: KnowledgeGraph, adaptive_engine: AdaptiveEngine) -> None:
        self.kg = kg
        self.adaptive_engine = adaptive_engine  # Access question details

    def load_user_data(self, username: str) -> Tuple[defaultdict[str, float], List[Dict[str, any]], Dict[str, any]]:
        """Load user's mastery, error history, and learning behavior"""
        conn = DBHelper.get_conn()
        c = conn.cursor()
        c.execute('''SELECT mastery_json, error_history, learning_behavior
                     FROM user_mastery WHERE username = ?''', (username,))
        row = c.fetchone()
        if getattr(conn, "_created_by_dbhelper", False):
            conn.close()
        mastery = defaultdict(float, json.loads(row[0])) if (row and row[0]) else defaultdict(float)
        error_history = json.loads(row[1]) if (row and row[1]) else []
        learning_behavior = json.loads(row[2]) if (row and row[2]) else {}
        return mastery, error_history, learning_behavior

    def generate_path(self, username: str) -> List[Dict[str, any]]:
        """Generate learning path based on INCORRECT QUESTIONS: concept + example for each error"""
        mastery, error_history, _ = self.load_user_data(username)
        learning_path: List[Dict[str, any]] = []

        # No errors? Return basic review path
        if not error_history:
            learning_path.append({
                "stage": "No Recent Errors!",
                "concepts": ["Basic Review"],
                "resources": [{
                    "type": "Fun Practice",
                    "title": "Keep Up the Good Work!",
                    "content": "You haven't made mistakes recently! Try reviewing key concepts with simple examples:\n1. Addition: 3 + 5 = 8 (3 toys + 5 toys = 8 toys)\n2. Multiplication: 2 × 4 = 8 (2 groups of 4 candies = 8 candies)\n3. Fraction: 1/2 of 6 = 3 (3 slices out of 6 equal pizza slices)"
                }],
                "difficulty": "Easy",
                "goal": "Maintain your great work!"
            })
            # Save path to database
            self._save_path(username, learning_path)
            return learning_path

        # Group errors by concept (avoid duplicates)
        concept_errors = defaultdict(list)
        for error in error_history:
            qid = error["qid"]
            question = self.adaptive_engine.question_cache.get(qid)
            if not question:
                continue
            # Parse concepts from question (support both JSON string and already-parsed list)
            raw_concepts = question.get("concepts", [])
            if isinstance(raw_concepts, str):
                try:
                    concepts = json.loads(raw_concepts)
                except Exception:
                    concepts = [raw_concepts]
            else:
                concepts = raw_concepts or []

            for concept in concepts:
                concept_errors[concept].append({
                    "qid": qid,
                    "question_text": question["text"],
                    "user_answer": error["user_answer"],
                    "correct_answer": error["correct_answer"]
                })

        # Create stage for each problematic concept
        for concept, errors in concept_errors.items():
            # Get 1 representative error (first one)
            sample_error = errors[0]
            learning_path.append({
                "stage": f"Fix Your Mistake: {concept}",
                "concepts": [concept],
                "related_error": {
                    "question": sample_error["question_text"],
                    "your_answer": sample_error["user_answer"],
                    "correct_answer": sample_error["correct_answer"]
                },
                "resources": [{
                    "type": "Concept + Simple Example",
                    "title": f"Learn {concept} Easily",
                    "content": f"📚 What is {concept}?\n{self._get_concept_explanation(concept)}\n\n✨ Example: {self._get_simple_example(concept)}\n\n💡 Tip: {self._get_kid_tip(concept)}"
                }],
                "difficulty": "Easy" if mastery.get(concept, 0.0) >= 0.3 else "Very Easy",
                "goal": f"Understand {concept} and avoid the same mistake next time!"
            })

        # Save path to database
        self._save_path(username, learning_path)
        return learning_path

    def _get_concept_explanation(self, concept: str) -> str:
        """Explain concept in simple English for 1st graders"""
        if "addition (1-20)" in concept:
            return "Adding two numbers between 1 and 20 to get a sum (e.g., 5 + 7 = 12)."
        elif "subtraction (1-20)" in concept:
            return "Taking one number away from another (between 1 and 20) to find the difference (e.g., 15 - 6 = 9)."
        elif "multiplication (2x)" in concept:
            return "Adding the number 2 repeatedly (e.g., 2 × 3 = 2 + 2 + 2 = 6)."
        elif "multiplication (3x)" in concept:
            return "Adding the number 3 repeatedly (e.g., 3 × 4 = 3 + 3 + 3 + 3 = 12)."
        elif "multiplication (4x)" in concept:
            return "Adding the number 4 repeatedly (e.g., 4 × 2 = 4 + 4 = 8)."
        elif "multiplication (5x)" in concept:
            return "Adding the number 5 repeatedly (e.g., 5 × 3 = 5 + 5 + 5 = 15)."
        elif "fraction recognition (1/2)" in concept:
            return "Recognizing that 1/2 means 1 equal part out of 2 total parts (e.g., half a pizza)."
        elif "fraction recognition (1/3)" in concept:
            return "Recognizing that 1/3 means 1 equal part out of 3 total parts (e.g., one slice of a 3-slice cake)."
        elif "fraction recognition (1/4)" in concept:
            return "Recognizing that 1/4 means 1 equal part out of 4 total parts (e.g., one piece of a 4-piece cookie)."
        elif "fraction (1/2) application" in concept:
            return "Finding half of a number by splitting it into two equal parts (e.g., 1/2 of 8 = 4)."
        elif "fraction (1/3) application" in concept:
            return "Finding one-third of a number by splitting it into three equal parts (e.g., 1/3 of 9 = 3)."
        else:
            return f"A basic math skill for 1st graders! {concept.replace('-', ' ')}."

    def _get_simple_example(self, concept: str) -> str:
        """Generate simple examples for 1st graders"""
        if "addition" in concept:
            return "7 + 4 = 11 (If you have 7 pencils and get 4 more, you have 11 total!)"
        elif "subtraction" in concept:
            return "13 - 5 = 8 (If you have 13 stickers and give 5 away, 8 are left!)"
        elif "multiplication (2x)" in concept:
            return "2 × 5 = 10 (2 hands with 5 fingers each = 10 fingers total)"
        elif "multiplication (3x)" in concept:
            return "3 × 3 = 9 (3 boxes with 3 crayons each = 9 crayons)"
        elif "multiplication (4x)" in concept:
            return "4 × 2 = 8 (4 toy cars with 2 wheels each = 8 wheels)"
        elif "multiplication (5x)" in concept:
            return "5 × 4 = 20 (5 days with 4 snacks each = 20 snacks)"
        elif "fraction recognition (1/2)" in concept:
            return "A pizza cut into 2 equal slices → each slice is 1/2 of the pizza"
        elif "fraction recognition (1/3)" in concept:
            return "A cake cut into 3 equal pieces → each piece is 1/3 of the cake"
        elif "fraction recognition (1/4)" in concept:
            return "A cookie cut into 4 equal parts → each part is 1/4 of the cookie"
        elif "fraction (1/2) application" in concept:
            return "1/2 of 6 = 3 (6 apples split between 2 kids → 3 apples each)"
        elif "fraction (1/3) application" in concept:
            return "1/3 of 12 = 4 (12 candies split between 3 friends → 4 candies each)"
        else:
            return "Ask your teacher for a fun example!"

    def _get_kid_tip(self, concept: str) -> str:
        """Generate simple tips for 1st graders"""
        if "addition" in concept:
            return "Count on your fingers! Start with the bigger number and add the smaller one."
        elif "subtraction" in concept:
            return "Count backwards! If you have 12 - 3, count 11, 10, 9 (that's 3 steps)."
        elif "multiplication" in concept:
            return "Sing a multiplication song! It makes remembering facts easier."
        elif "fraction" in concept:
            return "Draw a picture! Coloring the parts helps you see the fraction clearly."
        else:
            return "Practice 5 minutes every day—you'll get better!"

    def _save_path(self, username: str, path: List[Dict[str, any]]) -> None:
        """Helper: Save path to database"""
        conn = DBHelper.get_conn()
        c = conn.cursor()
        c.execute('''INSERT OR REPLACE INTO learning_paths
                     (username, path_json, updated_at)
                     VALUES (?, ?, CURRENT_TIMESTAMP)''',
                  (username, json.dumps(path)))
        conn.commit()
        if getattr(conn, "_created_by_dbhelper", False):
            conn.close()
# -------------------------- Flask Routes (English Interface) --------------------------
# Initialize core components
# Initialize core components
DBHelper.init_db()
kg = KnowledgeGraph()
# Reference texts for text grading (1st-grade math)
ref_texts: List[str] = [
    "Addition within 100: Adding two numbers that sum to less than 100, e.g., 25 + 30 = 55.",
    "Carry addition: Adding numbers where the ones place sums to 10 or more, e.g., 18 + 7 = 25 (carry 1 to tens place).",
    "Subtraction within 100: Subtracting two numbers where the result is positive, e.g., 40 - 15 = 25.",
    "Borrowing subtraction: Subtracting numbers where the ones place of the minuend is smaller, e.g., 32 - 5 = 27 (borrow 1 from tens place).",
    "Multiplication tables (2-9): The product of numbers 2 to 9, e.g., 3×4=12, 7×8=56.",
    "Division without remainder: Dividing a number into equal parts with no leftover, e.g., 12 ÷ 3 = 4.",
    "Division with remainder: Dividing a number into equal parts with leftover, e.g., 13 ÷ 3 = 4 with remainder 1 (written as 4r1).",
    "Fraction basics: 1/2 means one part out of two equal parts; same denominator fractions add by adding numerators, e.g., 1/4 + 2/4 = 3/4."
]
grader = TextGrader(ref_texts=ref_texts)
marker = AutoMarker(grader=grader)
adaptive_engine = AdaptiveEngine(kg=kg)
path_generator = LearningPathGenerator(kg=kg, adaptive_engine=adaptive_engine)  # Pass adaptive_engine

@app.route('/')
def index():
    """Homepage: Show 3 math modules"""
    conn = DBHelper.get_conn()
    c = conn.cursor()
    c.execute("SELECT id, title FROM assignments ORDER BY id")
    modules = c.fetchall()  # Modules: AS, MD, FR
    conn.close()
    return render_template('index.html', modules=modules)


@app.route('/enter-username')
def enter_username():
    """Page to enter username before starting a quiz"""
    module_id = request.args.get('module_id')
    if not module_id:
        return redirect(url_for('index'))
    # Get module title for display
    module_title = DBHelper.get_assignment_title(int(module_id))
    return render_template('enter_username.html', module_id=module_id, module_title=module_title)


@app.route('/quiz')
def quiz():
    """Quiz page: Show 10 random questions from the selected module"""
    username = request.args.get('username')
    module_id = request.args.get('module_id')
    if not username or not module_id:
        return redirect(url_for('index'))

    # Validate module ID
    try:
        module_id_int = int(module_id)
    except ValueError:
        return redirect(url_for('index'))

    # Get module title and 10 questions
    module_title = DBHelper.get_assignment_title(module_id_int)
    questions = adaptive_engine.choose_next_questions(username, module_id_int, target_count=10)

    return render_template(
        'quiz.html',
        username=username,
        module_id=module_id_int,
        module_title=module_title,
        questions=questions
    )


@app.route('/submit', methods=['POST'])
def submit():
    """Submit quiz answers, grade, and update user data"""
    username = request.form.get('username', 'Anonymous')
    module_id = request.form.get('module_id', '1')
    total = 0
    score_sum = 0.0
    details: List[Dict[str, any]] = []
    error_history: List[Dict[str, any]] = []

    # Validate module ID
    try:
        module_id_int = int(module_id)
    except ValueError:
        module_id_int = 1

    # Grade each question
    for qid, question in adaptive_engine.question_cache.items():
        if qid in request.form and question["assignment_id"] == module_id_int:
            user_answer = request.form.get(qid, '').strip()
            score, mastery_info = marker.grade(question, user_answer)

            # Update mastery
            adaptive_engine.update_mastery(username, question, score)

            # Record errors (score < 1.0)
            if score < 1.0:
                error_history.append({
                    "qid": qid,
                    "concept": question["concepts"][0],
                    "user_answer": user_answer,
                    "correct_answer": question["answer"],
                    "score": float(score)
                })

            # Collect details for result page
            details.append({
                "qid": qid,
                "text": question["text"],
                "user_answer": user_answer,
                "correct_answer": question["answer"],
                "score": round(score, 2),
                "mastered": mastery_info["mastered"],
                "missed": mastery_info["missed"]
            })

            total += 1
            score_sum += score

    # Save error history to database (upsert user_mastery if missing)
    conn = DBHelper.get_conn()
    c = conn.cursor()

    # Fetch existing mastery/error for this user
    c.execute("SELECT mastery_json, error_history FROM user_mastery WHERE username=?", (username,))
    row = c.fetchone()
    if row is None:
        # No existing record: create one with default mastery and the new errors
        default_mastery = dict(adaptive_engine.calculate_mastery(username))
        c.execute('''INSERT INTO user_mastery
                     (username, mastery_json, error_history, learning_behavior)
                     VALUES (?, ?, ?, ?)''', (username, json.dumps(default_mastery), json.dumps(error_history), '{}'))
    else:
        existing_errors = json.loads(row[1]) if (row and row[1]) else []
        existing_errors.extend(error_history)
        c.execute('''UPDATE user_mastery
                     SET error_history=?
                     WHERE username=?''', (json.dumps(existing_errors), username))

    # Save submission record
    c.execute('''INSERT INTO submissions
                 (username, assignment_id, score, total)
                 VALUES (?, ?, ?, ?)''', (username, module_id_int, score_sum, total))

    conn.commit()
    # Do not forcibly close a connection that tests may have provided
    try:
        conn.close()
    except Exception:
        pass

    # Redirect to result page
    return render_template(
        'result.html',
        username=username,
        score=round(score_sum, 2),
        total=total,
        details=details,
        module_id=module_id_int,
        module_title=DBHelper.get_assignment_title(module_id_int)
    )


@app.route('/learning-path')
def learning_path():
    """Show personalized learning path for the user"""
    username = request.args.get('username')
    if not username:
        return redirect(url_for('index'))

    # Generate or load learning path
    path = path_generator.generate_path(username)
    return render_template('learning_path.html', username=username, path=path)


@app.route('/report')
def report():
    """Show user's quiz history and mastery report"""
    username = request.args.get('username')
    if not username:
        return redirect(url_for('index'))

    conn = DBHelper.get_conn()
    c = conn.cursor()

    # 1. Get submission history
    c.execute('''SELECT a.title, s.score, s.total, s.date
                 FROM submissions s
                 JOIN assignments a ON s.assignment_id = a.id
                 WHERE s.username=?
                 ORDER BY s.date DESC''', (username,))
    submissions = c.fetchall()

    # 2. Get mastery data (formatted for display)
    c.execute("SELECT mastery_json FROM user_mastery WHERE username=?", (username,))
    row = c.fetchone()
    mastery_data = json.loads(row[0]) if (row and row[0]) else {}
    # Group mastery by module for clarity
    as_mastery = {k: v for k, v in mastery_data.items() if any(x in k for x in ["addition", "subtraction"])}
    md_mastery = {k: v for k, v in mastery_data.items() if any(x in k for x in ["multiplication", "division"])}
    fr_mastery = {k: v for k, v in mastery_data.items() if "fraction" in k}

    # 3. Generate score distribution chart (if submissions exist)
    img_base64 = ""
    if submissions:
        scores = [float(s[1]) for s in submissions]
        plt.figure(figsize=(6, 4))
        plt.hist(scores, bins=10, edgecolor='black', alpha=0.7, color='#FFD700')  # Gold color for kids
        plt.title(f"{username}'s Math Score Distribution")
        plt.xlabel(f"Score (Total: {submissions[0][2]} Questions)")
        plt.ylabel("Number of Quizzes")
        plt.grid(axis='y', linestyle='--', alpha=0.7)

        # Save chart as base64
        buffer = BytesIO()
        plt.savefig(buffer, format='png', dpi=150, bbox_inches='tight')
        buffer.seek(0)
        img_base64 = base64.b64encode(buffer.getvalue()).decode()
        plt.close()

    if getattr(conn, "_created_by_dbhelper", False):
        conn.close()

    return render_template(
        'report.html',
        username=username,
        submissions=submissions,
        as_mastery=as_mastery,
        md_mastery=md_mastery,
        fr_mastery=fr_mastery,
        img_base64=img_base64
    )


if __name__ == '__main__':
    # Create static folder for assets (if missing)
    os.makedirs('static', exist_ok=True)
    # Run Flask app (debug mode for development)
    app.run(debug=True, host='0.0.0.0', port=5003)