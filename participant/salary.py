"""
participant/salary.py — Salary projection for individual participant lifecycle.

SalaryProfile models pensionable pay over a working life:
  - real growth (productivity)
  - one-off promotion jumps at specified ages
  - CPI indexation (from MacroState.inflation) applied each step

Usage::

    profile = SalaryProfile(base_salary=50_000, real_growth=0.005,
                            promotion_jumps={30: 0.15, 40: 0.20})
    salary = profile.salary_at(age=35, cumulative_inflation=0.12)
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SalaryProfile:
    """Pensionable salary trajectory for one participant.

    Parameters
    ----------
    base_salary:
        Salary at entry age (real, today's €).
    real_growth:
        Annual real salary growth (e.g. 0.005 = 0.5%).
    promotion_jumps:
        Mapping {age: fractional_jump}. Applied multiplicatively once
        in the year the participant turns that age.
    """

    base_salary: float = 50_000.0
    real_growth: float = 0.005
    promotion_jumps: dict[int, float] = field(default_factory=lambda: {30: 0.15, 40: 0.20})

    def real_salary_at(self, age: int, entry_age: int = 25) -> float:
        """Real salary (today's €) at *age*, before CPI uplift."""
        years = max(0, age - entry_age)
        # Apply cumulative real growth
        salary = self.base_salary * (1.0 + self.real_growth) ** years
        # Apply all promotion jumps that have already been reached
        for jump_age, jump_frac in self.promotion_jumps.items():
            if age >= jump_age:
                salary *= 1.0 + jump_frac
        return salary

    def nominal_salary_at(
        self,
        age: int,
        entry_age: int = 25,
        cumulative_inflation: float = 0.0,
    ) -> float:
        """Nominal salary at *age*, applying cumulative CPI uplift."""
        return self.real_salary_at(age, entry_age) * (1.0 + cumulative_inflation)
