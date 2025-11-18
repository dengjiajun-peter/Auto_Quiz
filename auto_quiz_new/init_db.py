import sqlite3
import json

# -------------------------- 1. Connect to Database (No Lock Risk) --------------------------
conn = sqlite3.connect("intelligent_tutoring.db")
c = conn.cursor()

# -------------------------- 2. Clear & Recreate Tables (Safety First) --------------------------
# Drop tables to avoid duplicates (simple logic)
for table in ["questions", "assignments", "submissions", "user_mastery", "learning_paths"]:
    c.execute(f"DROP TABLE IF EXISTS {table}")

# Create assignments table (modules)
c.execute('''CREATE TABLE IF NOT EXISTS assignments
             (
                 id
                 INTEGER
                 PRIMARY
                 KEY
                 AUTOINCREMENT,
                 title
                 TEXT
                 NOT
                 NULL -- Module name (English, simple)
             )''')

# Create questions table (simplified schema)
c.execute('''CREATE TABLE IF NOT EXISTS questions
(
    id
    INTEGER
    PRIMARY
    KEY
    AUTOINCREMENT,
    qid
    TEXT
    UNIQUE
    NOT
    NULL, -- Simple ID (e.g., AS01)
    assignment_id
    INTEGER
    NOT
    NULL,
    qtype
    TEXT
    NOT
    NULL, -- Only mcq/judge/blank (no complex types)
    text
    TEXT
    NOT
    NULL, -- Easy 1st-grade question text
    options
    TEXT, -- JSON for MCQ (empty for others)
    answer
    TEXT
    NOT
    NULL, -- Simple answer (no special chars)
    concepts
    TEXT
    NOT
    NULL, -- Basic concepts (JSON)
    difficulty
    INTEGER
    NOT
    NULL
    DEFAULT
    1,    -- All easy (1)
    FOREIGN
    KEY
             (
    assignment_id
             ) REFERENCES assignments
             (
                 id
             )
    )''')

# Create helper tables (for app.py compatibility)
c.execute('''CREATE TABLE IF NOT EXISTS user_mastery
             (
                 id
                 INTEGER
                 PRIMARY
                 KEY
                 AUTOINCREMENT,
                 username
                 TEXT
                 UNIQUE
                 NOT
                 NULL,
                 mastery_json
                 TEXT
                 NOT
                 NULL
                 DEFAULT
                 '{}',
                 error_history
                 TEXT
                 NOT
                 NULL
                 DEFAULT
                 '[]',
                 learning_behavior
                 TEXT
                 NOT
                 NULL
                 DEFAULT
                 '{}'
             )''')

c.execute('''CREATE TABLE IF NOT EXISTS submissions
             (
                 id
                 INTEGER
                 PRIMARY
                 KEY
                 AUTOINCREMENT,
                 username
                 TEXT
                 NOT
                 NULL,
                 assignment_id
                 INTEGER
                 NOT
                 NULL,
                 score
                 REAL
                 NOT
                 NULL,
                 total
                 INTEGER
                 NOT
                 NULL,
                 date
                 TIMESTAMP
                 DEFAULT
                 CURRENT_TIMESTAMP
             )''')

c.execute('''CREATE TABLE IF NOT EXISTS learning_paths
             (
                 id
                 INTEGER
                 PRIMARY
                 KEY
                 AUTOINCREMENT,
                 username
                 TEXT
                 NOT
                 NULL,
                 path_json
                 TEXT
                 NOT
                 NULL
                 DEFAULT
                 '[]',
                 created_at
                 TIMESTAMP
                 DEFAULT
                 CURRENT_TIMESTAMP,
                 updated_at
                 TIMESTAMP
                 DEFAULT
                 CURRENT_TIMESTAMP
             )''')

# -------------------------- 3. Create 3 Easy Modules --------------------------
modules = [
    ("Addition & Subtraction (1-20)", "AS"),  # Simplify to 1-20 (no carry/borrow)
    ("Multiplication Tables (2-5)", "MD"),  # Only 2-5 tables (easy for 1st grade)
    ("Fraction Recognition (1/2, 1/3)", "FR")  # Only basic fractions
]
module_ids = {}
for title, prefix in modules:
    c.execute("INSERT INTO assignments (title) VALUES (?)", (title,))
    module_ids[prefix] = c.lastrowid
print("✅ 3 easy modules created!")

