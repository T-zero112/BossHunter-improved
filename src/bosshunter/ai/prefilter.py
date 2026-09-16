"""Pre-filter module - hard filtering before LLM evaluation."""

import re

from bosshunter.collection.models import classify_recruitment_type
from bosshunter.job_filters import matching_blocked_company, matching_deal_breaker
from bosshunter.job_filters import parse_daily_salary_yuan, parse_monthly_salary_k


_INTERNSHIP_KEYWORDS = ("实习", "intern", "internship")
_RECRUITMENT_TYPE_LABELS = {
    "campus": "校招",
    "experienced": "社招",
    "internship": "实习",
}
_ANONYMOUS_COMPANY_PATTERN = re.compile(
    r"^(?:[\u4e00-\u9fff]{2,4})?某.+(?:公司|企业|集团)$"
)


def quick_score(job: dict, config: dict) -> tuple[int, str]:
    """Apply hard filters before LLM scoring."""
    profile = config.get("profile", {})
    deal_breakers = profile.get("deal_breakers", [])
    jd_deal_breakers = profile.get("jd_deal_breakers", [])
    blocked_companies = profile.get("blocked_companies", [])
    title = job.get("title") or ""
    jd = job.get("jd") or ""
    company = str(job.get("company") or "").strip()

    blocked_company = matching_blocked_company(company, blocked_companies)
    if blocked_company:
        return 0, f"触发公司屏蔽: {blocked_company}"

    if _ANONYMOUS_COMPANY_PATTERN.search(company):
        return 0, "匿名公司岗位"

    breaker = matching_deal_breaker(title, deal_breakers)
    if breaker:
        return 0, f"触发排除词: {breaker}"

    jd_breaker = matching_deal_breaker(jd, jd_deal_breakers)
    if jd_breaker:
        return 0, f"触发JD排除词: {jd_breaker}"

    wanted_type = str(profile.get("recruitment_type") or "").strip()
    job_type = _job_recruitment_type(job)
    if wanted_type in _RECRUITMENT_TYPE_LABELS and job_type != "unknown" and job_type != wanted_type:
        return 0, (
            "招聘类型不匹配: "
            f"{_RECRUITMENT_TYPE_LABELS[job_type]} ≠ {_RECRUITMENT_TYPE_LABELS[wanted_type]}"
        )

    internship_allowed = profile.get("allow_internship", False) or wanted_type in {"internship", "all"}
    if not internship_allowed and (job_type == "internship" or _contains_internship_signal(job)):
        return 0, "实习岗位"

    salary_min = _as_number(profile.get("salary_min", 0))
    salary_max = _as_number(profile.get("salary_max", 0))
    daily_salary_min = _as_number(profile.get("internship_daily_salary_min", 0))
    daily_salary_max = _as_number(profile.get("internship_daily_salary_max", 0))
    salary = job.get("salary") or ""
    parsed_daily_salary = parse_daily_salary_yuan(salary)
    if parsed_daily_salary is not None:
        job_daily_min, job_daily_max = parsed_daily_salary
        if daily_salary_min > 0 and job_daily_max < daily_salary_min:
            return 0, f"日薪低于硬性要求: {_format_yuan(job_daily_max)}元/天 < {_format_yuan(daily_salary_min)}元/天"
        if daily_salary_max > 0 and job_daily_min > daily_salary_max:
            return 0, f"日薪高于期望上限: {_format_yuan(job_daily_min)}元/天 > {_format_yuan(daily_salary_max)}元/天"
        return 100, "预筛通过"

    parsed_monthly_salary = parse_monthly_salary_k(salary)
    if parsed_monthly_salary is None:
        if _as_bool(profile.get("filter_unparsed_salary", True)):
            return 0, "薪资面议/无法解析，已过滤"
        return 100, "薪资面议/无法解析（已关闭过滤，交由 AI 判断）"

    job_salary_min, job_salary_max = parsed_monthly_salary
    if salary_min > 0 and job_salary_max < salary_min:
        return 0, f"薪资低于硬性要求: {_format_k(job_salary_max)}K < {_format_k(salary_min)}K"

    salary_ceil_ratio = max(_as_number(profile.get("salary_ceil_ratio", 1.5)), 1.0)
    if salary_max > 0 and job_salary_min > salary_max * salary_ceil_ratio:
        return 0, (
            f"薪资远超期望上限: 报价下限 {_format_k(job_salary_min)}K > "
            f"{_format_k(salary_max)}K × {salary_ceil_ratio:g}"
        )

    return 100, "预筛通过"


def _contains_internship_signal(job: dict) -> bool:
    title = (job.get("title") or "").lower()
    return any(keyword.lower() in title for keyword in _INTERNSHIP_KEYWORDS)


def _job_recruitment_type(job: dict) -> str:
    value = str(job.get("recruitment_type") or "").strip()
    if value in _RECRUITMENT_TYPE_LABELS:
        return value
    return classify_recruitment_type(
        str(job.get("title") or ""),
        str(job.get("experience") or ""),
        str(job.get("jd") or ""),
    )


def _parse_salary_range_k(salary: str) -> tuple[float, float] | None:
    return parse_monthly_salary_k(salary)


def _as_number(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0


def _as_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on", "是"}
    return True


def _format_k(value: float) -> str:
    return str(int(value)) if value.is_integer() else str(value)


def _format_yuan(value: float) -> str:
    return str(int(value)) if value.is_integer() else str(value)
