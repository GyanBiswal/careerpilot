import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Importance = Literal["required", "preferred"]
Priority = Literal["P1", "P2", "P3"]


# ---- What the LLM must return (also used as the structured-output schema) ----

class SkillMatch(BaseModel):
    skill: str = Field(description="A skill or technology the job description asks for.")
    importance: Importance = Field(
        description="'required' if the job description requires it, 'preferred' if it is a nice-to-have."
    )
    evidence: str = Field(
        description="Where the resume shows this skill (a project, role, or phrase). Must come from the resume."
    )


class SkillGap(BaseModel):
    skill: str = Field(description="A skill the job description asks for that the resume does not show.")
    importance: Importance
    reason: str = Field(description="Why this skill matters for the role, based on the job description.")


class InterviewTopic(BaseModel):
    topic: str = Field(description="A general interview topic, e.g. Python, SQL, REST APIs, System Design.")
    priority: Priority = Field(description="P1 = essential, P2 = useful, P3 = lower priority.")
    reason: str = Field(description="Why this topic is likely to come up.")


class ResumeJDAnalysis(BaseModel):
    resume_skills: list[str] = Field(
        description="Skills and technologies that appear in the resume."
    )
    matched_skills: list[SkillMatch]
    missing_skills: list[SkillGap]
    experience_assessment: str = Field(
        description="Short, honest assessment of how the candidate's experience fits the role and experience category."
    )
    strengths: list[str]
    areas_to_improve: list[str]
    interview_topics: list[InterviewTopic]
    recommendations: list[str] = Field(
        description="Honest, actionable steps (learn, build, practice, or present existing experience better)."
    )


# ---- What the API returns ----

class AnalysisRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    application_id: uuid.UUID
    model_name: str
    match_score: int | None = Field(
        description="Percent of REQUIRED skills with evidence in the resume (calculated in Python)."
    )
    is_outdated: bool = Field(
        default=False,
        description="True if the resume, job description or application changed since this analysis.",
    )
    created_at: datetime
    updated_at: datetime
    result: ResumeJDAnalysis


class AnalysisRunResponse(BaseModel):
    reused: bool = Field(description="True if a saved analysis was returned without calling the LLM.")
    analysis: AnalysisRead