# -------------------------- 4. Module 1: Addition & Subtraction (1-20) - 30 Easy Questions --------------------------
as_questions = [
    # 1-10: MCQ (no carry/borrow, sum/diff ≤20)
    {"qid": "AS01", "qtype": "mcq", "text": "What is 5 + 3?", "options": json.dumps(["8", "7", "9", "6"]),
     "answer": "8", "concepts": json.dumps(["addition (1-20)"])},
    {"qid": "AS02", "qtype": "mcq", "text": "What is 10 + 4?", "options": json.dumps(["14", "13", "15", "12"]),
     "answer": "14", "concepts": json.dumps(["addition (1-20)"])},
    {"qid": "AS03", "qtype": "mcq", "text": "What is 12 - 2?", "options": json.dumps(["10", "9", "11", "8"]),
     "answer": "10", "concepts": json.dumps(["subtraction (1-20)"])},
    {"qid": "AS04", "qtype": "mcq", "text": "What is 8 + 2?", "options": json.dumps(["10", "9", "11", "7"]),
     "answer": "10", "concepts": json.dumps(["addition (1-20)"])},
    {"qid": "AS05", "qtype": "mcq", "text": "What is 15 - 5?", "options": json.dumps(["10", "9", "11", "8"]),
     "answer": "10", "concepts": json.dumps(["subtraction (1-20)"])},
    {"qid": "AS06", "qtype": "mcq", "text": "What is 3 + 7?", "options": json.dumps(["10", "9", "11", "8"]),
     "answer": "10", "concepts": json.dumps(["addition (1-20)"])},
    {"qid": "AS07", "qtype": "mcq", "text": "What is 18 - 6?", "options": json.dumps(["12", "11", "13", "10"]),
     "answer": "12", "concepts": json.dumps(["subtraction (1-20)"])},
    {"qid": "AS08", "qtype": "mcq", "text": "What is 6 + 4?", "options": json.dumps(["10", "9", "11", "8"]),
     "answer": "10", "concepts": json.dumps(["addition (1-20)"])},
    {"qid": "AS09", "qtype": "mcq", "text": "What is 14 - 3?", "options": json.dumps(["11", "10", "12", "9"]),
     "answer": "11", "concepts": json.dumps(["subtraction (1-20)"])},
    {"qid": "AS10", "qtype": "mcq", "text": "What is 9 + 1?", "options": json.dumps(["10", "9", "11", "8"]),
     "answer": "10", "concepts": json.dumps(["addition (1-20)"])},

    # 11-20: Judge (simple true/false)
    {"qid": "AS11", "qtype": "judge", "text": "5 + 5 = 10 (True/False)", "options": json.dumps([]), "answer": "true",
     "concepts": json.dumps(["addition (1-20)"])},
    {"qid": "AS12", "qtype": "judge", "text": "10 - 3 = 8 (True/False)", "options": json.dumps([]), "answer": "false",
     "concepts": json.dumps(["subtraction (1-20)"])},
    {"qid": "AS13", "qtype": "judge", "text": "7 + 2 = 9 (True/False)", "options": json.dumps([]), "answer": "true",
     "concepts": json.dumps(["addition (1-20)"])},
    {"qid": "AS14", "qtype": "judge", "text": "12 - 4 = 7 (True/False)", "options": json.dumps([]), "answer": "false",
     "concepts": json.dumps(["subtraction (1-20)"])},
    {"qid": "AS15", "qtype": "judge", "text": "4 + 6 = 10 (True/False)", "options": json.dumps([]), "answer": "true",
     "concepts": json.dumps(["addition (1-20)"])},
    {"qid": "AS16", "qtype": "judge", "text": "15 - 7 = 8 (True/False)", "options": json.dumps([]), "answer": "true",
     "concepts": json.dumps(["subtraction (1-20)"])},
    {"qid": "AS17", "qtype": "judge", "text": "2 + 8 = 9 (True/False)", "options": json.dumps([]), "answer": "false",
     "concepts": json.dumps(["addition (1-20)"])},
    {"qid": "AS18", "qtype": "judge", "text": "11 - 1 = 10 (True/False)", "options": json.dumps([]), "answer": "true",
     "concepts": json.dumps(["subtraction (1-20)"])},
    {"qid": "AS19", "qtype": "judge", "text": "3 + 9 = 11 (True/False)", "options": json.dumps([]), "answer": "false",
     "concepts": json.dumps(["addition (1-20)"])},
    {"qid": "AS20", "qtype": "judge", "text": "16 - 6 = 10 (True/False)", "options": json.dumps([]), "answer": "true",
     "concepts": json.dumps(["subtraction (1-20)"])},

    # 21-30: Blank (simple input)
    {"qid": "AS21", "qtype": "blank", "text": "What is 2 + 3? (Enter number)", "options": json.dumps([]), "answer": "5",
     "concepts": json.dumps(["addition (1-20)"])},
    {"qid": "AS22", "qtype": "blank", "text": "What is 10 - 2? (Enter number)", "options": json.dumps([]),
     "answer": "8", "concepts": json.dumps(["subtraction (1-20)"])},
    {"qid": "AS23", "qtype": "blank", "text": "What is 6 + 4? (Enter number)", "options": json.dumps([]),
     "answer": "10", "concepts": json.dumps(["addition (1-20)"])},
    {"qid": "AS24", "qtype": "blank", "text": "What is 14 - 4? (Enter number)", "options": json.dumps([]),
     "answer": "10", "concepts": json.dumps(["subtraction (1-20)"])},
    {"qid": "AS25", "qtype": "blank", "text": "What is 1 + 9? (Enter number)", "options": json.dumps([]),
     "answer": "10", "concepts": json.dumps(["addition (1-20)"])},
    {"qid": "AS26", "qtype": "blank", "text": "What is 13 - 3? (Enter number)", "options": json.dumps([]),
     "answer": "10", "concepts": json.dumps(["subtraction (1-20)"])},
    {"qid": "AS27", "qtype": "blank", "text": "What is 4 + 5? (Enter number)", "options": json.dumps([]), "answer": "9",
     "concepts": json.dumps(["addition (1-20)"])},
    {"qid": "AS28", "qtype": "blank", "text": "What is 17 - 7? (Enter number)", "options": json.dumps([]),
     "answer": "10", "concepts": json.dumps(["subtraction (1-20)"])},
    {"qid": "AS29", "qtype": "blank", "text": "What is 8 + 1? (Enter number)", "options": json.dumps([]), "answer": "9",
     "concepts": json.dumps(["addition (1-20)"])},
    {"qid": "AS30", "qtype": "blank", "text": "What is 19 - 9? (Enter number)", "options": json.dumps([]),
     "answer": "10", "concepts": json.dumps(["subtraction (1-20)"])}
]

