"""
helpers.py — Grade lookup helper
"""
from models import Grade


def calculate_grade(score):
    grade = Grade.query.filter(
        Grade.min_score <= score,
        Grade.max_score >= score,
    ).first()
    if grade:
        return grade.grade
    if score >= 80:
        return "A"
    if score >= 70:
        return "B"
    if score >= 60:
        return "C"
    if score >= 50:
        return "D"
    return "F"
