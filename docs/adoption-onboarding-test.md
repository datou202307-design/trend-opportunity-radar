# Adoption Onboarding acceptance test

Use this protocol with three people who did not participate in development. Test the public repository or the pull-request branch from a clean Agent task. Do not coach the participant beyond the README, and do not commit names, account identifiers, prompts containing confidential information, platform content, local paths, or generated reports.

## Participant task

Ask each participant to:

1. decide which README route applies to them;
2. install the Skill if needed;
3. open a new Agent task and use the README's first-study request;
4. in another clean task, make a plain topic + platform + business-goal request without naming the Skill and record whether the host selects it automatically;
5. follow the specific prerequisite only if the run reports one;
6. identify whether a local report was completed and what the next action is;
7. after at least one saved run exists, use the documented workspace command or ask the Agent to reopen the research workspace.

The participant may stop when the chosen platform requires an unavailable login, adapter, permission, or collection time. Record that as the actual blocking step; do not replace it with invented success or a different platform unless the participant independently chooses the documented import fallback.

## Acceptance record

Use anonymous labels only. A cell is `yes`, `no`, `not reached`, or a short non-sensitive reason.

| Participant | Host and OS | Chose the correct route | Installed successfully | Agent invoked the Skill | Auto-invoked from plain request | First report completed | Reopened via workspace | First blocking step | Would use again |
|---|---|---|---|---|---|---|---|---|---|
| T1 | Pending | Pending | Pending | Pending | Pending | Pending | Pending | Pending | Pending |
| T2 | Pending | Pending | Pending | Pending | Pending | Pending | Pending | Pending | Pending |
| T3 | Pending | Pending | Pending | Pending | Pending | Pending | Pending | Pending | Pending |

## Release gate

Adoption Onboarding passes only when all three participants can identify the correct path and invoke the installed Skill without developer coaching. Installation, first-report completion, workspace return, blockers, and willingness to reuse remain separately reported; do not convert a platform access block into an installation failure or claim complete onboarding when the three records are still pending.
