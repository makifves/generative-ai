import json
import os

from github import Github
import requests
import vertexai
from vertexai.generative_models import GenerationConfig, GenerativeModel


def get_pr_number() -> str:
    event_path = os.getenv("GITHUB_EVENT_PATH", "")

    # Load event data
    with open(event_path, "r", encoding="utf-8") as f:
        event_data = json.load(f)

    # Determine the PR number based on the event
    if "pull_request" in event_data:
        return event_data["pull_request"]["number"]

    if (
        "issue" in event_data and "pull_request" in event_data["issue"]
    ):  # For comment events on PRs
        return event_data["issue"]["number"]

    raise ValueError("Unable to determine pull request number from event data.")


def call_gemini(
    pull_request_content: str, model_id: str = "gemini-1.5-flash-001"
) -> str:
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT_ID")
    vertexai.init(project=project_id, location="us-central1")

    model = GenerativeModel(
        model_id,
        system_instruction=[
            "You are an expert software engineer.",
        ],
        generation_config=GenerationConfig(temperature=0.0),
    )

    prompt = [
        "The following is the content of a GitHub Pull Request for a repository focused on Generative AI with Google Cloud. This content includes the Pull Request title, Pull Request description, a list of all of the files changed with the file name, the code diff and the raw file content. Your task is to output a summary of the Pull Request in Markdown format.",
        "Content:",
        pull_request_content,
        "Summary:",
    ]

    print("---Prompt---\n", prompt)
    response = model.generate_content(prompt)
    print("---Gemini Response---\n", response)

    return response.text.replace("## Pull Request Summary", "")


def summarize_pr(token: str, repo_name: str, pr_number: str):
    # Create a GitHub client and access the repository
    g = Github(token)
    repo = g.get_repo(repo_name)
    pr = repo.get_pull(pr_number)

    pull_request_content = ""

    # Extract and print title and description
    pull_request_content += f"Title: {pr.title}\n"
    pull_request_content += f"Pull Request Description: {pr.body}\n"

    # Fetch and print code diff
    pull_request_content += "\n--- Files Changed ---\n"
    for file in pr.get_files():
        pull_request_content += f"File name: {file.filename}\n\n"

        # Attempt to fetch raw content if patch is not available
        if file.patch is None:
            try:
                raw_content = requests.get(file.raw_url).text
                pull_request_content += f"Raw File Content:\n`\n{raw_content}\n`\n\n"
            except requests.exceptions.RequestException:
                pull_request_content += "Unable to fetch raw file content.\n\n"
        else:  # Use patch if available
            pull_request_content += f"Code Diff:\n{file.patch}\n\n"

    gemini_response = call_gemini(pull_request_content)

    latest_commit = pr.get_commits()[0].sha
    comment_header = "## Pull Request Summary from Gemini ✨"
    comment_body = f"{comment_header}\n {gemini_response} \n---\n "

    # Check for existing comments by the bot
    bot_username = "github-actions[bot]"
    for comment in pr.get_issue_comments():
        if comment.user.login == bot_username and comment_header in comment.body:
            # Update the existing comment
            comment_body += f"Updated at `{latest_commit}`\n"
            comment.edit(comment_body)
            return

    # If no existing comment is found, create a new one
    comment_body += f"Generated at `{latest_commit}`\n"
    pr.create_issue_comment(comment_body)


def main():
    # Get GitHub token and repository details
    repo_name = os.getenv("GITHUB_REPOSITORY")
    token = os.getenv("GITHUB_TOKEN")
    pr_number = get_pr_number()

    summarize_pr(token, repo_name=repo_name, pr_number=pr_number)


if __name__ == "__main__":
    main()