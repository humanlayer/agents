class ClarificationRequest {
    intent "request_more_information"
    message string
}

class CreateIssue {
    intent "create_issue"
    issue Issue
}

class ListTeams {
    intent "list_teams"
    teams string[]
}

class ListIssues {
    intent "list_issues"
    from_time string
    to_time string
}

class DoneForNow {
    intent "done_for_now"
    message string?
}

class HumanResponse {
    event_type "human_response"
    message string
}


class Issue {
    id string?
    title string
    description string
    team_id string
}

class EmailMessage {
    from_address string
    to_address string[]
    cc_address string[]
    subject string
    content string
    datetime string
}

class EmailPayload {
    from_address string
    to_address string 
    subject string
    body string
    message_id string
    previous_thread EmailMessage[]
    raw_email string
    is_test bool?
}

class Event {
    type "email_received" | "human_response" | "issue_create_result" | "list_teams_result" | "list_issues_result" | "request_more_information" | "create_issue" | "done_for_now" | "list_teams" | "list_issues"
    data EmailPayload | HumanResponse | ClarificationRequest | CreateIssue | ListTeams | ListIssues | string // escape hatch for untyped data from linear client
}


class Thread {
    initial_email EmailPayload
    events Event[]
}

function DetermineNextStep(thread: Thread) -> ClarificationRequest | CreateIssue | ListTeams | ListIssues | DoneForNow {
    client CustomGPT4o
    prompt #"
        {{ _.role("system") }}

        You are a helpful assistant that helps the user with their linear issue management.

        {{ _.role("user") }}

        You are working on the following thread:
        {{ thread }}


        What should the next step be?

        {{ ctx.output_format }}
    "#
}