from app.core.crud_router import build_crud_router
from app.models.surveys import Survey
from app.schemas.surveys import SurveyCreate, SurveyOut, SurveyUpdate

router = build_crud_router(
    model=Survey,
    create_schema=SurveyCreate,
    update_schema=SurveyUpdate,
    out_schema=SurveyOut,
    prefix="/surveys",
    tags=["Surveys & Feedback"],
    resource_label="surveys",
    search_field="respondent_name",
)