# -------------------------- 5. Module 2: Multiplication Tables (2-5) - 30 Easy Questions --------------------------
md_questions = [
    # 1-10: MCQ (2-5 tables only)
    {"qid": "MD01", "qtype": "mcq", "text": "What is 2 × 2?", "options": json.dumps(["4", "5", "3", "6"]),
     "answer": "4", "concepts": json.dumps(["multiplication (2x)"])},
    {"qid": "MD02", "qtype": "mcq", "text": "What is 3 × 2?", "options": json.dumps(["6", "5", "7", "8"]),
     "answer": "6", "concepts": json.dumps(["multiplication (3x)"])},
    {"qid": "MD03", "qtype": "mcq", "text": "What is 4 × 1?", "options": json.dumps(["4", "5", "3", "6"]),
     "answer": "4", "concepts": json.dumps(["multiplication (4x)"])},
    {"qid": "MD04", "qtype": "mcq", "text": "What is 5 × 2?", "options": json.dumps(["10", "9", "11", "8"]),
     "answer": "10", "concepts": json.dumps(["multiplication (5x)"])},
    {"qid": "MD05", "qtype": "mcq", "text": "What is 2 × 3?", "options": json.dumps(["6", "5", "7", "8"]),
     "answer": "6", "concepts": json.dumps(["multiplication (2x)"])},
    {"qid": "MD06", "qtype": "mcq", "text": "What is 3 × 3?", "options": json.dumps(["9", "8", "10", "7"]),
     "answer": "9", "concepts": json.dumps(["multiplication (3x)"])},
    {"qid": "MD07", "qtype": "mcq", "text": "What is 4 × 2?", "options": json.dumps(["8", "7", "9", "6"]),
     "answer": "8", "concepts": json.dumps(["multiplication (4x)"])},
    {"qid": "MD08", "qtype": "mcq", "text": "What is 5 × 1?", "options": json.dumps(["5", "4", "6", "3"]),
     "answer": "5", "concepts": json.dumps(["multiplication (5x)"])},
    {"qid": "MD09", "qtype": "mcq", "text": "What is 2 × 4?", "options": json.dumps(["8", "7", "9", "6"]),
     "answer": "8", "concepts": json.dumps(["multiplication (2x)"])},
    {"qid": "MD10", "qtype": "mcq", "text": "What is 3 × 4?", "options": json.dumps(["12", "11", "13", "10"]),
     "answer": "12", "concepts": json.dumps(["multiplication (3x)"])},

    # 11-20: Judge (simple true/false)
    {"qid": "MD11", "qtype": "judge", "text": "2 × 5 = 10 (True/False)", "options": json.dumps([]), "answer": "true",
     "concepts": json.dumps(["multiplication (2x)"])},
    {"qid": "MD12", "qtype": "judge", "text": "3 × 1 = 4 (True/False)", "options": json.dumps([]), "answer": "false",
     "concepts": json.dumps(["multiplication (3x)"])},
    {"qid": "MD13", "qtype": "judge", "text": "4 × 3 = 12 (True/False)", "options": json.dumps([]), "answer": "true",
     "concepts": json.dumps(["multiplication (4x)"])},
    {"qid": "MD14", "qtype": "judge", "text": "5 × 3 = 14 (True/False)", "options": json.dumps([]), "answer": "false",
     "concepts": json.dumps(["multiplication (5x)"])},
    {"qid": "MD15", "qtype": "judge", "text": "2 × 1 = 2 (True/False)", "options": json.dumps([]), "answer": "true",
     "concepts": json.dumps(["multiplication (2x)"])},
    {"qid": "MD16", "qtype": "judge", "text": "3 × 5 = 15 (True/False)", "options": json.dumps([]), "answer": "true",
     "concepts": json.dumps(["multiplication (3x)"])},
    {"qid": "MD17", "qtype": "judge", "text": "4 × 4 = 15 (True/False)", "options": json.dumps([]), "answer": "false",
     "concepts": json.dumps(["multiplication (4x)"])},
    {"qid": "MD18", "qtype": "judge", "text": "5 × 4 = 20 (True/False)", "options": json.dumps([]), "answer": "true",
     "concepts": json.dumps(["multiplication (5x)"])},
    {"qid": "MD19", "qtype": "judge", "text": "2 × 6 = 11 (True/False)", "options": json.dumps([]), "answer": "false",
     "concepts": json.dumps(["multiplication (2x)"])},
    {"qid": "MD20", "qtype": "judge", "text": "3 × 2 = 6 (True/False)", "options": json.dumps([]), "answer": "true",
     "concepts": json.dumps(["multiplication (3x)"])},

    # 21-30: Blank (simple input)
    {"qid": "MD21", "qtype": "blank", "text": "What is 2 × 1? (Enter number)", "options": json.dumps([]), "answer": "2",
     "concepts": json.dumps(["multiplication (2x)"])},
    {"qid": "MD22", "qtype": "blank", "text": "What is 3 × 1? (Enter number)", "options": json.dumps([]), "answer": "3",
     "concepts": json.dumps(["multiplication (3x)"])},
    {"qid": "MD23", "qtype": "blank", "text": "What is 4 × 1? (Enter number)", "options": json.dumps([]), "answer": "4",
     "concepts": json.dumps(["multiplication (4x)"])},
    {"qid": "MD24", "qtype": "blank", "text": "What is 5 × 2? (Enter number)", "options": json.dumps([]),
     "answer": "10", "concepts": json.dumps(["multiplication (5x)"])},
    {"qid": "MD25", "qtype": "blank", "text": "What is 2 × 3? (Enter number)", "options": json.dumps([]), "answer": "6",
     "concepts": json.dumps(["multiplication (2x)"])},
    {"qid": "MD26", "qtype": "blank", "text": "What is 3 × 4? (Enter number)", "options": json.dumps([]),
     "answer": "12", "concepts": json.dumps(["multiplication (3x)"])},
    {"qid": "MD27", "qtype": "blank", "text": "What is 4 × 2? (Enter number)", "options": json.dumps([]), "answer": "8",
     "concepts": json.dumps(["multiplication (4x)"])},
    {"qid": "MD28", "qtype": "blank", "text": "What is 5 × 3? (Enter number)", "options": json.dumps([]),
     "answer": "15", "concepts": json.dumps(["multiplication (5x)"])},
    {"qid": "MD29", "qtype": "blank", "text": "What is 2 × 5? (Enter number)", "options": json.dumps([]),
     "answer": "10", "concepts": json.dumps(["multiplication (2x)"])},
    {"qid": "MD30", "qtype": "blank", "text": "What is 3 × 5? (Enter number)", "options": json.dumps([]),
     "answer": "15", "concepts": json.dumps(["multiplication (3x)"])}
]

