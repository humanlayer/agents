import json
import logging
from enum import Enum
import os
from fastapi import BackgroundTasks, FastAPI
from baml_client import b
from baml_client.types import HumanResponse, Thread, Event, EmailPayload as BamlEmailPayload
from typing import Any, Dict
from linear import LinearClient, get_linear_client
import marvin


from pydantic import BaseModel
from humanlayer import AsyncHumanLayer, FunctionCall, HumanContact
from humanlayer.core.models import ContactChannel, HumanContactSpec, FunctionCallSpec
from humanlayer.core.models_agent_webhook import EmailPayload

app = FastAPI(title="HumanLayer FastAPI Email Example", version="1.0.0")

logger = logging.getLogger(__name__)


# Root endpoint
@app.get("/")
async def root() -> Dict[str, str]:
    return {
        "message": "Welcome to a HumanLayer Email Example",
        "instructions": "https://github.com/humanlayer/humanlayer/blob/main/examples/fastapi-email/README.md",
    }


def to_state(thread: Thread) -> dict:
    """Convert thread to a state dict for preservation"""
    return thread.model_dump(mode="json")


def from_state(state: dict) -> Thread:
    """Restore thread from preserved state"""
    return Thread.model_validate(state)


async def handle_continued_thread(thread: Thread) -> None:
    # its dumb that we have to cast this, can probably just remove the need to duplicate the HL type into our baml schema
    casted: EmailPayload = EmailPayload.model_validate(thread.initial_email.model_dump_json())
    humanlayer = AsyncHumanLayer(
        contact_channel=ContactChannel(email=casted.as_channel())
    )

    # maybe: if thread gets too long, summarize parts of it - your call!
    # new_thread = maybe_summarize_parts_of_thread(thread)

    logger.info(
        f"thread received, determining next step. Last event: {thread.events[-1].type}"
    )

    while True:
        next_step = await b.DetermineNextStep(thread)
        logger.info(f"next step: {next_step.intent}")

        if next_step.intent == "request_more_information":
            logger.info(f"requesting more information: {next_step.message}")
            thread.events.append(Event(type="request_more_information", data=next_step))
            await humanlayer.create_human_contact(
                spec=HumanContactSpec(msg=next_step.message, state=to_state(thread))
            )
            logger.info("thread sent to humanlayer. Last event: request_more_information")
            break
        elif next_step.intent == "create_issue":
            logger.info(f"drafted issue: {next_step.model_dump_json()}")
            thread.events.append(Event(type="create_issue", data=next_step))
            await humanlayer.create_function_call(
                spec=FunctionCallSpec(
                    fn="create_issue",
                    kwargs=next_step.model_dump(),
                )
            )
            logger.info("thread sent to humanlayer. Last event: create_issue")
            break
        elif next_step.intent == "list_issues":
            logger.info(f"listing issues: {next_step.model_dump_json()}")
            thread.events.append(Event(type="list_issues", data=next_step))
            client = get_linear_client()
            issues = client.list_all_issues(
                from_time=next_step.from_time, to_time=next_step.to_time
            )
            thread.events.append(
                Event(type="list_issues_result", data=json.dumps(issues))
            )
            continue

        elif next_step.intent == "list_teams":
            logger.info(f"listing teams: {next_step.model_dump_json()}")
            thread.events.append(Event(type="list_teams", data=next_step))
            teams = client.list_all_teams()
            thread.events.append(
                Event(type="list_teams_result", data=json.dumps(teams))
            )
            continue
        else:
            raise ValueError(f"unknown intent: {next_step.intent}")


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
    thread = Thread(initial_email=BamlEmailPayload.model_validate(email_payload.model_dump_json()), events=[])
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
                data=HumanResponse(
                    event_type="human_response",
                    message=human_response.status.response,
                ),
            )
        )
        background_tasks.add_task(handle_continued_thread, thread)
    elif isinstance(human_response, FunctionCall):
        # todo support more functions
        if human_response.spec.fn != "create_issue":
            raise ValueError(f"unknown function call: {human_response.spec.fn}")

        if human_response.status.approved:
            client = get_linear_client()
            issue = client.create_issue(
                title=human_response.spec.kwargs["title"],
                description=human_response.spec.kwargs["description"],
                team_id=human_response.spec.kwargs["team_id"],
            )
            thread.events.append(
                Event(type="issue_create_result", data=json.dumps(issue))
            )
            # resume from here
            background_tasks.add_task(handle_continued_thread, thread)
        elif human_response.status.approved is False:
            thread.events.append(
                Event(
                    type="human_response",
                    data="User denied create_issue with feedback: "
                    + human_response.status.comment,
                )
            )
            # resume from here
            background_tasks.add_task(handle_continued_thread, thread)
        else:
            raise ValueError(
                "got FunctionCall webhook with null status, this should never happen"
            )
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    uvicorn.run(app, host="0.0.0.0", port=8000)  # noqa: S104
