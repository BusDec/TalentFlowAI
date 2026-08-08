"""Talent intelligence model test foundation."""

from talent.models import EmployeeSkill, Skill, TrainingNeed


def test_skill_and_employee_skill(staff_user):
    """Skills persist and link to employees with a proficiency rating."""
    skill = Skill.objects.create(name="Python", category="Engineering")
    assert str(skill) == "Python"
    assert skill.category == "Engineering"

    emp_skill = EmployeeSkill.objects.create(
        user=staff_user, skill=skill, proficiency=4.5
    )
    assert float(emp_skill.proficiency) == 4.5
    assert emp_skill.verified is False
    assert "Python" in str(emp_skill)
    assert "4.5" in str(emp_skill)


def test_training_need(tenant):
    """Training needs persist with priority and target counts."""
    need = TrainingNeed.objects.create(
        title="AWS Architecture", priority="high", target_count=5
    )
    assert str(need) == "AWS Architecture"
    assert need.priority == "high"
    assert need.target_count == 5
