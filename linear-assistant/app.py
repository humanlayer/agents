import json
import logging
from enum import Enum
import os
from fastapi import BackgroundTasks, FastAPI
from typing import Any, Dict, Literal, Union
from linear import LinearClient
import marvin


from pydantic import BaseModel
from humanlayer import AsyncHumanLayer, FunctionCall, HumanContact
from humanlayer.core.models import ContactChannel, EmailContactChannel, HumanContactSpec
from humanlayer.core.models_agent_webhook import EmailMessage, EmailPayload

app = FastAPI(title="HumanLayer FastAPI Email Example", version="1.0.0")

logger = logging.getLogger(__name__)


# Root endpoint
@app.get("/")
async def root() -> Dict[str, str]:
    return {
        "message": "Welcome to a HumanLayer Email Example",
        "instructions": "https://github.com/humanlayer/humanlayer/blob/main/examples/fastapi-email/README.md",
    }


##############################
########  Biz Logic   ########
##############################
class ClarificationRequest(BaseModel):
    intent: Literal["request_more_information"]
    message: str


class DraftIssue(BaseModel):
    intent: Literal["ready_to_draft_issue"]
    title: str
    description: str
    team_id: str


class PublishIssue(BaseModel):
    intent: Literal["human_approved__issue_ready_to_publish"]
    title: str
    description: str
    team_id: str


class AssignIssue(BaseModel):
    intent: Literal["assign_issue"]
    issue_id: str
    email: str


class GetIssueDetails(BaseModel):
    intent: Literal["get_issue_details"]
    issue_id: str


class GetHighPriorityIssues(BaseModel):
    intent: Literal["get_high_priority_issues"]


class GetUnassignedIssues(BaseModel):
    intent: Literal["get_unassigned_issues"]


class GetIssuesByLabel(BaseModel):
    intent: Literal["get_issues_by_label"]
    label: str


class GetIssuesDueBy(BaseModel):
    intent: Literal["get_issues_due_by"]
    due_date: str


async def determine_next_step(
    thread: "Thread",
) -> Union[
    ClarificationRequest,
    DraftIssue,
    PublishIssue,
    AssignIssue,
    GetIssueDetails,
    GetHighPriorityIssues,
    GetUnassignedIssues,
    GetIssuesByLabel,
    GetIssuesDueBy,
]:
    """determine the next step in the email thread"""

    response: Union[
        ClarificationRequest,
        DraftIssue,
        PublishIssue,
        AssignIssue,
        GetIssueDetails,
        GetHighPriorityIssues,
        GetUnassignedIssues,
        GetIssuesByLabel,
        GetIssuesDueBy,
    ] = await marvin.cast_async(
        json.dumps([event.model_dump(mode="json") for event in thread.events]),
        Union[
            ClarificationRequest,
            DraftIssue,
            PublishIssue,
            AssignIssue,
            GetIssueDetails,
            GetHighPriorityIssues,
            GetUnassignedIssues,
            GetIssuesByLabel,
            GetIssuesDueBy,
        ],
        instructions="""
        determine if you have enough information to create an issue, or if you need more input.
        The issue should be a task that needs to be completed.

        Once an issue is drafted, a human will automatically review it. If the human approves,
        and has not requested any changes, you should publish it.
        """,
    )
    return response


class Issue(BaseModel):
    title: str
    description: str


async def publish_issue(issue_id: int) -> None:
    """tool to publish an issue"""
    raise NotImplementedError("publish_issue")


##########################
######## CONTEXT #########
##########################


class Event(BaseModel):
    type: Literal[
        "email_received",
        "request_more_information",
        "draft_issue",
        "human_approved__issue_ready_to_publish",
        "human_response",
        "assign_issue",
        "publish_issue",
        "get_issue_details",
        "get_high_priority_issues",
        "get_unassigned_issues",
        "get_issues_by_label",
        "get_issues_due_by",
    ]
    data: Any  # don't really care about this, it will just be context to the LLM


