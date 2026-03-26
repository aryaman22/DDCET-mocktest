# DDCET Exam Portal

A robust, full-featured Mock Test Platform designed for the **Diploma to Degree Common Entrance Test (DDCET)**. This application provides a comprehensive environment for students to practice and take exams, while offering administrators powerful tools for question management, exam configuration, and performance analytics.

---

## 🚀 Tech Stack

- **Backend**: Python (Flask)
- **Database**: SQLite (Development) / PostgreSQL (Production) with SQLAlchemy ORM
- **Frontend**: HTML5, CSS3 (Vanilla), JavaScript (Vanilla)
- **Authentication**: Flask-Login with Bcrypt password hashing
- **Deployment**: Configured for Heroku/Vercel (via Gunicorn)

---

## ✨ Core Features

### 👤 Student Interface
- **Personalized Dashboard**: View available exams, practice sessions, and performance history.
- **Exam Mode**: 
    - Full-screen, timed environment.
    - Automatic submission on timer expiration or tab/browser exit.
    - Question palette for quick navigation and "Mark for Review" functionality.
- **Practice Mode**: 
    - Instant feedback on answers.
    - Topic-wise drilling.
    - Resume capability for active sessions.
- **Detailed Results**: Graphical analysis of topic-wise accuracy and section-wise performance.

### 🛠 Administrative Suite
- **Comprehensive Dashboard**: Real-time stats on question counts, active users, and recent exam attempts.
- **Question Bank Management**:
    - Organize questions into "Banks" (e.g., by Year or Subject).
    - Bulk upload questions via **CSV, JSON, or Excel (.xlsx)**.
    - Manual CRUD operations for individual questions.
- **Exam Configuration**:
    - Flexible rule engine: set duration, marks for correct/wrong answers, and section filters.
    - Support for "Bonus" questions (marked with 'X').
- **User Management**: Monitor student registration and manage access.
- **Analytics & Reporting**:
    - Daily attempt trends.
    - Hardest question identifier.
    - Topic-wise performance across all students.
    - Export attempt data to CSV.
- **Audit Logs**: Track all administrative actions for security and accountability.

---

## 🔒 Security & Anti-Cheating

- **Proctoring Logic (`exam.js`)**:
    - **Fullscreen Lock**: Detects and logs every time a student exits fullscreen mode.
    - **Tab Switching**: Monitors visibility changes and flags tab-switching events.
    - **Context Menu Disable**: Right-click is disabled to prevent easy inspection or copying.
- **Reliable Submission**:
    - Uses `navigator.sendBeacon()` to ensure answers are submitted even if the student closes the tab or the browser crashes.
    - Periodic auto-save every 30 seconds.

---

## 📊 Database Schema

### Models & Relationships
- **User**: Stores credentials, role (Admin/Student), and profile details (Enrollment No, Branch).
- **QuestionBank**: Container for questions; allows logical grouping.
- **Question**: Belongs to a Bank. Contains text, 4 options, correct answer, topic, and explanation.
- **ExamConfig**: Defines the rules for an exam or practice session (pool of banks, duration, marks).
- **TestAttempt**: Record of a completed/in-progress exam. Stores a JSON snapshot of the questions served and the student's choices.
- **PracticeSession**: Lightweight tracking for ongoing practice.
- **AdminLog**: Audit trail for admin actions.

---

## 🧠 Implementation Logic (For Reference)

If re-implementing this project in another language (e.g., Node.js, Go, or Java), follow these core logic patterns:

### 1. Scoring Formula
```python
score = (correct_count * marks_correct) - (wrong_count * marks_wrong) + (bonus_count * marks_correct)
```
*Note: Unattempted questions result in 0 marks.*

### 2. Question Selection
Questions are randomly sampled from the selected banks based on the `total_questions` limit in the `ExamConfig`. This ensures students get different sets from the same pool.

### 3. Reliable Exit Submission
Always use `sendBeacon` or a synchronous `POST` on the `pagehide` / `beforeunload` browser events to prevent data loss when a user leaves the page abruptly.

---

## 🛠 Setup & Installation

1. **Clone the repository**:
   ```bash
   git clone <repo-url>
   cd DDCET-PROJECT
   ```

2. **Set up Environment**:
   Create a `.env` file with:
   ```env
   SECRET_KEY=your_secret_key
   DATABASE_URL=sqlite:///ddcet.db
   ADMIN_DEFAULT_PASSWORD=admin_pass
   ```

3. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Initialize Database**:
   The app automatically creates tables and a default admin (`admin@ddcet.local`) on first run.

5. **Run Application**:
   ```bash
   python app.py
   ```
