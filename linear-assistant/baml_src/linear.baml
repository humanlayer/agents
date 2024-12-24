class ClarificationRequest {
    intent "request_more_information"
    message string
}

class DraftIssue {
    intent "ready_to_draft_issue"
    issue Issue
}

class PublishIssue {
    intent "human_approved__issue_ready_to_publish"
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

class Issue {
    id string?
    title string
    description string
    team_id string
}