# -------------------------- 6. Module 3: Fraction Recognition (1/2, 1/3) - 30 Easy Questions --------------------------
fr_questions = [
    # 1-10: MCQ (only 1/2, 1/3, 1/4)
    {"qid": "FR01", "qtype": "mcq", "text": "1 slice of pizza cut into 2 parts: what fraction?",
     "options": json.dumps(["1/2", "1/3", "1/4", "2/1"]), "answer": "1/2",
     "concepts": json.dumps(["fraction recognition (1/2)"])},
    {"qid": "FR02", "qtype": "mcq", "text": "1 piece of cake cut into 3 parts: what fraction?",
     "options": json.dumps(["1/3", "1/2", "1/4", "3/1"]), "answer": "1/3",
     "concepts": json.dumps(["fraction recognition (1/3)"])},
    {"qid": "FR03", "qtype": "mcq", "text": "Which is 1/2 of 4?", "options": json.dumps(["2", "3", "1", "4"]),
     "answer": "2", "concepts": json.dumps(["fraction (1/2) application"])},
    {"qid": "FR04", "qtype": "mcq", "text": "Which is 1/3 of 3?", "options": json.dumps(["1", "2", "3", "0"]),
     "answer": "1", "concepts": json.dumps(["fraction (1/3) application"])},
    {"qid": "FR05", "qtype": "mcq", "text": "1 slice of pie cut into 4 parts: what fraction?",
     "options": json.dumps(["1/4", "1/2", "1/3", "4/1"]), "answer": "1/4",
     "concepts": json.dumps(["fraction recognition (1/4)"])},
    {"qid": "FR06", "qtype": "mcq", "text": "Which is 1/2 of 6?", "options": json.dumps(["3", "4", "2", "5"]),
     "answer": "3", "concepts": json.dumps(["fraction (1/2) application"])},
    {"qid": "FR07", "qtype": "mcq", "text": "Which is 1/3 of 6?", "options": json.dumps(["2", "3", "1", "4"]),
     "answer": "2", "concepts": json.dumps(["fraction (1/3) application"])},
    {"qid": "FR08", "qtype": "mcq", "text": "1 part of 2 equal parts: what fraction?",
     "options": json.dumps(["1/2", "1/3", "1/4", "2/2"]), "answer": "1/2",
     "concepts": json.dumps(["fraction recognition (1/2)"])},
    {"qid": "FR09", "qtype": "mcq", "text": "1 part of 3 equal parts: what fraction?",
     "options": json.dumps(["1/3", "1/2", "1/4", "3/3"]), "answer": "1/3",
     "concepts": json.dumps(["fraction recognition (1/3)"])},
    {"qid": "FR10", "qtype": "mcq", "text": "Which is 1/2 of 8?", "options": json.dumps(["4", "5", "3", "6"]),
     "answer": "4", "concepts": json.dumps(["fraction (1/2) application"])},

    # 11-20: Judge (simple true/false)
    {"qid": "FR11", "qtype": "judge", "text": "1/2 of 2 is 1 (True/False)", "options": json.dumps([]), "answer": "true",
     "concepts": json.dumps(["fraction (1/2) application"])},
    {"qid": "FR12", "qtype": "judge", "text": "1/3 of 9 is 4 (True/False)", "options": json.dumps([]),
     "answer": "false", "concepts": json.dumps(["fraction (1/3) application"])},
    {"qid": "FR13", "qtype": "judge", "text": "1/2 means 1 part out of 2 (True/False)", "options": json.dumps([]),
     "answer": "true", "concepts": json.dumps(["fraction recognition (1/2)"])},
    {"qid": "FR14", "qtype": "judge", "text": "1/3 means 3 parts out of 1 (True/False)", "options": json.dumps([]),
     "answer": "false", "concepts": json.dumps(["fraction recognition (1/3)"])},
    {"qid": "FR15", "qtype": "judge", "text": "1/2 of 10 is 5 (True/False)", "options": json.dumps([]),
     "answer": "true", "concepts": json.dumps(["fraction (1/2) application"])},
    {"qid": "FR16", "qtype": "judge", "text": "1/3 of 12 is 3 (True/False)", "options": json.dumps([]),
     "answer": "false", "concepts": json.dumps(["fraction (1/3) application"])},
    {"qid": "FR17", "qtype": "judge", "text": "A pizza cut into 2 parts: each is 1/2 (True/False)",
     "options": json.dumps([]), "answer": "true", "concepts": json.dumps(["fraction recognition (1/2)"])},
    {"qid": "FR18", "qtype": "judge", "text": "A cake cut into 3 parts: each is 1/2 (True/False)",
     "options": json.dumps([]), "answer": "false", "concepts": json.dumps(["fraction recognition (1/3)"])},
    {"qid": "FR19", "qtype": "judge", "text": "1/2 of 6 is 3 (True/False)", "options": json.dumps([]), "answer": "true",
     "concepts": json.dumps(["fraction (1/2) application"])},
    {"qid": "FR20", "qtype": "judge", "text": "1/3 of 3 is 2 (True/False)", "options": json.dumps([]),
     "answer": "false", "concepts": json.dumps(["fraction (1/3) application"])},

    # 21-30: Blank (simple input)
    {"qid": "FR21", "qtype": "blank", "text": "1 part of 2 equal parts: what fraction? (e.g., 1/2)",
     "options": json.dumps([]), "answer": "1/2", "concepts": json.dumps(["fraction recognition (1/2)"])},
    {"qid": "FR22", "qtype": "blank", "text": "1 part of 3 equal parts: what fraction? (e.g., 1/2)",
     "options": json.dumps([]), "answer": "1/3", "concepts": json.dumps(["fraction recognition (1/3)"])},
    {"qid": "FR23", "qtype": "blank", "text": "What is 1/2 of 4? (Enter number)", "options": json.dumps([]),
     "answer": "2", "concepts": json.dumps(["fraction (1/2) application"])},
    {"qid": "FR24", "qtype": "blank", "text": "What is 1/3 of 6? (Enter number)", "options": json.dumps([]),
     "answer": "2", "concepts": json.dumps(["fraction (1/3) application"])},
    {"qid": "FR25", "qtype": "blank", "text": "1 part of 4 equal parts: what fraction? (e.g., 1/2)",
     "options": json.dumps([]), "answer": "1/4", "concepts": json.dumps(["fraction recognition (1/4)"])},
    {"qid": "FR26", "qtype": "blank", "text": "What is 1/2 of 8? (Enter number)", "options": json.dumps([]),
     "answer": "4", "concepts": json.dumps(["fraction (1/2) application"])},
    {"qid": "FR27", "qtype": "blank", "text": "What is 1/3 of 9? (Enter number)", "options": json.dumps([]),
     "answer": "3", "concepts": json.dumps(["fraction (1/3) application"])},
    {"qid": "FR28", "qtype": "blank", "text": "A pizza cut into 2 parts: each part is ____ (e.g., 1/2)",
     "options": json.dumps([]), "answer": "1/2", "concepts": json.dumps(["fraction recognition (1/2)"])},
    {"qid": "FR29", "qtype": "blank", "text": "A cake cut into 3 parts: each part is ____ (e.g., 1/2)",
     "options": json.dumps([]), "answer": "1/3", "concepts": json.dumps(["fraction recognition (1/3)"])},
    {"qid": "FR30", "qtype": "blank", "text": "What is 1/2 of 10? (Enter number)", "options": json.dumps([]),
     "answer": "5", "concepts": json.dumps(["fraction (1/2) application"])}
]

# -------------------------- 7. Insert Questions (No Loops = No Lock) --------------------------
# Insert AS module
for q in as_questions:
    c.execute('''INSERT INTO questions
                 (qid, assignment_id, qtype, text, options, answer, concepts, difficulty)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
              (q["qid"], module_ids["AS"], q["qtype"], q["text"], q["options"],
               q["answer"], q["concepts"], 1))  # All difficulty 1

# Insert MD module
for q in md_questions:
    c.execute('''INSERT INTO questions
                 (qid, assignment_id, qtype, text, options, answer, concepts, difficulty)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
              (q["qid"], module_ids["MD"], q["qtype"], q["text"], q["options"],
               q["answer"], q["concepts"], 1))

# Insert FR module
for q in fr_questions:
    c.execute('''INSERT INTO questions
                 (qid, assignment_id, qtype, text, options, answer, concepts, difficulty)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
              (q["qid"], module_ids["FR"], q["qtype"], q["text"], q["options"],
               q["answer"], q["concepts"], 1))

# -------------------------- 8. Finalize (Fast & Safe) --------------------------
conn.commit()
conn.close()
print("✅ All questions inserted! Total: 90 (3 modules × 30 easy questions)")
print("💡 No complex logic = No DB lock. Ready to use with app.py!")