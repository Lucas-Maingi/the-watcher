"""Connector unit tests - the parsing logic only. Live API calls are
exercised manually; I'm not mocking the whole GitHub REST API for a
portfolio project, but the fiddly parsing bits deserve coverage."""

from watcher.ingest.aws_connector import _summarize_statements
from watcher.ingest.github_connector import DEPLOY_HINTS, SECRET_RE


def test_secret_regex_finds_actions_secrets():
    yaml_ish = """
    steps:
      - run: aws configure
        env:
          AWS_ACCESS_KEY_ID: ${{ secrets.AWS_DEPLOY_KEY }}
          AWS_SECRET_ACCESS_KEY: ${{secrets.AWS_DEPLOY_SECRET}}
          SAFE: ${{ github.sha }}
    """
    found = set(SECRET_RE.findall(yaml_ish))
    assert found == {"AWS_DEPLOY_KEY", "AWS_DEPLOY_SECRET"}


def test_deploy_hints_catch_the_usual_suspects():
    assert any(h in "uses: aws-actions/configure-aws-credentials@v4" for h in DEPLOY_HINTS)
    assert any(h in "run: terraform apply -auto-approve" for h in DEPLOY_HINTS)
    assert not any(h in "run: pytest tests/" for h in DEPLOY_HINTS)


def test_policy_statement_flattening():
    doc = {
        "Version": "2012-10-17",
        "Statement": [
            {"Effect": "Allow", "Action": "s3:*", "Resource": "*"},
            {"Effect": "Allow", "Action": ["sqs:SendMessage"],
             "Resource": ["arn:aws:sqs:us-east-1:123:q1"]},
            {"Effect": "Deny", "Action": "iam:*", "Resource": "*"},
        ],
    }
    actions, resources = _summarize_statements(doc)
    assert actions == ["s3:*", "sqs:SendMessage"]
    assert "iam:*" not in actions  # deny statements aren't grants
    assert "*" in resources


def test_single_statement_dict_not_list():
    # AWS lets Statement be a bare dict; seen it in real bucket policies
    doc = {"Statement": {"Effect": "Allow", "Action": "s3:GetObject", "Resource": "*"}}
    actions, _ = _summarize_statements(doc)
    assert actions == ["s3:GetObject"]