# todo you probably want to version this but for now lets assume we're not going to change the schema
class Thread(BaseModel):
    initial_email: EmailPayload
    # initial_slack_message: SlackMessage
    events: list[Event]

    def to_state(self) -> dict:
        """Convert thread to a state dict for preservation"""
        return self.model_dump(mode="json")

    @classmethod
    def from_state(cls, state: dict) -> "Thread":
        """Restore thread from preserved state"""
        return cls.model_validate(state)


##########################
######## Handlers ########
##########################
async def handle_continued_thread(thread: Thread) -> None:
    humanlayer = AsyncHumanLayer(
        contact_channel=ContactChannel(email=thread.initial_email.as_channel())
    )

    # maybe: if thread gets too long, summarize parts of it - your call!
    # new_thread = maybe_summarize_parts_of_thread(thread)

    logger.info(
        f"thread received, determining next step. Last event: {thread.events[-1].type}"
    )
    next_step = await determine_next_step(thread)
    logger.info(f"next step: {next_step.intent}")

    if next_step.intent == "request_more_information":
        logger.info(f"requesting more information: {next_step.message}")
        thread.events.append(
            Event(type="request_more_information", data=next_step.message)
        )
        await humanlayer.create_human_contact(
            spec=HumanContactSpec(msg=next_step.message, state=thread.to_state())
        )

    elif next_step.intent == "ready_to_draft_issue":
        logger.info(f"drafted issue: {next_step.model_dump_json()}")
        thread.events.append(Event(type="draft_issue", data=next_step))
        await humanlayer.create_human_contact(
            spec=HumanContactSpec(
                msg=f"I've drafted an issue with title: {next_step.title} with description: {next_step.description}. Would you like me to publish it?",
                state=thread.to_state(),
            )
        )

    elif next_step.intent == "human_approved__issue_ready_to_publish":
        logger.info(f"publishing issue: {next_step.model_dump_json()}")
        LINEAR_API_KEY = os.environ["LINEAR_API_KEY"]
        if not LINEAR_API_KEY:
            raise ValueError("LINEAR_API_KEY is not set")
        client = LinearClient(api_key=LINEAR_API_KEY)
        client.create_issue(
            title=next_step.title,
            description=next_step.description,
            team_id=next_step.team_id,
        )
        thread.events.append(Event(type="publish_issue", data=next_step))

        await humanlayer.create_human_contact(
            spec=HumanContactSpec(
                msg="Issue has been published. Let me know if you need anything else!",
                state=thread.to_state(),
            )
        )

    else:
        raise ValueError(f"unknown intent: {next_step.intent}")
    logger.info(f"thread sent to humanlayer. Last event: {thread.events[-1].type}")


@app.post("/webhook/new-email-thread")
async def email_inbound(
    email_payload: EmailPayload, background_tasks: BackgroundTasks
) -> Dict[str, Any]:
    """
    route to kick off new processing thread from an email
    """
    # test payload
    if (
        email_payload.is_test
        or email_payload.from_address == "overworked-admin@coolcompany.com"
    ):
        logger.info("test payload received, skipping")
        return {"status": "ok"}

    logger.info(f"inbound email received: {email_payload.model_dump_json()}")
    thread = Thread(initial_email=email_payload, events=[])
    thread.events.append(Event(type="email_received", data=email_payload))

    background_tasks.add_task(handle_continued_thread, thread)

    return {"status": "ok"}


@app.post("/webhook/human-response-on-existing-thread")
async def human_response(
    human_response: FunctionCall | HumanContact, background_tasks: BackgroundTasks
) -> Dict[str, Any]:
    """
    route to handle human responses
    """

    if human_response.spec.state is not None:
        thread = Thread.model_validate(human_response.spec.state)
    else:
        # decide what's the right way to handle this? probably logger.warn and proceed
        raise ValueError("state is required")

    if isinstance(human_response, HumanContact):
        thread.events.append(
            Event(
                type="human_response",
                data={"human_response": human_response.status.response},
            )
        )
        background_tasks.add_task(handle_continued_thread, thread)

    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    uvicorn.run(app, host="0.0.0.0", port=8000)  # noqa: S104
